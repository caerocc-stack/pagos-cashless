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
from app.models.curso import Curso, AlumnoCurso
from app.models.caja import MovimientoCaja
from app.routers.cursos import curso_de_alumno
from app.schemas.pago_cuota import PagoCuotaResponse
from app.tz import ahora_ar
from app.cuenta_alumno import estado_cuenta, anio_de_pago, plan_simple, MES_INICIO

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
        if leg and str(a.legajo).strip().isdigit():  # "D<dni>" = sin legajo: no se busca por legajo
            by_leg.setdefault(leg[-5:], a)
        d = _dig(a.dni)
        if len(d) >= 7:  # DNI real (los placeholders 'SL...' quedan afuera)
            by_dni.setdefault(d[-8:].zfill(8), a)
    return by_leg, by_dni


def _matchear(cliente, by_leg, by_dni):
    """Cliente SIRO = 1 dígito de concepto + 8 dígitos: el DNI, o "000" + legajo.
    Si los 8 dígitos no empiezan con 000 es un DNI: se busca primero por DNI para no confundirlo
    con un legajo que coincida con sus últimos 5 dígitos."""
    c = _dig(cliente)
    if not c:
        return None, None
    if len(c) >= 8 and not c[-8:].startswith("000"):
        a = by_dni.get(c[-8:].zfill(8))
        if a:
            return a, "dni"
    a = by_leg.get(c[-5:])
    if a:
        return a, "legajo"
    a = by_dni.get(c[-8:].zfill(8))
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


def _base_alumno(alumno) -> dict:
    return {"id": alumno.id, "legajo": alumno.legajo, "apellido": alumno.apellido, "nombre": alumno.nombre,
            "curso": alumno.curso, "area": alumno.area, "division": alumno.division, "nivel": _nivel(alumno.curso),
            "modalidad": alumno.modalidad, "condicion": alumno.condicion}


def _estado_de(alumno, planes, pagos, anio: int, mes_corte: int | None = None, detalle: bool = False) -> dict:
    """Estado de cuenta cuota por cuota (ver app/cuenta_alumno.py). Sin `detalle` devuelve solo el resumen."""
    info = estado_cuenta(alumno, planes, pagos, anio, hoy=ahora_ar().date(), mes_corte=mes_corte)
    if not detalle:
        for k in ("items", "pagos", "proximo"):
            info.pop(k, None)
        for c in info.get("cursos", []):
            c.pop("items", None)
    info["cursos_nombres"] = [c["nombre"] for c in info.get("cursos", [])]
    return {**_base_alumno(alumno), **info}


def planes_de(alumno, cursos: list[Curso], extras: list[AlumnoCurso]) -> list[dict]:
    """Cursos del alumno en el año: los cargados explícitamente (si cursa más de uno) o el de su padrón."""
    if extras:
        por_id = {c.id: c for c in cursos}
        planes = [{"clave": f"ac{x.id}", "curso": por_id[x.curso_id], "nombre": por_id[x.curso_id].nombre,
                   "mes_inicio": x.mes_inicio or por_id[x.curso_id].mes_inicio or MES_INICIO, "principal": bool(x.principal), "curso_id": x.curso_id,
                   "alumno_curso_id": x.id}
                  for x in sorted(extras, key=lambda x: (not x.principal, x.mes_inicio or MES_INICIO, x.id)) if x.curso_id in por_id]
        if planes:
            return planes
    return plan_simple(curso_de_alumno(alumno, cursos))


def cursos_vigentes(db: Session, anio: int) -> list[Curso]:
    cursos = db.query(Curso).filter(Curso.anio == anio, Curso.activo == True).all()  # noqa: E712
    return cursos or db.query(Curso).filter(Curso.activo == True).all()  # noqa: E712


def extras_por_alumno(db: Session, anio: int, alumno_id: int | None = None) -> dict[int, list[AlumnoCurso]]:
    q = db.query(AlumnoCurso).filter(AlumnoCurso.anio == anio)
    if alumno_id:
        q = q.filter(AlumnoCurso.alumno_id == alumno_id)
    salida: dict[int, list[AlumnoCurso]] = {}
    for x in q.all():
        salida.setdefault(x.alumno_id, []).append(x)
    return salida


