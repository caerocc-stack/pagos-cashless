import re
import json
import hashlib
from decimal import Decimal
from datetime import date

import xlrd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.banco import MovimientoBanco, ExtractoBancario, EncargadoCompra, CONCEPTOS_CONCILIABLES
from app import rendiciones
from app.models.gasto import Gasto
from app.models.proveedor import Proveedor
from app.schemas.banco import BancoMovResponse
from app.auth import requiere_admin
from app.seguridad import auditar
from app import extracto_roela

router = APIRouter(prefix="/api/conciliacion", tags=["Conciliacion"])

TOLERANCIA = Decimal("1.00")  # diferencia de redondeo aceptada entre factura y pago
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _solo_digitos(s) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _parsear_descripcion(desc: str):
    """Extrae el CUIT (11 dígitos) y la razón social del texto del movimiento."""
    desc = (desc or "").strip()
    m = re.search(r"(\d{11})", desc)
    if not m:
        return None, None
    cuit = m.group(1)
    razon = desc[m.end():].strip(" .,-").strip() or None
    return cuit, razon


def _hash_mov(fecha, comprobante, concepto, importe, desc) -> str:
    base = f"{fecha}|{comprobante}|{concepto}|{importe}|{desc}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:40]


def _parsear_extracto_xls(contenido: bytes):
    """Lee el .xls del extracto y devuelve solo los egresos conciliables (190 / F30)."""
    try:
        wb = xlrd.open_workbook(file_contents=contenido)
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo. Subí el PDF del extracto o el .xls del banco.")
    sh = wb.sheet_by_index(0)
    datemode = wb.datemode

    fila_cab = None
    for r in range(min(8, sh.nrows)):
        textos = [str(sh.cell_value(r, c)).strip().lower() for c in range(sh.ncols)]
        if "concepto" in textos and "importe" in textos:
            fila_cab = r
            break
    if fila_cab is None:
        raise HTTPException(400, "El archivo no parece un extracto de cuenta (no encuentro las columnas).")

    cab = {str(sh.cell_value(fila_cab, c)).strip().lower(): c for c in range(sh.ncols)}
    c_fecha, c_comp, c_concepto = cab.get("fecha"), cab.get("comprobante"), cab.get("concepto")
    c_desc = next((c for t, c in cab.items() if t.startswith("descrip")), None)
    c_importe, c_cuenta = cab.get("importe"), cab.get("cuenta")
    if None in (c_fecha, c_concepto, c_desc, c_importe):
        raise HTTPException(400, "Faltan columnas esperadas en el extracto (Fecha/Concepto/Descripción/Importe).")

    movimientos = []
    for r in range(fila_cab + 1, sh.nrows):
        concepto = str(sh.cell_value(r, c_concepto)).strip()
        if concepto not in CONCEPTOS_CONCILIABLES:
            continue
        try:
            importe = Decimal(str(sh.cell_value(r, c_importe)))
        except Exception:
            continue
        if importe >= 0:
            continue
        try:
            fecha = xlrd.xldate.xldate_as_datetime(float(sh.cell_value(r, c_fecha)), datemode).date()
        except Exception:
            continue
        desc = str(sh.cell_value(r, c_desc)).strip()
        comp = str(sh.cell_value(r, c_comp)).strip() if c_comp is not None else ""
        cuit, razon = _parsear_descripcion(desc)
        cuenta = str(sh.cell_value(r, c_cuenta)).strip() if c_cuenta is not None else None
        movimientos.append({
            "fecha": fecha, "cuenta": cuenta, "comprobante": comp or None, "concepto": concepto,
            "categoria": "pago", "descripcion": desc, "cuit": cuit, "razon_social": razon, "importe": importe,
            "hash": _hash_mov(fecha, comp, concepto, importe, desc),
        })
    return movimientos


# ---------------------------------------------------------------- cruce automático

def _facturas_libres(db: Session) -> list[Gasto]:
    """Facturas (importe positivo) que todavía no tienen pago vinculado."""
    usados = {g for (g,) in db.query(MovimientoBanco.gasto_id).filter(MovimientoBanco.gasto_id.isnot(None))}
    return [g for g in db.query(Gasto).filter(Gasto.importe > 0, Gasto.caja_mov_id.is_(None), Gasto.banco_mov_id.is_(None)).all()
            if g.id not in usados]


