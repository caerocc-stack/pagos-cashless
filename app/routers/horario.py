from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract

from app.database import get_db
from app.models.horario import Empleado, RegistroHorario, LiquidacionHoras, TIPOS_DIA
from app.schemas.horario import (EmpleadoCreate, EmpleadoUpdate, EmpleadoResponse,
                                 RegistroCreate, RegistroUpdate)
from app.tz import ahora_ar

router = APIRouter(prefix="/api/horario", tags=["Horario"])

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _horas_trab(reg: RegistroHorario) -> Decimal:
    if reg.tipo != "Normal" or not reg.entrada or not reg.salida:
        return Decimal("0")
    e = reg.entrada.hour * 60 + reg.entrada.minute
    s = reg.salida.hour * 60 + reg.salida.minute
    if s < e:  # salida pasada la medianoche
        s += 24 * 60
    return (Decimal(s - e) / Decimal(60)).quantize(Decimal("0.01"))


def _fila(reg: RegistroHorario, horas_diarias: Decimal) -> dict:
    trab = _horas_trab(reg)
    esperadas = horas_diarias if reg.tipo == "Normal" else Decimal("0")
    extras = max(Decimal("0"), trab - esperadas) if reg.tipo == "Normal" else Decimal("0")
    return {
        "id": reg.id, "empleado_id": reg.empleado_id,
        "fecha": str(reg.fecha), "tipo": reg.tipo,
        "entrada": reg.entrada.strftime("%H:%M") if reg.entrada else None,
        "salida": reg.salida.strftime("%H:%M") if reg.salida else None,
        "hs_trabajadas": float(trab), "hs_extras": float(extras),
        "notas": reg.notas,
    }


@router.get("/meta")
def meta():
    return {"tipos_dia": TIPOS_DIA, "meses": MESES}


# ---------- Empleados ----------
@router.get("/empleados", response_model=list[EmpleadoResponse])
def listar_empleados(db: Session = Depends(get_db)):
    return db.query(Empleado).order_by(Empleado.nombre).all()


