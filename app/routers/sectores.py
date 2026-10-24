"""
Cuenta corriente de cada sector del colegio: lo cobrado en cuotas de sus cursos menos lo gastado en
facturas destinadas a ese sector (gasto.sector).

- Ingresos: pagos de cuotas (por fecha de proceso) de los cursos del sector. Cada pago se atribuye a uno
  de los cursos del alumno con el mismo criterio que su estado de cuenta (exámenes, imputación a mano,
  importe de la cuota). Los cursos por examen se agrupan por instancia; el resto, por mes.
- Egresos: facturas con ese sector (por fecha de factura), pagadas o no.
"""
import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.curso import Curso, InstanciaExamen
from app.models.gasto import Gasto, SECTORES
from app.models.pago_cuota import PagoCuota
from app.models.alumno import Alumno
from app.cuenta_alumno import MESES, separar_pagos_examen, instancia_de, fecha_imputacion, es_examen
from app.routers.cuotas import cursos_vigentes, extras_por_alumno, planes_de
from app.tz import ahora_ar

router = APIRouter(prefix="/api/sectores", tags=["Sectores"])

# sector -> área de los cursos (Curso.area) cuyas cuotas son ingresos del sector
SECTOR_AREA = {"Ciclo Básico": "Ciclo Basico", "Aviónica": "Avionica", "Mecánica": "Mecanica",
               "Aeronavegantes": "Aeronavegantes"}
# cada examen es su propio sector: los cursos del área Exámenes con ese nombre
SECTOR_EXAMEN = {"RAAC 147": "RAAC 147", "Pericia": "PERICIA"}


def _nombre(c) -> str:
    return re.sub(r"\s*\(.*\)$", "", c.nombre or "").strip().upper()  # "RAAC 147 (Examen)" -> "RAAC 147"


def cursos_del_sector(sector: str, cursos: list) -> list:
    """Cursos cuyas cuotas son ingresos del sector."""
    if sector in SECTOR_EXAMEN:
        return [c for c in cursos if (c.area or "").lower() in ("examenes", "exámenes")
                and _nombre(c).startswith(SECTOR_EXAMEN[sector])]
    area = SECTOR_AREA.get(sector)
    return [c for c in cursos if area and c.area == area]


def curso_de_pago(planes: list, p) -> int | None:
    """Curso al que corresponde un pago, con el mismo criterio que la cuenta del alumno."""
    if not planes:
        return None
    _, por_plan = separar_pagos_examen(planes, [p])
    for clave, lista in por_plan.items():
        if lista:
            return next(pl.get("curso_id") for pl in planes if pl["clave"] == clave)
    forzado = next((pl for pl in planes if pl.get("curso_id") and pl.get("curso_id") == getattr(p, "curso_id", None)), None)
    if forzado:
        return forzado.get("curso_id")
    comunes = [pl for pl in planes if not es_examen(pl.get("curso"))] or planes
    if len(comunes) == 1:
        return comunes[0].get("curso_id") or getattr(comunes[0]["curso"], "id", None)
    exacto = next((pl for pl in comunes if Decimal(str(pl["curso"].cuota or 0)) == Decimal(str(p.importe))), None)
    elegido = exacto or comunes[0]
    return elegido.get("curso_id") or getattr(elegido["curso"], "id", None)


def _fmt(n) -> float:
    return float(round(Decimal(str(n)), 2))


@router.get("/")
def sectores(db: Session = Depends(get_db)):
    """Sectores con los cursos que les aportan ingresos."""
    cursos = db.query(Curso).filter(Curso.activo.is_(True)).order_by(Curso.area, Curso.nombre).all()
    return [{"sector": s, "cursos": [{"id": c.id, "nombre": c.nombre, "por_examen": bool(c.por_examen)}
                                     for c in cursos_del_sector(s, cursos)]}
            for s in SECTORES]


