import re
import hashlib
from decimal import Decimal
from datetime import date

import xlrd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.banco import MovimientoBanco, CONCEPTOS_CONCILIABLES
from app.models.gasto import Gasto
from app.schemas.banco import BancoMovResponse

router = APIRouter(prefix="/api/conciliacion", tags=["Conciliacion"])


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


def _parsear_extracto(contenido: bytes):
    """Lee el .xls del extracto y devuelve solo los egresos conciliables (190 / F30)."""
    try:
        wb = xlrd.open_workbook(file_contents=contenido)
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo. Tiene que ser el .xls del extracto de cuenta.")
    sh = wb.sheet_by_index(0)
    datemode = wb.datemode

    # Ubicar la fila de encabezados (la que contiene 'Concepto' e 'Importe')
    fila_cab = None
    for r in range(min(8, sh.nrows)):
        textos = [str(sh.cell_value(r, c)).strip().lower() for c in range(sh.ncols)]
        if "concepto" in textos and "importe" in textos:
            fila_cab = r
            break
    if fila_cab is None:
        raise HTTPException(400, "El archivo no parece un extracto de cuenta (no encuentro las columnas).")

    cab = {str(sh.cell_value(fila_cab, c)).strip().lower(): c for c in range(sh.ncols)}
    c_fecha = cab.get("fecha")
    c_comp = cab.get("comprobante")
    c_concepto = cab.get("concepto")
    c_desc = next((c for t, c in cab.items() if t.startswith("descrip")), None)
    c_importe = cab.get("importe")
    c_cuenta = cab.get("cuenta")
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
        if importe >= 0:  # solo egresos (pagos), no créditos
            continue
        # Fecha (serial de Excel)
        bruto = sh.cell_value(r, c_fecha)
        try:
            fdt = xlrd.xldate.xldate_as_datetime(float(bruto), datemode)
            fecha = fdt.date()
        except Exception:
            continue
        desc = str(sh.cell_value(r, c_desc)).strip()
        comp = str(sh.cell_value(r, c_comp)).strip() if c_comp is not None else ""
        cuit, razon = _parsear_descripcion(desc)
        cuenta = str(sh.cell_value(r, c_cuenta)).strip() if c_cuenta is not None else None
        movimientos.append({
            "fecha": fecha, "cuenta": cuenta, "comprobante": comp or None,
            "concepto": concepto, "descripcion": desc, "cuit": cuit,
            "razon_social": razon, "importe": importe,
            "hash": _hash_mov(fecha, comp, concepto, importe, desc),
        })
    return movimientos


def _intentar_match(mov: MovimientoBanco, db: Session) -> bool:
    """Busca una factura no conciliada con el mismo CUIT e importe. Si hay 1 sola, la vincula."""
    if mov.conciliado or not mov.cuit:
        return False
    objetivo = abs(mov.importe)
    # Facturas (positivas) con ese CUIT que aún no están conciliadas con otro movimiento
    candidatos = [
        g for g in db.query(Gasto).filter(Gasto.importe > 0).all()
        if _solo_digitos(g.cuit) == _solo_digitos(mov.cuit)
        and abs(Decimal(str(g.importe))) == objetivo
        and not db.query(MovimientoBanco).filter(
            MovimientoBanco.gasto_id == g.id, MovimientoBanco.id != mov.id
        ).first()
    ]
    if len(candidatos) == 1:
        g = candidatos[0]
        mov.gasto_id = g.id
        mov.conciliado = True
        mov.conciliado_manual = False
        g.conciliado = True
        return True
    return False


