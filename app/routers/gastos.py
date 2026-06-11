from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.gasto import Gasto, CATEGORIAS, FORMAS_PAGO, TIPOS_COMPROBANTE
from app.models.proveedor import Proveedor
from app.models.caja import MovimientoCaja
from app.models.banco import MovimientoBanco
from app.schemas.gasto import GastoCreate, GastoUpdate, GastoResponse
from app.storage_util import subir_comprobante, storage_configurado
from app.tz import ahora_ar

router = APIRouter(prefix="/api/gastos", tags=["Gastos"])


def _norm_cuit(cuit) -> str:
    return "".join(ch for ch in str(cuit or "") if ch.isdigit())


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
    db: Session = Depends(get_db),
):
    query = db.query(Gasto)
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
    return {
        "total": float(total),
        "cantidad": cantidad,
        "por_categoria": [
            {"categoria": c or "Sin categoría", "total": float(t), "cantidad": n}
            for c, t, n in por_cat
        ],
    }


@router.get("/{gasto_id}", response_model=GastoResponse)
def obtener(gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    return g


@router.post("/", response_model=GastoResponse, status_code=201)
def crear(data: GastoCreate, db: Session = Depends(get_db)):
    d = data.model_dump()
    cuit = _norm_cuit(d.get("cuit"))
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
    db.commit()
    db.refresh(g)
    return g


@router.put("/{gasto_id}", response_model=GastoResponse)
def actualizar(gasto_id: int, data: GastoUpdate, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    cambios = _completar_proveedor(data.model_dump(exclude_unset=True), db)
    for campo, valor in cambios.items():
        setattr(g, campo, valor)
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

    bancos = []
    for b in db.query(MovimientoBanco).filter(MovimientoBanco.conciliado == False).all():  # noqa: E712
        coincide_monto = abs(Decimal(str(b.importe))) == objetivo
        coincide_cuit = bool(cuit) and _norm_cuit(b.cuit) == cuit
        if coincide_monto or coincide_cuit:
            bancos.append({
                "id": b.id, "fecha": str(b.fecha), "descripcion": b.descripcion,
                "cuit": b.cuit, "razon_social": b.razon_social,
                "importe": float(abs(b.importe)),
                "coincide_monto": coincide_monto, "coincide_cuit": coincide_cuit,
            })

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


@router.post("/{gasto_id}/pago/banco/{banco_id}")
def pago_banco(gasto_id: int, banco_id: int, db: Session = Depends(get_db)):
    """Vincula el gasto a un movimiento del banco (= conciliar). Forma de pago: Transferencia."""
    g = db.get(Gasto, gasto_id)
    b = db.get(MovimientoBanco, banco_id)
    if not g or not b:
        raise HTTPException(404, "Gasto o movimiento no encontrado")
    b.gasto_id = g.id
    b.conciliado = True
    b.conciliado_manual = True
    g.conciliado = True
    g.forma_pago = "Transferencia"
    g.fecha_pago = b.fecha
    g.caja_mov_id = None
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


@router.post("/{gasto_id}/pago/efectivo-nuevo")
def pago_efectivo_nuevo(gasto_id: int, db: Session = Depends(get_db)):
    """Registra un egreso de caja por el importe del gasto y lo vincula como pago en efectivo."""
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    c = MovimientoCaja(
        fecha=g.fecha or ahora_ar().date(),
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
    for b in db.query(MovimientoBanco).filter(MovimientoBanco.gasto_id == g.id).all():
        b.gasto_id = None
        b.conciliado = False
        b.conciliado_manual = False
    g.conciliado = False
    g.caja_mov_id = None
    g.forma_pago = None
    g.fecha_pago = None
    db.commit()
    return {"ok": True, "mensaje": "Pago desvinculado"}


@router.delete("/{gasto_id}")
def eliminar(gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    db.delete(g)
    db.commit()
    return {"ok": True, "mensaje": "Gasto eliminado"}