@router.post("/empleados", response_model=EmpleadoResponse, status_code=201)
def crear_empleado(data: EmpleadoCreate, db: Session = Depends(get_db)):
    e = Empleado(**data.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.put("/empleados/{emp_id}", response_model=EmpleadoResponse)
def actualizar_empleado(emp_id: int, data: EmpleadoUpdate, db: Session = Depends(get_db)):
    e = db.get(Empleado, emp_id)
    if not e:
        raise HTTPException(404, "Empleado no encontrado")
    for c, v in data.model_dump(exclude_unset=True).items():
        setattr(e, c, v)
    db.commit()
    db.refresh(e)
    return e


@router.delete("/empleados/{emp_id}")
def eliminar_empleado(emp_id: int, db: Session = Depends(get_db)):
    e = db.get(Empleado, emp_id)
    if not e:
        raise HTTPException(404, "Empleado no encontrado")
    db.query(RegistroHorario).filter(RegistroHorario.empleado_id == emp_id).delete()
    db.query(LiquidacionHoras).filter(LiquidacionHoras.empleado_id == emp_id).delete()
    db.delete(e)
    db.commit()
    return {"ok": True, "mensaje": "Empleado y sus registros eliminados"}


# ---------- Registros (fichadas) ----------
@router.get("/registros")
def listar_registros(empleado_id: int, anio: int, mes: int, db: Session = Depends(get_db)):
    emp = db.get(Empleado, empleado_id)
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")
    regs = db.query(RegistroHorario).filter(
        RegistroHorario.empleado_id == empleado_id,
        extract("year", RegistroHorario.fecha) == anio,
        extract("month", RegistroHorario.fecha) == mes,
    ).order_by(RegistroHorario.fecha).all()
    filas = [_fila(r, Decimal(str(emp.horas_diarias))) for r in regs]
    return {"registros": filas, "resumen": _resumen_mes(regs, Decimal(str(emp.horas_diarias)), db, empleado_id, anio, mes)}


def _resumen_mes(regs, horas_diarias, db, empleado_id, anio, mes):
    dias_trab = hs_trab = hs_extras = hs_esperadas = dias_vac = 0
    hs_trab = Decimal("0"); hs_extras = Decimal("0"); hs_esperadas = Decimal("0")
    for r in regs:
        if r.tipo == "Vacaciones":
            dias_vac += 1
        if r.tipo == "Normal":
            t = _horas_trab(r)
            hs_esperadas += horas_diarias
            hs_trab += t
            hs_extras += max(Decimal("0"), t - horas_diarias)
            if t > 0:
                dias_trab += 1
    liq = db.query(LiquidacionHoras).filter_by(empleado_id=empleado_id, anio=anio, mes=mes).first()
    liquidadas = Decimal(str(liq.horas)) if liq else Decimal("0")
    return {
        "dias_trabajados": dias_trab, "dias_vacaciones": dias_vac,
        "hs_trabajadas": float(hs_trab), "hs_esperadas": float(hs_esperadas),
        "hs_extras": float(hs_extras), "hs_liquidadas": float(liquidadas),
        "hs_pendientes": float(max(Decimal("0"), hs_extras - liquidadas)),
    }


@router.post("/registros")
def crear_registro(data: RegistroCreate, db: Session = Depends(get_db)):
    existe = db.query(RegistroHorario).filter_by(empleado_id=data.empleado_id, fecha=data.fecha).first()
    if existe:
        # actualizar el del día
        for c, v in data.model_dump().items():
            setattr(existe, c, v)
        db.commit()
        db.refresh(existe)
        reg = existe
    else:
        reg = RegistroHorario(**data.model_dump())
        db.add(reg)
        db.commit()
        db.refresh(reg)
    emp = db.get(Empleado, reg.empleado_id)
    return _fila(reg, Decimal(str(emp.horas_diarias)))


@router.put("/registros/{reg_id}")
def actualizar_registro(reg_id: int, data: RegistroUpdate, db: Session = Depends(get_db)):
    reg = db.get(RegistroHorario, reg_id)
    if not reg:
        raise HTTPException(404, "Registro no encontrado")
    for c, v in data.model_dump(exclude_unset=True).items():
        setattr(reg, c, v)
    db.commit()
    db.refresh(reg)
    emp = db.get(Empleado, reg.empleado_id)
    return _fila(reg, Decimal(str(emp.horas_diarias)))


@router.delete("/registros/{reg_id}")
def eliminar_registro(reg_id: int, db: Session = Depends(get_db)):
    reg = db.get(RegistroHorario, reg_id)
    if not reg:
        raise HTTPException(404, "Registro no encontrado")
    db.delete(reg)
    db.commit()
    return {"ok": True}


# ---------- Liquidacion de horas ----------
@router.put("/liquidacion")
def fijar_liquidacion(empleado_id: int, anio: int, mes: int, horas: float, db: Session = Depends(get_db)):
    liq = db.query(LiquidacionHoras).filter_by(empleado_id=empleado_id, anio=anio, mes=mes).first()
    if liq:
        liq.horas = Decimal(str(horas))
    else:
        db.add(LiquidacionHoras(empleado_id=empleado_id, anio=anio, mes=mes, horas=Decimal(str(horas))))
    db.commit()
    return {"ok": True}


# ---------- Resumen anual ----------
@router.get("/anual")
def resumen_anual(empleado_id: int, anio: int, db: Session = Depends(get_db)):
    emp = db.get(Empleado, empleado_id)
    if not emp:
        raise HTTPException(404, "Empleado no encontrado")
    hd = Decimal(str(emp.horas_diarias))
    regs = db.query(RegistroHorario).filter(
        RegistroHorario.empleado_id == empleado_id,
        extract("year", RegistroHorario.fecha) == anio,
    ).all()
    por_mes = {m: [] for m in range(1, 13)}
    for r in regs:
        por_mes[r.fecha.month].append(r)
    filas = []
    acum_pend = Decimal("0")
    tot = {"dias": 0, "trab": 0.0, "extras": 0.0, "esperadas": 0.0, "vac": 0, "liq": 0.0}
    for m in range(1, 13):
        s = _resumen_mes(por_mes[m], hd, db, empleado_id, anio, m)
        acum_pend += Decimal(str(s["hs_extras"])) - Decimal(str(s["hs_liquidadas"]))
        filas.append({"mes": m, "mes_nombre": MESES[m - 1], **s,
                      "pend_acumuladas": float(max(Decimal("0"), acum_pend))})
        tot["dias"] += s["dias_trabajados"]; tot["trab"] += s["hs_trabajadas"]
        tot["extras"] += s["hs_extras"]; tot["esperadas"] += s["hs_esperadas"]
        tot["vac"] += s["dias_vacaciones"]; tot["liq"] += s["hs_liquidadas"]
    return {"empleado": emp.nombre, "anio": anio, "meses": filas, "totales": tot}
