from datetime import date, timedelta
from decimal import Decimal
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.gasto import Gasto, GastoAdjunto, CATEGORIAS, FORMAS_PAGO, TIPOS_COMPROBANTE, SECTORES
from app.models.proveedor import Proveedor
from app.models.caja import MovimientoCaja
from app.models.banco import MovimientoBanco, ExtractoBancario
from app.schemas.gasto import GastoCreate, GastoUpdate, GastoResponse
from app.storage_util import subir_comprobante, crear_subida_firmada, storage_configurado
from app.tz import ahora_ar
from app.auth import get_current_user
from app.factura_pdf import cuit_valido

router = APIRouter(prefix="/api/gastos", tags=["Gastos"])


def _norm_cuit(cuit) -> str:
    return "".join(ch for ch in str(cuit or "") if ch.isdigit())


def _entero(x) -> int | None:
    d = _norm_cuit(x)
    return int(d) if d else None


def gasto_duplicado(db: Session, cuit, punto_venta, numero, tipo=None, excluir_id: int | None = None) -> Gasto | None:
    """Mismo proveedor + punto de venta + número (+ tipo si se conoce) = el mismo comprobante."""
    c, pv, nro = _norm_cuit(cuit), _entero(punto_venta), _entero(numero)
    if not (c and nro):
        return None
    for g in db.query(Gasto).filter(Gasto.cuit == c).all():
        if g.id == excluir_id or _entero(g.numero) != nro or (pv is not None and _entero(g.punto_venta) not in (pv, None)):
            continue
        if tipo and g.tipo_comprobante and g.tipo_comprobante != tipo:
            continue
        return g
    return None


def _error_duplicado(g: Gasto):
    raise HTTPException(409, f"Ese comprobante ya está cargado: {g.razon_social or g.cuit} "
                             f"{g.punto_venta or ''}-{g.numero or ''} del {g.fecha:%d/%m/%Y} (gasto #{g.id}).")


def _estado(g: Gasto, hoy: date) -> str:
    if not g.revisado:
        return "por_revisar"
    if g.forma_pago or Decimal(str(g.importe)) < 0:
        return "pagada"
    if g.vencimiento and g.vencimiento < hoy:
        return "vencida"
    return "pendiente"


@router.get("/storage-estado")
def storage_estado():
    """Indica si Supabase Storage está configurado (para mostrar avisos en la interfaz)."""
    return {"configurado": storage_configurado()}


@router.post("/adjunto")
async def subir_adjunto(archivo: UploadFile = File(...)):
    """Sube la foto/PDF del comprobante a Storage y devuelve su URL pública."""
    contenido = await archivo.read()
    if len(contenido) > 10 * 1024 * 1024:
        raise HTTPException(400, "El archivo supera los 10 MB.")
    try:
        url = subir_comprobante(contenido, archivo.filename, archivo.content_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"url": url}


@router.get("/adjuntos/{adj_id}")
def ver_adjunto(adj_id: int, db: Session = Depends(get_db)):
    """Comprobante guardado en la base (las facturas escaneadas que se cargaron desde los PDF)."""
    a = db.get(GastoAdjunto, adj_id)
    if not a:
        raise HTTPException(404, "Comprobante no encontrado")
    nombre = re.sub(r'[^\w .()-]', "_", a.nombre)
    return Response(a.contenido, media_type=a.content_type,
                    headers={"Content-Disposition": f'inline; filename="{nombre}"', "Cache-Control": "private, max-age=3600"})


@router.post("/adjunto-firma")
def firmar_adjunto(datos: dict):
    """Devuelve una URL firmada para subir el comprobante directo a Storage desde el navegador."""
    nombre = str(datos.get("nombre") or "")
    if int(datos.get("tamanio") or 0) > 10 * 1024 * 1024:
        raise HTTPException(400, "El archivo supera los 10 MB.")
    try:
        return crear_subida_firmada(nombre)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _vincular_proveedor_por_cuit(db: Session, g: Gasto):
    """Si la factura quedó sin proveedor pero su CUIT es de un proveedor cargado, la vincula (no se pierde de su ficha)."""
    if not g.proveedor_id and g.cuit:
        p = db.query(Proveedor).filter(Proveedor.cuit == _norm_cuit(g.cuit)).first()
        if p:
            g.proveedor_id = p.id