def _vincular(mov: MovimientoBanco, g: Gasto, manual: bool):
    mov.gasto_id = g.id
    mov.conciliado = True
    mov.conciliado_manual = manual
    g.conciliado = True
    g.forma_pago = "Débito" if mov.concepto == "146" else "Transferencia"
    g.fecha_pago = mov.fecha


_PALABRAS_VACIAS = {"S.A.", "S.R.L.", "SRL", "SA", "SAS", "S.A.S.", "DE", "DEL", "LA", "EL", "LOS", "LAS", "Y",
                    "DEBITO", "DIRECTO", "INTERNET", "SERVICIOS", "GRUPO"}


def _palabras(texto: str | None) -> set[str]:
    return {p for p in re.findall(r"[A-ZÁÉÍÓÚÑ0-9]{4,}", (texto or "").upper()) if p not in _PALABRAS_VACIAS}


def _intentar_match(mov: MovimientoBanco, libres: list[Gasto]) -> bool:
    """Concilia solo si hay UNA factura libre con el mismo importe (±$1) y el mismo CUIT;
    si el banco no informa CUIT (ej. débitos directos), con el nombre del proveedor."""
    if mov.conciliado or mov.sin_factura:
        return False
    objetivo = abs(Decimal(str(mov.importe)))
    mismo_monto = [g for g in libres if abs(abs(Decimal(str(g.importe))) - objetivo) <= TOLERANCIA]
    if mov.cuit:
        cuit = _solo_digitos(mov.cuit)
        cand = [g for g in mismo_monto if _solo_digitos(g.cuit) == cuit]
    else:
        nombre_banco = _palabras(f"{mov.razon_social or ''} {mov.descripcion or ''}")
        cand = [g for g in mismo_monto if nombre_banco & _palabras(g.razon_social)] if nombre_banco else []
    if len(cand) == 1:
        _vincular(mov, cand[0], manual=False)
        libres.remove(cand[0])
        return True
    return False


def _nombre_proveedor(db: Session, cuit: str | None) -> str | None:
    if not cuit:
        return None
    p = db.query(Proveedor).filter(Proveedor.cuit == _solo_digitos(cuit)).first()
    return p.razon_social if p else None


# ---------------------------------------------------------------- importar

