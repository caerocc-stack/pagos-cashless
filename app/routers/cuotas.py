import hashlib
from decimal import Decimal

import xlrd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.pago_cuota import PagoCuota
from app.models.alumno import Alumno
from app.schemas.pago_cuota import PagoCuotaResponse

router = APIRouter(prefix="/api/cuotas", tags=["Cuotas"])


def _dig(x):
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return "".join(ch for ch in str(x) if ch.isdigit()) if x is not None else ""


def _indices(db: Session):
    """Construye indices del padron: por legajo (5 dig) y por DNI (ult 8)."""
    by_leg, by_dni = {}, {}
    for a in db.query(Alumno).all():
        leg = _dig(a.legajo)
        if leg:
            by_leg.setdefault(leg[-5:], a)
        d = _dig(a.dni)
        if len(d) >= 7:  # DNI real (los placeholders 'SL...' quedan afuera)
            by_dni.setdefault(d[-8:], a)
    return by_leg, by_dni


def _matchear(cliente, by_leg, by_dni):
    c = _dig(cliente)
    if not c:
        return None, None
    a = by_leg.get(c[-5:])
    if a:
        return a, "legajo"
    a = by_dni.get(c[-8:])
    if a:
        return a, "dni"
    return None, None


def reasignar_pendientes(db: Session) -> int:
    """Reasigna los pagos sin alumno a los que ahora existan en el padron. Devuelve cuantos asigno."""
    by_leg, by_dni = _indices(db)
    n = 0
    for p in db.query(PagoCuota).filter(PagoCuota.alumno_id.is_(None)).all():
        a, via = _matchear(p.cliente_siro, by_leg, by_dni)
        if a:
            p.alumno_id = a.id
            p.via = via
            n += 1
    if n:
        db.commit()
    return n


def _parsear_siro(contenido: bytes):
    try:
        wb = xlrd.open_workbook(file_contents=contenido)
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo. Tiene que ser el .xls del listado de cobranzas SIRO.")
    sh = wb.sheet_by_index(0)
    dm = wb.datemode

    fila_cab = None
    for r in range(min(6, sh.nrows)):
        textos = [str(sh.cell_value(r, c)).strip().lower() for c in range(sh.ncols)]
        if "cliente" in textos and "importe" in textos:
            fila_cab = r
            break
    if fila_cab is None:
        raise HTTPException(400, "El archivo no parece un listado de cobranzas SIRO (no encuentro las columnas).")

    cab = {str(sh.cell_value(fila_cab, c)).strip().lower(): c for c in range(sh.ncols)}
    c_cli = cab.get("cliente")
    c_imp = cab.get("importe")
    c_proc = next((c for t, c in cab.items() if "proceso" in t), None)
    c_pago = next((c for t, c in cab.items() if t == "fecha de pago"), None)
    c_canal = cab.get("canal")
    if None in (c_cli, c_imp, c_proc):
        raise HTTPException(400, "Faltan columnas (Cliente / Importe / Fecha de Proceso).")

    pagos = []
    for r in range(fila_cab + 1, sh.nrows):
        cliente = str(sh.cell_value(r, c_cli)).strip()
        if not _dig(cliente):
            continue
        try:
            importe = Decimal(str(sh.cell_value(r, c_imp)))
        except Exception:
            continue
        if importe == 0:
            continue
        bruto_proc = sh.cell_value(r, c_proc)
        try:
            fecha = xlrd.xldate.xldate_as_datetime(float(bruto_proc), dm).date()
        except Exception:
            continue
        fecha_pago = None
        bruto_pago = sh.cell_value(r, c_pago) if c_pago is not None else None
        try:
            if bruto_pago:
                fecha_pago = xlrd.xldate.xldate_as_datetime(float(bruto_pago), dm).date()
        except Exception:
            pass
        canal = str(sh.cell_value(r, c_canal)).strip() if c_canal is not None else None
        h = hashlib.sha1(f"{cliente}|{importe}|{bruto_proc}|{bruto_pago}".encode()).hexdigest()[:40]
        pagos.append({
            "cliente_siro": _dig(cliente), "importe": importe, "fecha": fecha,
            "fecha_pago": fecha_pago, "canal": canal or None,
            "mes": fecha.month, "anio": fecha.year, "hash": h,
        })
    return pagos