def _completar_proveedor(data: dict, db: Session):
    """Si se eligio un proveedor, copia su razon social y CUIT al gasto."""
    if data.get("proveedor_id"):
        p = db.get(Proveedor, data["proveedor_id"])
        if not p:
            raise HTTPException(404, "Proveedor no encontrado")
        data.setdefault("razon_social", None)
        data.setdefault("cuit", None)
        if not data.get("razon_social"):
            data["razon_social"] = p.razon_social
        if not data.get("cuit"):
            data["cuit"] = p.cuit
    return data


@router.get("/meta")
def meta():
    """Listas fijas para los desplegables del formulario."""
    return {
        "categorias": CATEGORIAS,
        "sectores": SECTORES,
        "formas_pago": FORMAS_PAGO,
        "tipos_comprobante": TIPOS_COMPROBANTE,
    }


@router.get("/", response_model=list[GastoResponse])
def listar(
    q: str | None = None,
    categoria: str | None = None,
    forma_pago: str | None = None,
    mes: int | None = None,
    anio: int | None = None,
    estado: str | None = None,
    sector: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Gasto)
    if sector == "sin":
        query = query.filter(Gasto.sector.is_(None))
    elif sector:
        query = query.filter(Gasto.sector == sector)
    hoy = ahora_ar().date()
    if estado == "por_revisar":
        query = query.filter(Gasto.revisado.is_(False))
    elif estado == "pagada":
        query = query.filter(Gasto.revisado.isnot(False), or_(Gasto.forma_pago.isnot(None), Gasto.importe < 0))
    elif estado in ("pendiente", "vencida"):
        query = query.filter(Gasto.revisado.isnot(False), Gasto.forma_pago.is_(None), Gasto.importe > 0)
        if estado == "vencida":
            query = query.filter(Gasto.vencimiento < hoy)
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(
            Gasto.razon_social.ilike(t),
            Gasto.cuit.ilike(t),
            Gasto.concepto.ilike(t),
            Gasto.rubro.ilike(t),
            Gasto.destino.ilike(t),
            Gasto.numero.ilike(t),
        ))
    if categoria:
        query = query.filter(Gasto.categoria == categoria)
    if forma_pago:
        query = query.filter(Gasto.forma_pago == forma_pago)
    if anio:
        query = query.filter(extract("year", Gasto.fecha) == anio)
    if mes:
        query = query.filter(extract("month", Gasto.fecha) == mes)
    return query.order_by(Gasto.fecha.desc(), Gasto.id.desc()).all()


@router.get("/resumen")
def resumen(mes: int | None = None, anio: int | None = None, db: Session = Depends(get_db)):
    """Total general y subtotales por categoria (respeta los filtros de mes/anio)."""
    query = db.query(Gasto)
    if anio:
        query = query.filter(extract("year", Gasto.fecha) == anio)
    if mes:
        query = query.filter(extract("month", Gasto.fecha) == mes)
    total = query.with_entities(func.coalesce(func.sum(Gasto.importe), 0)).scalar() or 0
    por_cat = (
        query.with_entities(Gasto.categoria, func.coalesce(func.sum(Gasto.importe), 0), func.count(Gasto.id))
        .group_by(Gasto.categoria).all()
    )
    cantidad = query.count()
    hoy = ahora_ar().date()
    impagas = db.query(Gasto).filter(Gasto.forma_pago.is_(None), Gasto.importe > 0).all()
    suma = lambda lista: float(sum((Decimal(str(g.importe)) for g in lista), Decimal("0")))
    vencidas = [g for g in impagas if g.vencimiento and g.vencimiento < hoy]
    semana = [g for g in impagas if g.vencimiento and hoy <= g.vencimiento <= hoy + timedelta(days=7)]
    return {
        "a_pagar": {"total": suma(impagas), "cantidad": len(impagas), "vencido": suma(vencidas), "vencidas": len(vencidas),
                    "esta_semana": suma(semana), "semana": len(semana)},
        "por_revisar": db.query(Gasto).filter(Gasto.revisado.is_(False)).count(),
        "total": float(total),
        "cantidad": cantidad,
        "por_categoria": [
            {"categoria": c or "Sin categoría", "total": float(t), "cantidad": n}
            for c, t, n in por_cat
        ],
    }