def planes_alumno(db: Session, a: Alumno, anio: int) -> list[dict]:
    return planes_de(a, cursos_vigentes(db, anio), extras_por_alumno(db, anio, a.id).get(a.id, []))


def pagos_del_anio(db: Session, anio: int, alumno_id: int | None = None) -> dict[int, list]:
    """Pagos imputables al año (por fecha de pago: un pago del 30/12 acreditado en enero es del año anterior)."""
    q = db.query(PagoCuota).filter(PagoCuota.alumno_id.isnot(None),
                                   PagoCuota.fecha >= date(anio - 1, 12, 1), PagoCuota.fecha <= date(anio + 1, 1, 31))
    if alumno_id:
        q = q.filter(PagoCuota.alumno_id == alumno_id)
    por_alumno: dict[int, list] = {}
    for p in q.all():
        if anio_de_pago(p) == anio:
            por_alumno.setdefault(p.alumno_id, []).append(p)
    return por_alumno


def _corte_texto(mes_corte: int | None) -> int:
    """Último mes con la cuota ya vencida (las cuotas vencen el último día de cada mes)."""
    return mes_corte if mes_corte else max(0, ahora_ar().month - 1)


def _calcular(db: Session, anio: int, mes_corte: int | None):
    cursos = cursos_vigentes(db, anio)
    pagos = pagos_del_anio(db, anio)
    extras = extras_por_alumno(db, anio)
    return [_estado_de(a, planes_de(a, cursos, extras.get(a.id, [])), pagos.get(a.id, []), anio, mes_corte)
            for a in db.query(Alumno).filter(Alumno.activo == True).all()]  # noqa: E712


@router.get("/estado")
def estado(anio: int | None = None, mes: int | None = None,
           area: str | None = None, curso: str | None = None,
           estado: str | None = None, q: str | None = None,
           db: Session = Depends(get_db)):
    """Estado de cuenta de todos los alumnos (para consulta y morosos)."""
    anio = anio or ahora_ar().year
    filas = _calcular(db, anio, mes)
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
    return {"anio": anio, "mes_corte": _corte_texto(mes), "alumnos": filas}


def detalle_alumno(db: Session, a: Alumno, anio: int | None = None) -> dict:
    """Estado de cuenta completo de un alumno: cuotas, imputación de cada pago y próximo vencimiento."""
    anio = anio or ahora_ar().year
    planes = planes_alumno(db, a, anio)
    info = _estado_de(a, planes, pagos_del_anio(db, anio, a.id).get(a.id, []), anio, detalle=True)
    curso = planes[0]["curso"] if planes else None
    info["curso_param"] = {"nombre": curso.nombre, "cuota": float(curso.cuota), "n_cuotas": curso.n_cuotas,
                           "matricula": float(curso.matricula or 0)} if curso else None
    return info


@router.get("/estado/{alumno_id}")
def estado_alumno(alumno_id: int, anio: int | None = None, db: Session = Depends(get_db)):
    a = db.get(Alumno, alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    return detalle_alumno(db, a, anio)


@router.get("/estadisticas")
def estadisticas(anio: int | None = None, mes: int | None = None, db: Session = Depends(get_db)):
    anio = anio or ahora_ar().year
    mes_corte = _corte_texto(mes)
    filas = _calcular(db, anio, mes)

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


class Imputacion(BaseModel):
    curso_id: int | None = None


@router.post("/pagos/{pago_id}/imputar")
def imputar_pago(pago_id: int, data: Imputacion, db: Session = Depends(get_db)):
    """Imputa a mano un pago a uno de los cursos del alumno (o lo deja en automático con curso_id null)."""
    p = db.get(PagoCuota, pago_id)
    if not p or not p.alumno_id:
        raise HTTPException(404, "Pago no encontrado")
    if data.curso_id is not None and not db.query(AlumnoCurso).filter(
            AlumnoCurso.alumno_id == p.alumno_id, AlumnoCurso.curso_id == data.curso_id).first():
        raise HTTPException(400, "Ese curso no está asignado al alumno")
    p.curso_id = data.curso_id
    db.commit()
    return {"ok": True, "mensaje": "Imputación actualizada"}