@router.post("/importar")
async def importar(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    contenido = await archivo.read()
    pagos = _parsear_siro(contenido)
    by_leg, by_dni = _indices(db)

    nuevos = duplicados = asignados = 0
    for p in pagos:
        if db.query(PagoCuota).filter(PagoCuota.hash == p["hash"]).first():
            duplicados += 1
            continue
        a, via = _matchear(p["cliente_siro"], by_leg, by_dni)
        obj = PagoCuota(origen=archivo.filename, alumno_id=(a.id if a else None), via=via, **p)
        db.add(obj)
        nuevos += 1
        if a:
            asignados += 1
    db.commit()
    return {
        "ok": True, "leidos": len(pagos), "nuevos": nuevos, "duplicados": duplicados,
        "asignados": asignados, "sin_asignar": nuevos - asignados,
    }


@router.post("/reasignar")
def reasignar(db: Session = Depends(get_db)):
    n = reasignar_pendientes(db)
    pend = db.query(func.count(PagoCuota.id)).filter(PagoCuota.alumno_id.is_(None)).scalar()
    return {"ok": True, "asignados": n, "sin_asignar": pend}


@router.get("/resumen")
def resumen(mes: int | None = None, anio: int | None = None, db: Session = Depends(get_db)):
    q = db.query(PagoCuota)
    if anio:
        q = q.filter(PagoCuota.anio == anio)
    if mes:
        q = q.filter(PagoCuota.mes == mes)
    total = q.count()
    asign = q.filter(PagoCuota.alumno_id.isnot(None)).count()
    monto = q.with_entities(func.coalesce(func.sum(PagoCuota.importe), 0)).scalar() or 0
    monto_sin = q.filter(PagoCuota.alumno_id.is_(None)).with_entities(
        func.coalesce(func.sum(PagoCuota.importe), 0)).scalar() or 0
    return {
        "total": total, "asignados": asign, "sin_asignar": total - asign,
        "monto_total": float(monto), "monto_sin_asignar": float(monto_sin),
    }


@router.get("/", response_model=list[PagoCuotaResponse])
def listar(estado: str | None = None, q: str | None = None,
           mes: int | None = None, anio: int | None = None,
           db: Session = Depends(get_db)):
    query = db.query(PagoCuota).options(joinedload(PagoCuota.alumno))
    if estado == "asignado":
        query = query.filter(PagoCuota.alumno_id.isnot(None))
    elif estado == "sin_asignar":
        query = query.filter(PagoCuota.alumno_id.is_(None))
    if anio:
        query = query.filter(PagoCuota.anio == anio)
    if mes:
        query = query.filter(PagoCuota.mes == mes)
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(PagoCuota.cliente_siro.ilike(t)))
    return query.order_by(PagoCuota.fecha.desc(), PagoCuota.id.desc()).limit(1000).all()


@router.post("/{pago_id}/asignar/{alumno_id}")
def asignar_manual(pago_id: int, alumno_id: int, db: Session = Depends(get_db)):
    p = db.get(PagoCuota, pago_id)
    a = db.get(Alumno, alumno_id)
    if not p or not a:
        raise HTTPException(404, "Pago o alumno no encontrado")
    p.alumno_id = a.id
    p.via = "manual"
    db.commit()
    return {"ok": True, "mensaje": f"Pago asignado a {a.apellido}, {a.nombre}"}


@router.delete("/{pago_id}")
def eliminar(pago_id: int, db: Session = Depends(get_db)):
    p = db.get(PagoCuota, pago_id)
    if not p:
        raise HTTPException(404, "Pago no encontrado")
    db.delete(p)
    db.commit()
    return {"ok": True, "mensaje": "Pago eliminado"}