@router.post("/importar")
async def importar(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    contenido = await archivo.read()
    nombre = (archivo.filename or "").lower()
    extracto = None
    info = {}
    if nombre.endswith(".pdf") or contenido[:4] == b"%PDF":
        try:
            datos = extracto_roela.leer_pdf(contenido)
        except ValueError as e:
            raise HTTPException(400, str(e))
        desde, hasta = datos["periodo"] or (None, None)
        resumen = extracto_roela.resumen(datos)
        # Si ya se importó este mismo período, se actualiza ese registro (no se duplica)
        extracto = (db.query(ExtractoBancario).filter(ExtractoBancario.desde == desde, ExtractoBancario.hasta == hasta).first()
                    if desde else None) or ExtractoBancario()
        extracto.archivo = archivo.filename
        extracto.desde, extracto.hasta = desde, hasta
        extracto.saldo_inicial, extracto.saldo_final = datos["saldo_inicial"], datos["saldo_final"]
        extracto.cierra = bool(datos["cierra"])
        extracto.movimientos = len(datos["movimientos"])
        extracto.resumen = json.dumps(resumen)
        db.add(extracto)
        db.flush()
        # Solo transferencias, DEBIN y débitos directos se concilian (haberes y pagos automáticos no)
        movimientos = [m for m in datos["movimientos"] if m["categoria"] == "pago"]
        info = {"periodo": [str(desde), str(hasta)] if desde else None, "cierra": extracto.cierra,
                "diferencia": float(datos["diferencia"]) if datos["diferencia"] is not None else None,
                "movimientos_leidos": extracto.movimientos, "resumen": resumen, "extracto_id": extracto.id}
    else:
        movimientos = _parsear_extracto_xls(contenido)

    nuevos, duplicados, nuevos_objs = 0, 0, []
    for m in movimientos:
        if db.query(MovimientoBanco.id).filter(MovimientoBanco.hash == m["hash"]).first():
            duplicados += 1
            continue
        datos_mov = {k: m.get(k) for k in ("fecha", "cuenta", "comprobante", "concepto", "categoria",
                                           "descripcion", "cuit", "razon_social", "importe", "hash")}
        datos_mov["razon_social"] = _nombre_proveedor(db, m.get("cuit")) or m.get("razon_social")
        obj = MovimientoBanco(origen=archivo.filename, extracto_id=extracto.id if extracto else None, **datos_mov)
        if extracto_roela.es_afip(obj.descripcion, obj.cuit):
            obj.sin_factura = "afip"  # impuestos / planes de AFIP: no llevan factura, no quedan pendientes
        db.add(obj)
        nuevos_objs.append(obj)
        nuevos += 1
    db.flush()

    libres = _facturas_libres(db)
    conciliados = sum(1 for obj in nuevos_objs if _intentar_match(obj, libres))
    afip = sum(1 for obj in nuevos_objs if obj.sin_factura == "afip")
    db.commit()
    return {"ok": True, "leidos": len(movimientos), "nuevos": nuevos, "duplicados": duplicados,
            "conciliados_automaticamente": conciliados, "afip": afip,
            "pendientes": nuevos - conciliados - afip, **info}


@router.post("/auto")
def re_conciliar(db: Session = Depends(get_db)):
    """Reintenta conciliar automáticamente los pendientes (útil después de cargar facturas)."""
    pendientes = db.query(MovimientoBanco).filter(MovimientoBanco.conciliado == False,  # noqa: E712
                                                  MovimientoBanco.sin_factura.is_(None)).all()
    libres = _facturas_libres(db)
    for m in pendientes:  # de paso, completar nombres con los proveedores cargados
        m.razon_social = _nombre_proveedor(db, m.cuit) or m.razon_social
    nuevos = sum(1 for m in pendientes if _intentar_match(m, libres))
    db.commit()
    return {"ok": True, "conciliados": nuevos, "pendientes": len(pendientes) - nuevos}


# ---------------------------------------------------------------- extractos importados

def _dto_extracto(e: ExtractoBancario) -> dict:
    return {
        "id": e.id, "banco": e.banco, "archivo": e.archivo,
        "desde": str(e.desde) if e.desde else None, "hasta": str(e.hasta) if e.hasta else None,
        "saldo_inicial": float(e.saldo_inicial) if e.saldo_inicial is not None else None,
        "saldo_final": float(e.saldo_final) if e.saldo_final is not None else None,
        "cierra": e.cierra, "movimientos": e.movimientos,
        "resumen": json.loads(e.resumen or "{}"), "comisiones_gasto_id": e.comisiones_gasto_id,
        "creado": e.created_at.strftime("%Y-%m-%dT%H:%M:%S") if e.created_at else None,
    }


@router.get("/extractos")
def extractos(db: Session = Depends(get_db)):
    return [_dto_extracto(e) for e in db.query(ExtractoBancario).order_by(ExtractoBancario.desde.desc()).all()]


@router.post("/extractos/{ext_id}/registrar-comisiones")
def registrar_comisiones(ext_id: int, db: Session = Depends(get_db)):
    """Registra las comisiones e impuestos bancarios del período como un único gasto (ya pagado por débito)."""
    e = db.get(ExtractoBancario, ext_id)
    if not e:
        raise HTTPException(404, "Extracto no encontrado")
    if e.comisiones_gasto_id and db.get(Gasto, e.comisiones_gasto_id):
        raise HTTPException(409, "Las comisiones de este extracto ya están registradas como gasto.")
    total = abs(Decimal(str(json.loads(e.resumen or "{}").get("comision", {}).get("total", 0))))
    if not total:
        raise HTTPException(400, "Este extracto no tiene comisiones ni impuestos bancarios.")
    periodo = f"{MESES[e.hasta.month - 1]} {e.hasta.year}" if e.hasta else "período"
    g = Gasto(fecha=e.hasta or date.today(), tipo_comprobante="Comprobante", razon_social=e.banco,
              importe=total, concepto=f"Comisiones, IVA e impuesto a los débitos y créditos — {periodo}",
              rubro="Gastos bancarios", categoria="Oficina", forma_pago="Débito",
              fecha_pago=e.hasta, conciliado=True, notas=f"Generado desde el extracto {e.archivo or ''}".strip())
    db.add(g)
    db.flush()
    e.comisiones_gasto_id = g.id
    db.commit()
    return {"ok": True, "mensaje": f"Gasto bancario de {periodo} registrado por ${total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "gasto_id": g.id}


# ---------------------------------------------------------------- eliminar extractos (p. ej. los de prueba)

def _borrar_movimientos(db: Session, movs: list, extractos: list) -> dict:
    """Borra movimientos y extractos. Las facturas conciliadas vuelven a quedar pendientes; los gastos que se
    habían creado DESDE el extracto (pagos sin factura y comisiones bancarias) se borran."""
    from app.routers.gastos import borrar_gasto
    liberadas = borrados = 0
    for e in extractos:
        if e.comisiones_gasto_id:
            g = db.get(Gasto, e.comisiones_gasto_id)
            e.comisiones_gasto_id = None
            db.flush()
            if g:
                borrar_gasto(db, g)
                borrados += 1
    for mov in movs:
        for gr in rendiciones.facturas_de(db, mov):  # rendidas por un encargado con esta transferencia
            rendiciones.desvincular(db, gr)
            liberadas += 1
        g = db.get(Gasto, mov.gasto_id) if mov.gasto_id else None
        mov.gasto_id = None
        db.flush()
        if g:
            if (g.notas or "").startswith("Creado desde el extracto"):
                borrar_gasto(db, g)
                borrados += 1
            else:
                g.conciliado = False
                if not g.caja_mov_id:  # el pago lo marcaba el banco: vuelve a quedar pendiente
                    g.forma_pago, g.fecha_pago = None, None
                liberadas += 1
        db.delete(mov)
    db.flush()
    for e in extractos:
        db.delete(e)
    return {"movimientos": len(movs), "extractos": len(extractos), "facturas_liberadas": liberadas, "gastos_borrados": borrados}


def _mensaje_borrado(r: dict) -> str:
    partes = [f"{r['extractos']} extracto(s) y {r['movimientos']} movimiento(s) eliminados"]
    if r["facturas_liberadas"]:
        partes.append(f"{r['facturas_liberadas']} factura(s) volvieron a quedar sin conciliar")
    if r["gastos_borrados"]:
        partes.append(f"{r['gastos_borrados']} gasto(s) creados desde el extracto se borraron")
    return " · ".join(partes)


@router.delete("/extractos/{ext_id}")
def eliminar_extracto(ext_id: int, request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    e = db.get(ExtractoBancario, ext_id)
    if not e:
        raise HTTPException(404, "Extracto no encontrado")
    movs = db.query(MovimientoBanco).filter(MovimientoBanco.extracto_id == e.id).all()
    nombre = e.archivo or f"#{e.id}"
    r = _borrar_movimientos(db, movs, [e])
    auditar(db, "extracto_eliminado", admin["sub"], f"{nombre}: {r['movimientos']} movimientos", request)
    db.commit()
    return {"ok": True, **r, "mensaje": _mensaje_borrado(r)}


@router.delete("/extractos")
def eliminar_todos_los_extractos(request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    """Deja la conciliación vacía: todos los extractos y todos los movimientos del banco."""
    r = _borrar_movimientos(db, db.query(MovimientoBanco).all(), db.query(ExtractoBancario).all())
    auditar(db, "extractos_eliminados", admin["sub"], f"{r['extractos']} extractos, {r['movimientos']} movimientos", request)
    db.commit()
    return {"ok": True, **r, "mensaje": _mensaje_borrado(r)}


# ---------------------------------------------------------------- listado y acciones

@router.get("/resumen")
def resumen(db: Session = Depends(get_db)):
    total = db.query(func.count(MovimientoBanco.id)).scalar() or 0
    conc = db.query(func.count(MovimientoBanco.id)).filter(MovimientoBanco.conciliado == True).scalar() or 0  # noqa: E712
    monto = func.coalesce(func.sum(func.abs(MovimientoBanco.importe)), 0)
    monto_total = db.query(monto).scalar() or 0
    pend = (MovimientoBanco.conciliado == False, MovimientoBanco.sin_factura.is_(None))  # noqa: E712
    n_pend = db.query(func.count(MovimientoBanco.id)).filter(*pend).scalar() or 0
    monto_pend = db.query(monto).filter(*pend).scalar() or 0
    sf = (MovimientoBanco.sin_factura.isnot(None),)
    return {"total": total, "conciliados": conc, "pendientes": n_pend,
            "monto_total": float(monto_total), "monto_pendiente": float(monto_pend),
            "sin_factura": db.query(func.count(MovimientoBanco.id)).filter(*sf).scalar() or 0,
            "monto_sin_factura": float(db.query(monto).filter(*sf).scalar() or 0)}


@router.get("/")
def listar(estado: str | None = None, q: str | None = None,
           mes: int | None = None, anio: int | None = None,
           db: Session = Depends(get_db)):
    query = db.query(MovimientoBanco).options(joinedload(MovimientoBanco.gasto))
    if estado == "conciliado":
        query = query.filter(MovimientoBanco.conciliado == True)  # noqa: E712
    elif estado == "pendiente":
        query = query.filter(MovimientoBanco.conciliado == False, MovimientoBanco.sin_factura.is_(None))  # noqa: E712
    elif estado == "sin_factura":
        query = query.filter(MovimientoBanco.sin_factura.isnot(None))
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(MovimientoBanco.descripcion.ilike(t), MovimientoBanco.cuit.ilike(t),
                                 MovimientoBanco.razon_social.ilike(t)))
    if anio:
        query = query.filter(extract("year", MovimientoBanco.fecha) == anio)
    if mes:
        query = query.filter(extract("month", MovimientoBanco.fecha) == mes)
    movs = query.order_by(MovimientoBanco.fecha.desc(), MovimientoBanco.id.desc()).all()
    encargados = {e.cuit: e for e in db.query(EncargadoCompra).filter(EncargadoCompra.activo.is_(True)).all() if e.cuit}
    salida = []
    for m in movs:
        d = BancoMovResponse.model_validate(m).model_dump()
        es_rendicion = not m.gasto_id and not m.sin_factura and (m.encargado_id or _solo_digitos(m.cuit) in encargados)
        d["rendicion"] = rendiciones.resumen(db, m) if es_rendicion else None
        salida.append(d)
    return salida


# ---------------------------------------------------------------- compras por un encargado

class EncargadoIn(BaseModel):
    nombre: str
    cuit: str | None = None
    activo: bool = True


def _enc_dto(e: EncargadoCompra) -> dict:
    return {"id": e.id, "nombre": e.nombre, "cuit": e.cuit, "activo": e.activo}


@router.get("/encargados")
def encargados(db: Session = Depends(get_db)):
    return [_enc_dto(e) for e in db.query(EncargadoCompra).order_by(EncargadoCompra.activo.desc(), EncargadoCompra.nombre).all()]


def _validar_encargado(db: Session, data: EncargadoIn, excluir: int | None = None) -> tuple[str, str | None]:
    nombre = re.sub(r"\s+", " ", data.nombre or "").strip()[:120]
    if len(nombre) < 3:
        raise HTTPException(400, "Escribí el nombre del encargado.")
    cuit = _solo_digitos(data.cuit) or None
    if cuit and len(cuit) != 11:
        raise HTTPException(400, "El CUIT/CUIL tiene que tener 11 dígitos.")
    if cuit and db.query(EncargadoCompra).filter(EncargadoCompra.cuit == cuit, EncargadoCompra.id != (excluir or 0)).first():
        raise HTTPException(409, "Ya hay un encargado con ese CUIT/CUIL.")
    return nombre, cuit


@router.post("/encargados")
def crear_encargado(data: EncargadoIn, db: Session = Depends(get_db)):
    nombre, cuit = _validar_encargado(db, data)
    e = EncargadoCompra(nombre=nombre, cuit=cuit, activo=data.activo)
    db.add(e)
    db.commit()
    return _enc_dto(e)


@router.put("/encargados/{enc_id}")
def editar_encargado(enc_id: int, data: EncargadoIn, db: Session = Depends(get_db)):
    e = db.get(EncargadoCompra, enc_id)
    if not e:
        raise HTTPException(404, "Encargado no encontrado")
    e.nombre, e.cuit = _validar_encargado(db, data, enc_id)
    e.activo = data.activo
    db.commit()
    return _enc_dto(e)


@router.delete("/encargados/{enc_id}")
def borrar_encargado(enc_id: int, db: Session = Depends(get_db)):
    e = db.get(EncargadoCompra, enc_id)
    if not e:
        raise HTTPException(404, "Encargado no encontrado")
    if db.query(MovimientoBanco).filter(MovimientoBanco.encargado_id == enc_id).first():
        e.activo = False  # tiene rendiciones: queda inactivo para no perder la historia
        db.commit()
        return {"ok": True, "mensaje": "Tiene rendiciones cargadas: quedó inactivo"}
    db.delete(e)
    db.commit()
    return {"ok": True, "mensaje": "Encargado eliminado"}


def _gasto_mini(g: Gasto) -> dict:
    return {"id": g.id, "fecha": str(g.fecha), "razon_social": g.razon_social, "cuit": g.cuit, "importe": float(g.importe),
            "concepto": g.concepto, "tipo": g.tipo_comprobante, "numero": g.numero, "categoria": g.categoria}


@router.get("/encargados/pendientes")
def rendiciones_pendientes(db: Session = Depends(get_db)):
    """Transferencias a encargados que todavía no se rindieron del todo (para vincular una factura desde Gastos)."""
    salida = []
    for m in (db.query(MovimientoBanco).filter(MovimientoBanco.conciliado.is_(False), MovimientoBanco.gasto_id.is_(None),
                                                MovimientoBanco.sin_factura.is_(None),
                                                MovimientoBanco.importe < 0)
              .order_by(MovimientoBanco.fecha.desc()).all()):
        if not rendiciones.encargado_de(db, m):
            continue
        salida.append({"id": m.id, "fecha": str(m.fecha), "descripcion": m.razon_social or m.descripcion, **rendiciones.resumen(db, m)})
    return salida


@router.get("/{mov_id}/rendicion")
def ver_rendicion(mov_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    libres = sorted(_facturas_libres(db), key=lambda g: abs((g.fecha - mov.fecha).days))
    return {"movimiento": {"id": mov.id, "fecha": str(mov.fecha), "cuit": mov.cuit, "razon_social": mov.razon_social,
                           "descripcion": mov.descripcion, "importe": float(abs(Decimal(str(mov.importe))))},
            **rendiciones.resumen(db, mov),
            "vinculadas": [_gasto_mini(g) for g in rendiciones.facturas_de(db, mov)],
            "disponibles": [_gasto_mini(g) for g in libres[:300]]}


class Rendir(BaseModel):
    encargado_id: int
    gasto_ids: list[int] = []


@router.post("/{mov_id}/rendicion")
def rendir(mov_id: int, data: Rendir, request: Request, db: Session = Depends(get_db)):
    """Vincula facturas (de cualquier proveedor) con una transferencia a un encargado de compras."""
    mov = db.get(MovimientoBanco, mov_id)
    enc = db.get(EncargadoCompra, data.encargado_id)
    if not mov or not enc:
        raise HTTPException(404, "Movimiento o encargado no encontrado")
    if mov.gasto_id:
        raise HTTPException(409, "Este movimiento está conciliado con una factura del proveedor: deshacelo primero.")
    _no_es_sin_factura(mov)
    if Decimal(str(mov.importe)) >= 0:
        raise HTTPException(400, "Solo se rinden transferencias que salieron del banco.")
    libres = {g.id for g in _facturas_libres(db)}
    for gid in data.gasto_ids:
        g = db.get(Gasto, gid)
        if not g or gid not in libres:
            raise HTTPException(409, f"La factura #{gid} ya tiene el pago registrado o no existe.")
        rendiciones.vincular(db, mov, g, enc)
    mov.encargado_id = enc.id
    db.flush()
    rendiciones.actualizar_estado(db, mov)
    if data.gasto_ids:
        auditar(db, "rendicion_encargado", None, f"Transferencia #{mov.id} a {enc.nombre}: {len(data.gasto_ids)} factura(s)", request)
    db.commit()
    return {"ok": True, **rendiciones.resumen(db, mov)}


@router.delete("/{mov_id}/rendicion/{gasto_id}")
def quitar_de_rendicion(mov_id: int, gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g or g.banco_mov_id != mov_id:
        raise HTTPException(404, "Esa factura no está en esta rendición")
    rendiciones.desvincular(db, g)
    db.commit()
    return {"ok": True, **rendiciones.resumen(db, db.get(MovimientoBanco, mov_id))}


class CerrarRendicion(BaseModel):
    cerrar: bool = True
    nota: str | None = None


@router.post("/{mov_id}/rendicion/cerrar")
def cerrar_rendicion(mov_id: int, data: CerrarRendicion, db: Session = Depends(get_db)):
    """Da por rendida la transferencia aunque no cierre el importe (vuelto devuelto, diferencia, etc.)."""
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    nota = (data.nota or "").strip()[:300]
    if data.cerrar and not nota:
        raise HTTPException(400, "Contá por qué se da por rendida (ej.: devolvió el vuelto en efectivo).")
    mov.rendicion_cerrada = data.cerrar
    mov.rendicion_nota = nota if data.cerrar else None
    rendiciones.actualizar_estado(db, mov)
    db.commit()
    return {"ok": True, **rendiciones.resumen(db, mov)}


@router.get("/{mov_id}/candidatos")
def candidatos(mov_id: int, db: Session = Depends(get_db)):
    """Facturas sugeridas para conciliar manualmente este movimiento (mismo CUIT o importe parecido)."""
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    objetivo = abs(Decimal(str(mov.importe)))
    cuit = _solo_digitos(mov.cuit)
    libres = _facturas_libres(db)
    if mov.gasto_id:
        actual = db.get(Gasto, mov.gasto_id)
        if actual:
            libres.append(actual)
    salida = []
    for g in libres:
        mismo_cuit = bool(cuit) and _solo_digitos(g.cuit) == cuit
        dif = abs(abs(Decimal(str(g.importe))) - objetivo)
        mismo_monto = dif <= TOLERANCIA
        if not (mismo_cuit or mismo_monto):
            continue
        salida.append({
            "id": g.id, "fecha": str(g.fecha), "razon_social": g.razon_social, "cuit": g.cuit,
            "importe": float(g.importe), "concepto": g.concepto, "numero": g.numero,
            "coincide_cuit": mismo_cuit, "coincide_monto": mismo_monto, "diferencia": float(dif),
        })
    salida.sort(key=lambda x: (not (x["coincide_cuit"] and x["coincide_monto"]), not x["coincide_monto"], x["diferencia"]))
    return {"facturas": salida, "proveedor": _nombre_proveedor(db, mov.cuit)}


@router.post("/{mov_id}/match/{gasto_id}")
def match_manual(mov_id: int, gasto_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mov_id)
    g = db.get(Gasto, gasto_id)
    if not mov or not g:
        raise HTTPException(404, "Movimiento o factura no encontrados")
    _no_es_sin_factura(mov)
    if mov.gasto_id and mov.gasto_id != gasto_id:
        anterior = db.get(Gasto, mov.gasto_id)
        if anterior:
            anterior.conciliado = False
            anterior.forma_pago = None
            anterior.fecha_pago = None
    _vincular(mov, g, manual=True)
    db.commit()
    return {"ok": True, "mensaje": "Movimiento conciliado con la factura"}


class GastoDesdePago(BaseModel):
    razon_social: str | None = None
    concepto: str | None = None
    rubro: str | None = None
    categoria: str | None = None


@router.post("/{mov_id}/crear-gasto")
def crear_gasto(mov_id: int, data: GastoDesdePago, db: Session = Depends(get_db)):
    """Para pagos sin factura de proveedor (seguros, servicios): crea el gasto
    con los datos del banco y lo deja conciliado con este movimiento."""
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    _no_es_sin_factura(mov)
    if mov.conciliado:
        raise HTTPException(409, "Este movimiento ya está conciliado.")
    cuit = _solo_digitos(mov.cuit) or None
    prov = db.query(Proveedor).filter(Proveedor.cuit == cuit).first() if cuit else None
    tipo = CONCEPTOS_CONCILIABLES.get(mov.concepto or "", "Pago bancario")
    g = Gasto(fecha=mov.fecha, tipo_comprobante="Comprobante", proveedor_id=prov.id if prov else None,
              razon_social=(data.razon_social or (prov.razon_social if prov else None) or mov.razon_social or tipo)[:160],
              cuit=cuit, importe=abs(Decimal(str(mov.importe))),
              concepto=(data.concepto or tipo)[:200], rubro=data.rubro or (prov.rubro if prov else None),
              categoria=data.categoria, notas=f"Creado desde el extracto: {mov.descripcion or ''}"[:400])
    db.add(g)
    db.flush()
    _vincular(mov, g, manual=True)
    db.commit()
    return {"ok": True, "mensaje": "Gasto creado y conciliado con el pago", "gasto_id": g.id}


@router.post("/{mov_id}/unmatch")
def unmatch(mov_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    if mov.gasto_id:
        g = db.get(Gasto, mov.gasto_id)
        if g:
            g.conciliado = False
            g.forma_pago = None
            g.fecha_pago = None
    mov.gasto_id = None
    mov.conciliado = False
    mov.conciliado_manual = False
    db.commit()
    return {"ok": True, "mensaje": "Conciliación deshecha"}


@router.delete("/{mov_id}")
def eliminar(mov_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    if mov.gasto_id:
        g = db.get(Gasto, mov.gasto_id)
        if g:
            g.conciliado = False
    for gr in rendiciones.facturas_de(db, mov):
        rendiciones.desvincular(db, gr)
    db.flush()
    db.delete(mov)
    db.commit()
    return {"ok": True, "mensaje": "Movimiento eliminado"}


# ---------------------------------------------------------------- egresos que no llevan factura (sueldos, AFIP)

# devuelta: transferencia hecha por error y reintegrada a la cuenta (se anota de dónde volvió la plata)
MOTIVOS_SIN_FACTURA = {"sueldo": "sueldo", "afip": "AFIP", "devuelta": "transferencia devuelta"}


def _no_es_sin_factura(mov: MovimientoBanco):
    if mov.sin_factura:
        raise HTTPException(409, f"Este movimiento está marcado como {MOTIVOS_SIN_FACTURA.get(mov.sin_factura, mov.sin_factura)} "
                                 "(no lleva factura). Deshacé esa marca primero.")


class SinFactura(BaseModel):
    motivo: str | None = None  # "sueldo", "afip", "devuelta" o None para volver a dejarlo pendiente
    nota: str | None = None


@router.post("/{mov_id}/sin-factura")
def marcar_sin_factura(mov_id: int, data: SinFactura, request: Request, db: Session = Depends(get_db)):
    """Saca el movimiento de los pendientes: es un sueldo o un pago a AFIP, no un gasto con factura."""
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    motivo = (data.motivo or "").strip().lower() or None
    if motivo and motivo not in MOTIVOS_SIN_FACTURA:
        raise HTTPException(400, "Motivo no válido")
    if motivo:
        if mov.gasto_id or rendiciones.facturas_de(db, mov):
            raise HTTPException(409, "Este movimiento ya tiene facturas vinculadas: quitalas primero.")
        if Decimal(str(mov.importe)) >= 0:
            raise HTTPException(400, "Solo se marcan pagos que salieron del banco.")
        if motivo == "sueldo" and (mov.concepto not in extracto_roela.TRANSFERENCIAS or len(_solo_digitos(mov.cuit)) != 11):
            raise HTTPException(400, "Solo una transferencia o un DEBIN a un CUIT se puede marcar como sueldo.")
        if motivo == "devuelta" and not (data.nota or "").strip():
            raise HTTPException(400, "Anotá cuándo y de quién volvió la plata.")
        mov.rendicion_cerrada, mov.rendicion_nota = False, None
    mov.sin_factura = motivo
    mov.sin_factura_nota = (data.nota or "").strip()[:300] or None if motivo else None
    auditar(db, "banco_sin_factura", None,
            f"Movimiento #{mov.id} ({mov.razon_social or mov.cuit or ''}, ${abs(Decimal(str(mov.importe)))}): "
            + (f"marcado como {MOTIVOS_SIN_FACTURA[motivo]}" if motivo else "vuelve a pendiente"), request)
    db.commit()
    return {"ok": True, "sin_factura": motivo}