@router.get("/cuenta")
def cuenta(sector: str, desde: date | None = None, hasta: date | None = None, cursos: str | None = None,
           db: Session = Depends(get_db)):
    """Cuenta corriente del sector en el período: ingresos por cuotas, egresos por facturas y saldo."""
    if sector not in SECTORES:
        raise HTTPException(400, "Sector inválido")
    hoy = ahora_ar().date()
    hasta = hasta or hoy
    desde = desde or date(hasta.year, 1, 1)
    if desde > hasta:
        raise HTTPException(400, "La fecha 'desde' es posterior a 'hasta'.")
    del_sector = cursos_del_sector(sector, db.query(Curso).all())
    elegidos = {int(x) for x in (cursos or "").split(",") if x.strip().isdigit()} or {c.id for c in del_sector}
    elegidos &= {c.id for c in del_sector}
    nombres = {c.id: re.sub(r"\s*\(.*\)$", "", c.nombre) for c in del_sector}

    # ---- ingresos
    grupos: dict = {}
    sin_alumno = 0
    if elegidos:
        pagos = db.query(PagoCuota).filter(PagoCuota.fecha >= desde, PagoCuota.fecha <= hasta).all()
        sin_alumno = sum(1 for p in pagos if not p.alumno_id)
        alumnos = {a.id: a for a in db.query(Alumno).filter(Alumno.id.in_({p.alumno_id for p in pagos if p.alumno_id} or {0}))}
        cache: dict = {}
        for p in pagos:
            a = alumnos.get(p.alumno_id)
            if not a:
                continue
            anio = fecha_imputacion(p).year
            if anio not in cache:
                cache[anio] = (cursos_vigentes(db, anio), extras_por_alumno(db, anio))
            cursos_cfg, extras = cache[anio]
            cid = curso_de_pago(planes_de(a, cursos_cfg, extras.get(a.id, [])), p)
            if cid not in elegidos:
                continue
            curso = next((c for c in cursos_cfg if c.id == cid), None) or db.get(Curso, cid)
            if curso and curso.por_examen:
                inst = instancia_de(p, getattr(curso, "_instancias", None) or
                                    db.query(InstanciaExamen).filter(InstanciaExamen.curso_id == cid).all())
                clave = (cid, "inst", inst.id if inst else 0)
                concepto = (f"Examen {nombres[cid]} · instancia {MESES[inst.mes - 1]} {inst.anio}" if inst
                            else f"Examen {nombres[cid]} · sin instancia")
            else:
                clave = (cid, "mes", p.fecha.year, p.fecha.month)
                concepto = f"Cuotas {nombres[cid]} · {MESES[p.fecha.month - 1]} {p.fecha.year}"
            g = grupos.setdefault(clave, {"concepto": concepto, "curso": nombres[cid], "cantidad": 0, "total": Decimal("0"),
                                          "fecha": p.fecha, "desde": p.fecha})
            g["cantidad"] += 1
            g["total"] += Decimal(str(p.importe))
            g["fecha"] = max(g["fecha"], p.fecha)
            g["desde"] = min(g["desde"], p.fecha)
    ingresos = sorted(grupos.values(), key=lambda g: (g["fecha"], g["concepto"]))

    # ---- egresos
    gastos = (db.query(Gasto).filter(Gasto.sector == sector, Gasto.fecha >= desde, Gasto.fecha <= hasta)
              .order_by(Gasto.fecha, Gasto.id).all())

    # ---- cuenta corriente (por fecha; el mismo día, primero los ingresos)
    movs = [{"tipo": "ingreso", "fecha": g["fecha"], "concepto": g["concepto"],
             "detalle": f"{g['cantidad']} pago{'s' if g['cantidad'] != 1 else ''}" + (f" del {g['desde'].strftime('%d/%m')} al {g['fecha'].strftime('%d/%m')}" if g["desde"] != g["fecha"] else ""),
             "importe": g["total"]} for g in ingresos]
    movs += [{"tipo": "egreso", "fecha": x.fecha, "concepto": x.concepto or x.destino or "Factura",
              "detalle": " ".join(v for v in (x.tipo_comprobante, f"{x.punto_venta or ''}-{x.numero or ''}".strip("-")) if v),
              "razon_social": x.razon_social, "importe": Decimal(str(x.importe)), "gasto_id": x.id,
              "pagado": bool(x.forma_pago) or Decimal(str(x.importe)) < 0, "forma_pago": x.forma_pago,
              "fecha_pago": str(x.fecha_pago) if x.fecha_pago else None, "categoria": x.categoria} for x in gastos]
    movs.sort(key=lambda m: (m["fecha"], 0 if m["tipo"] == "ingreso" else 1))
    saldo = Decimal("0")
    for m in movs:
        saldo += m["importe"] if m["tipo"] == "ingreso" else -m["importe"]
        m["saldo"] = _fmt(saldo)
        m["importe"] = _fmt(m["importe"])
        m["fecha"] = str(m["fecha"])
    total_in = sum((g["total"] for g in ingresos), Decimal("0"))
    total_eg = sum((Decimal(str(x.importe)) for x in gastos), Decimal("0"))
    pendiente = sum((Decimal(str(x.importe)) for x in gastos if not x.forma_pago and Decimal(str(x.importe)) > 0), Decimal("0"))
    return {
        "sector": sector, "desde": str(desde), "hasta": str(hasta),
        "cursos": [{"id": c.id, "nombre": c.nombre, "incluido": c.id in elegidos, "por_examen": bool(c.por_examen)} for c in del_sector],
        "ingresos": _fmt(total_in), "egresos": _fmt(total_eg), "saldo": _fmt(total_in - total_eg),
        "egresos_sin_pagar": _fmt(pendiente), "cantidad_facturas": len(gastos),
        "pagos_sin_alumno": sin_alumno, "movimientos": movs,
    }