@router.post("/importar")
async def importar(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    contenido = await archivo.read()
    movimientos = _parsear_extracto(contenido)

    nuevos = 0
    duplicados = 0
    nuevos_objs = []
    for m in movimientos:
        if db.query(MovimientoBanco).filter(MovimientoBanco.hash == m["hash"]).first():
            duplicados += 1
            continue
        obj = MovimientoBanco(origen=archivo.filename, **m)
        db.add(obj)
        nuevos_objs.append(obj)
        nuevos += 1
    db.flush()

    # Auto-conciliar los nuevos
    conciliados = 0
    for obj in nuevos_objs:
        if _intentar_match(obj, db):
            conciliados += 1
    db.commit()

    return {
        "ok": True,
        "leidos": len(movimientos),
        "nuevos": nuevos,
        "duplicados": duplicados,
        "conciliados_automaticamente": conciliados,
        "pendientes": nuevos - conciliados,
    }


@router.post("/auto")
def re_conciliar(db: Session = Depends(get_db)):
    """Reintenta conciliar automáticamente los movimientos pendientes (útil tras cargar facturas)."""
    pendientes = db.query(MovimientoBanco).filter(MovimientoBanco.conciliado == False).all()  # noqa: E712
    nuevos = sum(1 for m in pendientes if _intentar_match(m, db))
    db.commit()
    return {"ok": True, "conciliados": nuevos, "pendientes": len(pendientes) - nuevos}


@router.get("/resumen")
def resumen(db: Session = Depends(get_db)):
    total = db.query(func.count(MovimientoBanco.id)).scalar() or 0
    conc = db.query(func.count(MovimientoBanco.id)).filter(MovimientoBanco.conciliado == True).scalar() or 0  # noqa: E712
    monto_total = db.query(func.coalesce(func.sum(func.abs(MovimientoBanco.importe)), 0)).scalar() or 0
    monto_pend = db.query(func.coalesce(func.sum(func.abs(MovimientoBanco.importe)), 0)).filter(
        MovimientoBanco.conciliado == False).scalar() or 0  # noqa: E712
    return {
        "total": total,
        "conciliados": conc,
        "pendientes": total - conc,
        "monto_total": float(monto_total),
        "monto_pendiente": float(monto_pend),
    }


@router.get("/", response_model=list[BancoMovResponse])
def listar(estado: str | None = None, q: str | None = None,
           mes: int | None = None, anio: int | None = None,
           db: Session = Depends(get_db)):
    query = db.query(MovimientoBanco).options(joinedload(MovimientoBanco.gasto))
    if estado == "conciliado":
        query = query.filter(MovimientoBanco.conciliado == True)  # noqa: E712
    elif estado == "pendiente":
        query = query.filter(MovimientoBanco.conciliado == False)  # noqa: E712
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(
            MovimientoBanco.descripcion.ilike(t),
            MovimientoBanco.cuit.ilike(t),
            MovimientoBanco.razon_social.ilike(t),
        ))
    if anio:
        query = query.filter(extract("year", MovimientoBanco.fecha) == anio)
    if mes:
        query = query.filter(extract("month", MovimientoBanco.fecha) == mes)
    return query.order_by(MovimientoBanco.fecha.desc(), MovimientoBanco.id.desc()).all()


@router.get("/{mov_id}/candidatos")
def candidatos(mov_id: int, db: Session = Depends(get_db)):
    """Facturas sugeridas para conciliar manualmente este movimiento."""
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    objetivo = abs(mov.importe)
    cuit = _solo_digitos(mov.cuit)
    usados = {b.gasto_id for b in db.query(MovimientoBanco).filter(MovimientoBanco.gasto_id.isnot(None)).all()}
    salida = []
    for g in db.query(Gasto).filter(Gasto.importe > 0).all():
        if g.id in usados and g.id != mov.gasto_id:
            continue
        mismo_cuit = cuit and _solo_digitos(g.cuit) == cuit
        mismo_monto = abs(Decimal(str(g.importe))) == objetivo
        if not (mismo_cuit or mismo_monto):
            continue
        salida.append({
            "id": g.id, "fecha": str(g.fecha), "razon_social": g.razon_social,
            "cuit": g.cuit, "importe": float(g.importe), "concepto": g.concepto,
            "numero": g.numero, "coincide_cuit": bool(mismo_cuit), "coincide_monto": mismo_monto,
        })
    # Primero los que coinciden en CUIT y monto
    salida.sort(key=lambda x: (x["coincide_cuit"] and x["coincide_monto"]), reverse=True)
    return salida


@router.post("/{mov_id}/match/{gasto_id}")
def match_manual(mov_id: int, gasto_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Factura no encontrada")
    # Liberar el gasto anterior de este movimiento, si tenía
    if mov.gasto_id and mov.gasto_id != gasto_id:
        anterior = db.get(Gasto, mov.gasto_id)
        if anterior:
            anterior.conciliado = False
    mov.gasto_id = g.id
    mov.conciliado = True
    mov.conciliado_manual = True
    g.conciliado = True
    db.commit()
    return {"ok": True, "mensaje": "Movimiento conciliado con la factura"}


@router.post("/{mov_id}/unmatch")
def unmatch(mov_id: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mov_id)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    if mov.gasto_id:
        g = db.get(Gasto, mov.gasto_id)
        if g:
            g.conciliado = False
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
    db.delete(mov)
    db.commit()
    return {"ok": True, "mensaje": "Movimiento eliminado"}
