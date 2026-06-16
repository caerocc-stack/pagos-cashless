import re
import hashlib
from decimal import Decimal
from datetime import date

import xlrd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.pago_cuota import PagoCuota
from app.models.alumno import Alumno
from app.models.curso import Curso
from app.models.caja import MovimientoCaja
from app.routers.cursos import curso_de_alumno
from app.schemas.pago_cuota import PagoCuotaResponse
from app.tz import ahora_ar

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


class ImputarEfectivo(BaseModel):
    alumno_id: int
    caja_mov_id: int | None = None
    importe: Decimal | None = None
    fecha: date | None = None


@router.post("/efectivo")
def imputar_efectivo(data: ImputarEfectivo, db: Session = Depends(get_db)):
    """Imputa un pago de cuota en efectivo a un alumno (opcionalmente desde un movimiento de caja)."""
    a = db.get(Alumno, data.alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    importe = data.importe
    fecha = data.fecha
    if data.caja_mov_id:
        # Evitar imputar dos veces el mismo movimiento de caja
        ya = db.query(PagoCuota).filter(PagoCuota.caja_mov_id == data.caja_mov_id).first()
        if ya:
            raise HTTPException(409, "Ese movimiento de caja ya está imputado a una cuota")
        mov = db.get(MovimientoCaja, data.caja_mov_id)
        if not mov:
            raise HTTPException(404, "Movimiento de caja no encontrado")
        importe = importe or Decimal(str(mov.monto))
        fecha = fecha or mov.fecha
    if not importe or not fecha:
        raise HTTPException(400, "Faltan importe y/o fecha del pago")
    importe = abs(Decimal(str(importe)))
    h = hashlib.sha1(f"efectivo|{data.caja_mov_id}|{a.id}|{importe}|{fecha}".encode()).hexdigest()[:40]
    pago = PagoCuota(
        alumno_id=a.id, via="efectivo", canal="Efectivo", caja_mov_id=data.caja_mov_id,
        cliente_siro=None, importe=importe, fecha=fecha, fecha_pago=fecha,
        mes=fecha.month, anio=fecha.year, origen="caja/efectivo", hash=h,
    )
    db.add(pago)
    db.commit()
    return {"ok": True, "mensaje": f"Pago en efectivo imputado a {a.apellido}, {a.nombre}"}


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


# =========================================================
# --- ESTADO DE CUENTA Y ESTADISTICAS ---
# =========================================================
def _nivel(curso: str) -> str:
    m = re.match(r"\s*(\d+)", str(curso or ""))
    return f"{m.group(1)}°" if m else "Otros"


def _estado_de(alumno, curso, total_pagado: Decimal, mes_corte: int) -> dict:
    cond = (alumno.condicion or "").strip().lower()
    deuda_ant = Decimal(str(alumno.deuda_anio_anterior or 0))
    base = {
        "id": alumno.id, "legajo": alumno.legajo,
        "apellido": alumno.apellido, "nombre": alumno.nombre,
        "curso": alumno.curso, "area": alumno.area,
        "division": alumno.division, "nivel": _nivel(alumno.curso),
        "modalidad": alumno.modalidad, "condicion": alumno.condicion,
        "pagado": float(total_pagado), "deuda_anterior": float(deuda_ant),
    }
    if cond in ("becado", "exento"):
        base.update(esperado=0, deuda=0, deuda_total=float(deuda_ant),
                    cuotas_pagas=0, estado=alumno.condicion)
        return base
    if not curso:
        base.update(esperado=0, deuda=0, deuda_total=float(deuda_ant),
                    cuotas_pagas=0, estado="Sin curso")
        return base
    cuota = Decimal(str(curso.cuota or 0))
    matric = Decimal(str(curso.matricula or 0))
    devengadas = min(curso.n_cuotas, max(0, mes_corte - 2))
    esperado = matric + devengadas * cuota
    deuda_corriente = max(Decimal("0"), esperado - total_pagado)
    deuda_total = deuda_corriente + deuda_ant
    cuotas_pagas = int(total_pagado / cuota) if cuota else 0
    if total_pagado <= 0:
        estado = "Sin pagos"
    elif deuda_corriente <= 0:
        estado = "Al día"
    else:
        estado = "Moroso"
    base.update(esperado=float(esperado), deuda=float(deuda_corriente),
                deuda_total=float(deuda_total), cuotas_pagas=cuotas_pagas, estado=estado)
    return base


def _calcular(db: Session, anio: int, mes_corte: int):
    cursos = db.query(Curso).filter(Curso.anio == anio, Curso.activo == True).all()  # noqa: E712
    if not cursos:
        cursos = db.query(Curso).filter(Curso.activo == True).all()  # noqa: E712
    sumas = dict(
        db.query(PagoCuota.alumno_id, func.coalesce(func.sum(PagoCuota.importe), 0))
        .filter(PagoCuota.anio == anio, PagoCuota.alumno_id.isnot(None))
        .group_by(PagoCuota.alumno_id).all()
    )
    salida = []
    for a in db.query(Alumno).filter(Alumno.activo == True).all():  # noqa: E712
        curso = curso_de_alumno(a, cursos)
        total = Decimal(str(sumas.get(a.id, 0)))
        salida.append(_estado_de(a, curso, total, mes_corte))
    return salida


@router.get("/estado")
def estado(anio: int | None = None, mes: int | None = None,
           area: str | None = None, curso: str | None = None,
           estado: str | None = None, q: str | None = None,
           db: Session = Depends(get_db)):
    """Estado de cuenta de todos los alumnos (para consulta y morosos)."""
    anio = anio or ahora_ar().year
    mes_corte = mes or ahora_ar().month
    filas = _calcular(db, anio, mes_corte)
    if area:
        filas = [f for f in filas if (f["area"] or "") == area]
    if curso:
        filas = [f for f in filas if (f["curso"] or "") == curso]
    if estado:
        filas = [f for f in filas if f["estado"] == estado]
    if q:
        t = q.strip().lower()
        filas = [f for f in filas if t in f"{f['apellido']} {f['nombre']} {f['legajo']}".lower()]
    filas.sort(key=lambda f: (-f["deuda_total"], f["apellido"]))
    return {"anio": anio, "mes_corte": mes_corte, "alumnos": filas}


@router.get("/estado/{alumno_id}")
def estado_alumno(alumno_id: int, anio: int | None = None, db: Session = Depends(get_db)):
    a = db.get(Alumno, alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    anio = anio or ahora_ar().year
    mes_corte = ahora_ar().month
    cursos = db.query(Curso).filter(Curso.activo == True).all()  # noqa: E712
    curso = curso_de_alumno(a, cursos)
    pagos = db.query(PagoCuota).filter(
        PagoCuota.alumno_id == alumno_id, PagoCuota.anio == anio
    ).order_by(PagoCuota.fecha).all()
    total = sum((Decimal(str(p.importe)) for p in pagos), Decimal("0"))
    info = _estado_de(a, curso, total, mes_corte)
    info["curso_param"] = {
        "nombre": curso.nombre, "cuota": float(curso.cuota), "n_cuotas": curso.n_cuotas,
        "matricula": float(curso.matricula),
    } if curso else None
    info["pagos"] = [
        {"fecha": str(p.fecha), "mes": p.mes, "importe": float(p.importe),
         "canal": p.canal, "via": p.via}
        for p in pagos
    ]
    return info


@router.get("/estadisticas")
def estadisticas(anio: int | None = None, mes: int | None = None, db: Session = Depends(get_db)):
    anio = anio or ahora_ar().year
    mes_corte = mes or ahora_ar().month
    filas = _calcular(db, anio, mes_corte)

    def agrupar(clave):
        g = {}
        for f in filas:
            k = f.get(clave) or "—"
            d = g.setdefault(k, {"clave": k, "alumnos": 0, "esperado": 0.0, "cobrado": 0.0,
                                 "deuda": 0.0, "al_dia": 0, "morosos": 0, "sin_pagos": 0})
            d["alumnos"] += 1
            d["esperado"] += f["esperado"]
            d["cobrado"] += f["pagado"]
            d["deuda"] += f["deuda_total"]
            if f["estado"] == "Al día":
                d["al_dia"] += 1
            elif f["estado"] == "Moroso":
                d["morosos"] += 1
            elif f["estado"] == "Sin pagos":
                d["sin_pagos"] += 1
        for d in g.values():
            d["cumplimiento"] = round(d["cobrado"] / d["esperado"] * 100, 1) if d["esperado"] else 0
        return sorted(g.values(), key=lambda x: str(x["clave"]))

    estados = {}
    for f in filas:
        estados[f["estado"]] = estados.get(f["estado"], 0) + 1

    # Cobranza mensual del año
    mensual = dict(
        db.query(PagoCuota.mes, func.coalesce(func.sum(PagoCuota.importe), 0))
        .filter(PagoCuota.anio == anio).group_by(PagoCuota.mes).all()
    )
    meses = [{"mes": m, "cobrado": float(mensual.get(m, 0))} for m in range(1, 13)]

    morosos = sorted([f for f in filas if f["deuda_total"] > 0], key=lambda f: -f["deuda_total"])[:15]

    tot_esp = sum(f["esperado"] for f in filas)
    tot_cob = sum(f["pagado"] for f in filas)
    return {
        "anio": anio, "mes_corte": mes_corte,
        "kpis": {
            "alumnos": len(filas),
            "esperado": tot_esp, "cobrado": tot_cob, "deuda": sum(f["deuda_total"] for f in filas),
            "cumplimiento": round(tot_cob / tot_esp * 100, 1) if tot_esp else 0,
        },
        "por_estado": estados,
        "por_area": agrupar("area"),
        "por_nivel": agrupar("nivel"),
        "por_division": agrupar("division"),
        "por_modalidad": agrupar("modalidad"),
        "cobranza_mensual": meses,
        "top_morosos": morosos,
    }