def _filtrar_periodo(query, desde: str | None, hasta: str | None, categoria: str | None = None):
    if desde:
        query = query.filter(Gasto.fecha >= date.fromisoformat(desde))
    if hasta:
        query = query.filter(Gasto.fecha <= date.fromisoformat(hasta))
    if categoria:
        query = query.filter(Gasto.categoria == categoria)
    return query


def _agrupar(gastos: list[Gasto], clave, total_general: Decimal) -> list[dict]:
    g = {}
    for x in gastos:
        k = clave(x) or "Sin especificar"
        d = g.setdefault(k, {"nombre": k, "total": Decimal("0"), "cantidad": 0})
        d["total"] += Decimal(str(x.importe))
        d["cantidad"] += 1
    salida = sorted(g.values(), key=lambda d: -d["total"])
    for d in salida:
        d["porcentaje"] = round(float(d["total"] / total_general * 100), 1) if total_general else 0
        d["total"] = float(d["total"])
    return salida


@router.get("/estadisticas")
def estadisticas(desde: str | None = None, hasta: str | None = None, categoria: str | None = None,
                 db: Session = Depends(get_db)):
    """Análisis de gastos del período: por rubro, proveedor, categoría, destino y mes (con %)."""
    gastos = _filtrar_periodo(db.query(Gasto), desde, hasta, categoria).all()
    total = sum((Decimal(str(x.importe)) for x in gastos), Decimal("0"))
    facturas = [x for x in gastos if Decimal(str(x.importe)) > 0]
    pagados = [x for x in facturas if x.forma_pago]
    pendiente = sum((Decimal(str(x.importe)) for x in facturas if not x.forma_pago), Decimal("0"))

    # Proveedores: total, cantidad, % y última factura
    provs = {}
    for x in gastos:
        k = x.proveedor_id or f"cuit:{x.cuit or x.razon_social or '-'}"
        d = provs.setdefault(k, {"proveedor_id": x.proveedor_id, "razon_social": x.razon_social or "Sin proveedor",
                                 "cuit": x.cuit, "rubro": x.rubro, "total": Decimal("0"), "cantidad": 0,
                                 "ultima": None, "pendiente": Decimal("0")})
        imp = Decimal(str(x.importe))
        d["total"] += imp
        d["cantidad"] += 1
        if imp > 0 and not x.forma_pago:
            d["pendiente"] += imp
        if not d["ultima"] or x.fecha > d["ultima"]:
            d["ultima"] = x.fecha
    por_proveedor = sorted(provs.values(), key=lambda d: -d["total"])
    for d in por_proveedor:
        d["porcentaje"] = round(float(d["total"] / total * 100), 1) if total else 0
        d["total"], d["pendiente"] = float(d["total"]), float(d["pendiente"])
        d["ultima"] = str(d["ultima"]) if d["ultima"] else None

    # Evolución mensual (incluye meses sin gastos dentro del rango)
    meses = {}
    for x in gastos:
        k = (x.fecha.year, x.fecha.month)
        meses[k] = meses.get(k, Decimal("0")) + Decimal(str(x.importe))
    if meses:
        (a, m), fin = min(meses), max(meses)
        serie = []
        while (a, m) <= fin:
            serie.append({"anio": a, "mes": m, "total": float(meses.get((a, m), 0))})
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    else:
        serie = []

    return {
        "kpis": {
            "total": float(total), "cantidad": len(gastos), "facturas": len(facturas),
            "promedio": float(total / len(facturas)) if facturas else 0,
            "proveedores": len(provs), "pagadas": len(pagados), "pendiente_pago": float(pendiente),
            "conciliadas": sum(1 for x in facturas if x.conciliado),
        },
        "por_rubro": _agrupar(gastos, lambda x: x.rubro, total),
        "por_categoria": _agrupar(gastos, lambda x: x.categoria, total),
        "por_destino": _agrupar(gastos, lambda x: x.destino, total),
        "por_forma_pago": _agrupar(gastos, lambda x: x.forma_pago or "Pendiente de pago", total),
        "por_proveedor": por_proveedor,
        "por_mes": serie,
    }


def _fmt_pesos(n) -> str:
    return f"${Decimal(str(n)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.get("/por-proveedor/{proveedor_id}")
def facturas_de_proveedor(proveedor_id: int, desde: str | None = None, hasta: str | None = None,
                          db: Session = Depends(get_db)):
    """Todas las facturas de un proveedor con totales (pagado, pendiente) y evolución mensual."""
    p = db.get(Proveedor, proveedor_id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    q = db.query(Gasto).filter(or_(Gasto.proveedor_id == p.id, Gasto.cuit == p.cuit))
    gastos = _filtrar_periodo(q, desde, hasta).order_by(Gasto.fecha.desc()).all()
    total = sum((Decimal(str(x.importe)) for x in gastos), Decimal("0"))
    pagado = sum((Decimal(str(x.importe)) for x in gastos if x.forma_pago or Decimal(str(x.importe)) < 0), Decimal("0"))
    meses = {}
    for x in gastos:
        k = f"{x.fecha.year}-{x.fecha.month:02d}"
        meses[k] = meses.get(k, 0) + float(x.importe)
    # pagos del banco por un importe distinto al de la factura (con el motivo anotado al conciliar); si se pagaron
    # varias facturas juntas, o una factura en varios pagos, la diferencia es la del grupo (se cuenta una vez)
    from app.routers.conciliacion import grupo_de
    info_pago, diferencia, vistos = {}, Decimal("0"), set()
    for x in gastos:
        movs_g, facts_g = grupo_de(db, g=x)
        if not movs_g:
            continue
        pagado_g = sum((abs(Decimal(str(m.importe))) for m in movs_g), Decimal("0"))
        facturado_g = sum((abs(Decimal(str(f.importe))) for f in facts_g), Decimal("0"))
        nota = next((m.nota_conciliacion for m in movs_g if m.nota_conciliacion), None)
        clave = (tuple(sorted(m.id for m in movs_g)), tuple(sorted(f.id for f in facts_g)))
        if nota and clave not in vistos:
            vistos.add(clave)
            diferencia += pagado_g - facturado_g
        if nota or len(movs_g) > 1 or len(facts_g) > 1:
            info_pago[x.id] = {"pagado": pagado_g, "nota": nota,
                               "junto": (f"pagada junto con {len(facts_g) - 1} factura{'s' if len(facts_g) > 2 else ''} más "
                                         f"(transferencia de {_fmt_pesos(pagado_g)} por {_fmt_pesos(facturado_g)})") if len(facts_g) > 1
                               else (f"pagada en {len(movs_g)} transferencias" if len(movs_g) > 1 else None)}
    return {
        "proveedor": {"id": p.id, "razon_social": p.razon_social, "cuit": p.cuit, "rubro": p.rubro,
                      "contacto": p.contacto, "telefono": p.telefono, "email": p.email, "cbu": p.cbu},
        "total": float(total), "pagado": float(pagado), "pendiente": float(total - pagado),
        "diferencia_banco": float(diferencia),  # + se transfirió de más, - de menos (por las facturas del período)
        "cantidad": len(gastos),
        "por_mes": [{"periodo": k, "total": v} for k, v in sorted(meses.items())],
        "facturas": [{
            "id": x.id, "fecha": str(x.fecha), "tipo": x.tipo_comprobante,
            "numero": f"{x.punto_venta or ''}-{x.numero or ''}".strip("-"), "concepto": x.concepto,
            "categoria": x.categoria, "destino": x.destino, "importe": float(x.importe),
            "forma_pago": x.forma_pago, "fecha_pago": str(x.fecha_pago) if x.fecha_pago else None,
            "conciliado": bool(x.conciliado), "adjunto_url": x.adjunto_url,
            "pagado_banco": float(info_pago[x.id]["pagado"]) if x.id in info_pago else None,
            "nota_diferencia": info_pago[x.id]["nota"] if x.id in info_pago else None,
            "pago_conjunto": info_pago[x.id]["junto"] if x.id in info_pago else None,
        } for x in gastos],
    }


@router.get("/totales-proveedores")
def totales_proveedores(db: Session = Depends(get_db)):
    """Total facturado, cantidad y última factura por proveedor (para la tabla de proveedores)."""
    filas = (db.query(Gasto.proveedor_id, func.coalesce(func.sum(Gasto.importe), 0), func.count(Gasto.id), func.max(Gasto.fecha))
             .filter(Gasto.proveedor_id.isnot(None)).group_by(Gasto.proveedor_id).all())
    return {str(pid): {"total": float(t), "cantidad": n, "ultima": str(u) if u else None} for pid, t, n, u in filas}


@router.get("/sugerencias")
def sugerencias(cuit: str | None = None, proveedor_id: int | None = None, db: Session = Depends(get_db)):
    """Rubro, categoría, destino y concepto de la última factura del proveedor (para completar más rápido)."""
    q = db.query(Gasto)
    if proveedor_id:
        q = q.filter(Gasto.proveedor_id == proveedor_id)
    elif cuit:
        q = q.filter(Gasto.cuit == _norm_cuit(cuit))
    else:
        return {}
    g = q.filter(Gasto.revisado.isnot(False)).order_by(Gasto.fecha.desc(), Gasto.id.desc()).first()
    if not g:
        return {}
    return {"rubro": g.rubro, "categoria": g.categoria, "destino": g.destino, "concepto": g.concepto}


def _gastos_del_mes(db: Session, anio: int, mes: int, por: str) -> list[Gasto]:
    """Facturas del mes: por la fecha de la factura (lo habitual) o por la fecha en que se pagó."""
    if not 1 <= mes <= 12:
        raise HTTPException(400, "Mes inválido")
    desde = date(anio, mes, 1)
    hasta = date(anio + (mes == 12), mes % 12 + 1, 1)
    campo = Gasto.fecha_pago if por == "pago" else Gasto.fecha
    return db.query(Gasto).filter(campo >= desde, campo < hasta).order_by(Gasto.fecha, Gasto.id).all()


def _con_proveedor(db: Session, gastos: list[Gasto]) -> list[Gasto]:
    """Asocia a cada factura su proveedor actual (por proveedor o, si no quedó vinculada, por CUIT)."""
    por_id = {p.id: p for p in db.query(Proveedor).all()}
    por_cuit = {p.cuit: p for p in por_id.values() if p.cuit}
    for g in gastos:
        g._prov = por_id.get(g.proveedor_id) or por_cuit.get(_norm_cuit(g.cuit))
    return gastos


@router.get("/excel-contadora/vista")
def excel_contadora_vista(anio: int, mes: int, por: str = "factura", db: Session = Depends(get_db)):
    """Lo que va a tener el Excel para la contadora: totales por destino y lo que conviene revisar antes."""
    from app.excel_contadora import nombre_proveedor
    gastos = _con_proveedor(db, _gastos_del_mes(db, anio, mes, por))
    destinos = {c: {"cantidad": 0, "total": 0.0} for c in CATEGORIAS}
    sin_destino = []
    for g in gastos:
        if g.categoria in destinos:
            destinos[g.categoria]["cantidad"] += 1
            destinos[g.categoria]["total"] += float(g.importe)
        else:
            sin_destino.append(g)
    corto = lambda g: {"id": g.id, "fecha": str(g.fecha), "razon_social": nombre_proveedor(g), "importe": float(g.importe),
                       "categoria": g.categoria}
    return {
        "cantidad": len(gastos), "total": round(sum(d["total"] for d in destinos.values()), 2),
        "por_destino": [{"categoria": c, **v} for c, v in destinos.items()],
        "sin_destino": [corto(g) for g in sin_destino],
        "sin_revisar": [corto(g) for g in gastos if not g.revisado],
        "sin_pagar": sum(1 for g in gastos if not g.forma_pago),
    }


@router.get("/excel-contadora")
def excel_contadora(anio: int, mes: int, por: str = "factura", db: Session = Depends(get_db)):
    """Excel del mes con el formato de la planilla modelo (TOTALES + una hoja por destino)."""
    from fastapi.responses import Response
    from app.excel_contadora import MESES, generar
    gastos = _con_proveedor(db, _gastos_del_mes(db, anio, mes, por))
    nombre = f"Gastos {MESES[mes - 1].upper()}-{anio}.xlsx"
    return Response(generar(gastos, anio, mes),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/{gasto_id}", response_model=GastoResponse)
def obtener(gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    return g


def _validar_pago(forma_pago, fecha_pago, fecha_factura=None):
    """Pago cargado a mano: la fecha es cuándo salió la plata (va en la columna PAGOS del Excel)."""
    if fecha_pago and not forma_pago:
        raise HTTPException(400, "Elegí el medio de pago (efectivo, transferencia…) para esa fecha de pago.")
    if forma_pago and forma_pago not in FORMAS_PAGO:
        raise HTTPException(400, "Medio de pago inválido")
    if fecha_pago and fecha_pago > ahora_ar().date() + timedelta(days=1):
        raise HTTPException(400, "La fecha de pago no puede ser futura.")


@router.post("/", response_model=GastoResponse, status_code=201)
def crear(data: GastoCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    d = data.model_dump()
    # el pago se registra después: conciliando con el banco o registrando el pago en efectivo
    d["forma_pago"] = d["fecha_pago"] = None
    cuit = _norm_cuit(d.get("cuit"))
    if cuit and not cuit_valido(cuit):
        raise HTTPException(400, "El CUIT no es válido (revisá los 11 dígitos).")
    dup = gasto_duplicado(db, cuit, d.get("punto_venta"), d.get("numero"), d.get("tipo_comprobante"))
    if dup:
        _error_duplicado(dup)
    if cuit:
        d["cuit"] = cuit
    d["creado_por"] = user["nombre"]
    d["origen"] = "portal" if d.get("factura_recibida_id") else "manual"
    prov = None
    if d.get("proveedor_id"):
        prov = db.get(Proveedor, d["proveedor_id"])
    elif cuit:
        prov = db.query(Proveedor).filter(Proveedor.cuit == cuit).first()

    if prov:
        d["proveedor_id"] = prov.id
        if not d.get("razon_social"):
            d["razon_social"] = prov.razon_social
        if not d.get("cuit"):
            d["cuit"] = prov.cuit
        if not d.get("rubro"):
            d["rubro"] = prov.rubro
    elif cuit and d.get("razon_social"):
        # Proveedor nuevo: se da de alta automaticamente en la base
        prov = Proveedor(cuit=cuit, razon_social=d["razon_social"], rubro=d.get("rubro"))
        db.add(prov)
        db.flush()
        d["proveedor_id"] = prov.id

    g = Gasto(**d)
    db.add(g)
    db.flush()
    if g.factura_recibida_id:  # se cargó a mano desde la bandeja de facturas recibidas
        from app.models.factura_recibida import FacturaRecibida
        fr = db.get(FacturaRecibida, g.factura_recibida_id)
        if fr:
            fr.estado, fr.gasto_id = "cargada", g.id
            g.adjunto_url = g.adjunto_url or f"/api/facturas-recibidas/{fr.id}/archivo"
    db.commit()
    db.refresh(g)
    return g


@router.put("/{gasto_id}", response_model=GastoResponse)
def actualizar(gasto_id: int, data: GastoUpdate, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    cambios = _completar_proveedor(data.model_dump(exclude_unset=True), db)
    # El medio de pago sale de conciliar con el banco o de registrar el pago en efectivo: no se carga a mano.
    if "forma_pago" in cambios and (cambios["forma_pago"] or None) != (g.forma_pago or None):
        raise HTTPException(400, "El medio de pago se completa al conciliar con el extracto del banco o al registrar "
                                 "el pago en efectivo (botón «Vincular pago»).")
    cambios.pop("forma_pago", None)
    if "fecha_pago" in cambios and cambios["fecha_pago"] != g.fecha_pago:
        if not g.forma_pago:
            raise HTTPException(400, "Primero registrá el pago (conciliación bancaria o pago en efectivo).")
        if g.conciliado and not g.caja_mov_id:
            raise HTTPException(400, "La fecha de un pago por banco sale del extracto conciliado.")
        _validar_pago(g.forma_pago, cambios["fecha_pago"])
        if g.caja_mov_id and cambios["fecha_pago"]:
            mov = db.get(MovimientoCaja, g.caja_mov_id)
            if mov:
                mov.fecha = cambios["fecha_pago"]  # el egreso de caja queda con la misma fecha
    if "cuit" in cambios and cambios["cuit"]:
        cambios["cuit"] = _norm_cuit(cambios["cuit"])
        if not cuit_valido(cambios["cuit"]):
            raise HTTPException(400, "El CUIT no es válido (revisá los 11 dígitos).")
    dup = gasto_duplicado(db, cambios.get("cuit", g.cuit), cambios.get("punto_venta", g.punto_venta),
                          cambios.get("numero", g.numero), cambios.get("tipo_comprobante", g.tipo_comprobante), excluir_id=g.id)
    if dup:
        _error_duplicado(dup)
    for campo, valor in cambios.items():
        setattr(g, campo, valor)
    _vincular_proveedor_por_cuit(db, g)
    db.commit()
    db.refresh(g)
    return g


@router.get("/{gasto_id}/candidatos-pago")
def candidatos_pago(gasto_id: int, db: Session = Depends(get_db)):
    """Movimientos (banco o caja efectivo) que podrían ser el pago de este gasto."""
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    objetivo = abs(Decimal(str(g.importe)))
    cuit = _norm_cuit(g.cuit)

    from app.routers.conciliacion import _palabras, _nombre_mov, TOLERANCIA, cuits_equivalentes, mismo_cuit
    eq = cuits_equivalentes(db)
    nombre = _palabras(g.razon_social)
    bancos = []
    for b in db.query(MovimientoBanco).filter(MovimientoBanco.conciliado == False,  # noqa: E712
                                              MovimientoBanco.sin_factura.is_(None)).all():
        coincide_monto = abs(abs(Decimal(str(b.importe))) - objetivo) <= TOLERANCIA
        coincide_cuit = mismo_cuit(b.cuit, cuit, eq)
        coincide_nombre = bool(nombre & _nombre_mov(b))  # débitos directos sin CUIT, DEBIN a otra cuenta
        if coincide_monto or coincide_cuit or coincide_nombre:
            bancos.append({
                "id": b.id, "fecha": str(b.fecha), "descripcion": b.descripcion,
                "cuit": b.cuit, "razon_social": b.razon_social,
                "importe": float(abs(b.importe)),
                "coincide_monto": coincide_monto, "coincide_cuit": coincide_cuit, "coincide_nombre": coincide_nombre,
            })
    bancos.sort(key=lambda x: (-(x["coincide_cuit"] + x["coincide_nombre"] + x["coincide_monto"]), x["fecha"]))

    usados = {x.caja_mov_id for x in db.query(Gasto).filter(Gasto.caja_mov_id.isnot(None)).all()}
    cajas = []
    for c in db.query(MovimientoCaja).filter(MovimientoCaja.tipo == "egreso").all():
        if c.id in usados and c.id != g.caja_mov_id:
            continue
        if abs(Decimal(str(c.monto))) == objetivo:
            cajas.append({
                "id": c.id, "fecha": str(c.fecha), "concepto": c.concepto,
                "tipo_movimiento": c.tipo_movimiento, "importe": float(c.monto),
            })
    return {"banco": bancos, "caja": cajas}


class VinculoBanco(BaseModel):
    nota: str | None = None  # motivo si el importe del banco no es igual al de la factura


@router.post("/{gasto_id}/pago/banco/{banco_id}")
def pago_banco(gasto_id: int, banco_id: int, data: VinculoBanco | None = None, db: Session = Depends(get_db)):
    """Vincula el gasto a un movimiento del banco (= conciliar). Forma de pago: Transferencia o Débito."""
    from app.routers.conciliacion import vincular_grupo
    g = db.get(Gasto, gasto_id)
    b = db.get(MovimientoBanco, banco_id)
    if not g or not b:
        raise HTTPException(404, "Gasto o movimiento no encontrado")
    if b.gasto_id and b.gasto_id != g.id:
        raise HTTPException(409, "Ese movimiento del banco ya está conciliado con otra factura.")
    g.caja_mov_id = None
    vincular_grupo(db, [b], [g], data.nota if data else None)
    db.commit()
    return {"ok": True, "mensaje": "Pago vinculado con el movimiento del banco"}


@router.post("/{gasto_id}/pago/caja/{caja_id}")
def pago_caja(gasto_id: int, caja_id: int, db: Session = Depends(get_db)):
    """Vincula el gasto a un egreso de caja existente. Forma de pago: Efectivo."""
    g = db.get(Gasto, gasto_id)
    c = db.get(MovimientoCaja, caja_id)
    if not g or not c:
        raise HTTPException(404, "Gasto o movimiento no encontrado")
    if c.tipo != "egreso":
        raise HTTPException(400, "El movimiento de caja debe ser un egreso")
    g.caja_mov_id = c.id
    g.forma_pago = "Efectivo"
    g.fecha_pago = c.fecha
    db.commit()
    return {"ok": True, "mensaje": "Pago vinculado con la caja en efectivo"}


class PagoEfectivo(BaseModel):
    fecha: date | None = None  # cuándo salió la plata de la caja (por defecto, hoy)


@router.post("/{gasto_id}/pago/efectivo-nuevo")
def pago_efectivo_nuevo(gasto_id: int, data: PagoEfectivo | None = None, db: Session = Depends(get_db)):
    """Registra un egreso de caja por el importe del gasto y lo vincula como pago en efectivo."""
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    if g.forma_pago or g.caja_mov_id:
        raise HTTPException(400, "Esta factura ya tiene el pago registrado.")
    fecha = (data.fecha if data and data.fecha else None) or ahora_ar().date()
    if fecha > ahora_ar().date():
        raise HTTPException(400, "La fecha de pago no puede ser futura.")
    c = MovimientoCaja(
        fecha=fecha,
        concepto=f"Pago {g.razon_social or 'proveedor'}",
        tipo_movimiento="Pago proveedor",
        tipo="egreso",
        monto=abs(Decimal(str(g.importe))),
    )
    db.add(c)
    db.flush()
    g.caja_mov_id = c.id
    g.forma_pago = "Efectivo"
    g.fecha_pago = c.fecha
    db.commit()
    return {"ok": True, "mensaje": "Egreso de caja registrado y vinculado"}


@router.post("/{gasto_id}/desvincular-pago")
def desvincular_pago(gasto_id: int, db: Session = Depends(get_db)):
    """Deshace el vínculo de pago (banco o caja) y borra forma/fecha de pago."""
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    # Liberar movimiento de banco que apunte a este gasto
    from app.routers.conciliacion import grupo_de, desvincular_grupo
    if grupo_de(db, g=g)[0]:  # conciliada con uno o varios pagos del banco (con otras facturas o sola)
        desvincular_grupo(db, g=g)
    if g.banco_mov_id:  # pagada vía un encargado: la transferencia vuelve a tener saldo a rendir
        from app import rendiciones
        rendiciones.desvincular(db, g)
    g.conciliado = False
    g.caja_mov_id = None
    g.forma_pago = None
    g.fecha_pago = None
    db.commit()
    return {"ok": True, "mensaje": "Pago desvinculado"}


def borrar_gasto(db: Session, g: Gasto) -> bool:
    """Borra el gasto liberando todo lo que apunta a él. Si se pagó en efectivo con un egreso de caja que
    creó el sistema solo para esta factura, ese egreso también se borra. Devuelve si borró un egreso."""
    caja_borrada = False
    if g.caja_mov_id:
        c = db.get(MovimientoCaja, g.caja_mov_id)
        otros = db.query(Gasto).filter(Gasto.caja_mov_id == g.caja_mov_id, Gasto.id != g.id).count()
        g.caja_mov_id = None
        db.flush()
        if c and not otros and c.tipo_movimiento == "Pago proveedor":
            db.delete(c)
            caja_borrada = True
    # Liberar lo que apunta a este gasto (si no, la base rechaza el borrado)
    from app.routers.conciliacion import grupo_de, desvincular_grupo
    if grupo_de(db, g=g)[0]:
        desvincular_grupo(db, g=g)
    if g.banco_mov_id:
        from app import rendiciones
        rendiciones.desvincular(db, g)
    for b in db.query(MovimientoBanco).filter(MovimientoBanco.gasto_id == g.id).all():
        b.gasto_id, b.conciliado, b.conciliado_manual = None, False, False
    for e in db.query(ExtractoBancario).filter(ExtractoBancario.comisiones_gasto_id == g.id).all():
        e.comisiones_gasto_id = None
    for nc in db.query(Gasto).filter(Gasto.nc_de_id == g.id).all():
        nc.nc_de_id = None
    for a in db.query(GastoAdjunto).filter(GastoAdjunto.gasto_id == g.id).all():
        db.delete(a)
    from app.models.factura_recibida import FacturaRecibida
    for fr in db.query(FacturaRecibida).filter(FacturaRecibida.gasto_id == g.id).all():
        # se eliminó a propósito: queda descartada (no vuelve a la bandeja para cargar)
        fr.gasto_id, fr.estado, fr.motivo = None, "descartada", f"Se eliminó el gasto #{g.id}"
    db.delete(g)
    return caja_borrada


@router.delete("/{gasto_id}")
def eliminar(gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    caja = borrar_gasto(db, g)
    db.commit()
    return {"ok": True, "mensaje": "Factura eliminada" + (" (y su egreso en el libro de caja)" if caja else "")}


@router.post("/{gasto_id}/revisado")
def marcar_revisado(gasto_id: int, db: Session = Depends(get_db)):
    """Confirma una factura que llegó del portal de proveedores (queda como cualquier otra)."""
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    g.revisado = True
    db.commit()
    return {"ok": True, "mensaje": "Factura revisada"}
