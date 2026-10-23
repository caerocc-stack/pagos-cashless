"""
Cursos que se rinden por examen (RAAC 147, Pericia): instancias del año y alumnos que pagaron cada una.

Cada pago de estos cursos es la inscripción a un examen. Va a la primera instancia desde el mes en que
se pagó (fecha de pago), salvo que se la haya movido a mano a otra (pago.instancia_id).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alumno import Alumno
from app.models.curso import Curso, InstanciaExamen
from app.models.pago_cuota import PagoCuota
from app.cuenta_alumno import MESES, instancia_de, separar_pagos_examen, fecha_imputacion
from app.routers.cuotas import cursos_vigentes, extras_por_alumno, pagos_del_anio, planes_de
from app.tz import ahora_ar

router = APIRouter(prefix="/api/examenes", tags=["Exámenes"])


def _curso_examen(db: Session, curso_id: int) -> Curso:
    c = db.get(Curso, curso_id)
    if not c or not c.por_examen:
        raise HTTPException(404, "Curso por examen no encontrado")
    return c


def _inst_dto(i: InstanciaExamen) -> dict:
    return {"id": i.id, "anio": i.anio, "mes": i.mes, "fecha": str(i.fecha) if i.fecha else None,
            "descripcion": i.descripcion, "nombre": f"{MESES[i.mes - 1].capitalize()} {i.anio}"}


@router.get("/cursos")
def cursos(db: Session = Depends(get_db)):
    return [{"id": c.id, "nombre": c.nombre, "cuota": float(c.cuota or 0), "anio": c.anio, "activo": c.activo}
            for c in db.query(Curso).filter(Curso.por_examen.is_(True)).order_by(Curso.nombre).all()]


@router.get("/{curso_id}")
def detalle(curso_id: int, anio: int | None = None, db: Session = Depends(get_db)):
    """Instancias del año y, en cada una, los alumnos que pagaron (con la fecha de proceso del pago)."""
    anio = anio or ahora_ar().year
    curso = _curso_examen(db, curso_id)
    instancias = (db.query(InstanciaExamen).filter(InstanciaExamen.curso_id == curso_id, InstanciaExamen.anio == anio)
                  .order_by(InstanciaExamen.mes).all())
    # el mismo cálculo que la cuenta del alumno: qué pagos son de este curso por examen
    cursos_cfg = cursos_vigentes(db, anio)
    if not any(c.id == curso_id for c in cursos_cfg):
        cursos_cfg = cursos_cfg + [curso]
    extras = extras_por_alumno(db, anio)
    pagos = pagos_del_anio(db, anio)
    filas = []
    for a in db.query(Alumno).filter(Alumno.id.in_(list(pagos.keys()) or [0])).all():
        planes = planes_de(a, cursos_cfg, extras.get(a.id, []))
        claves = {pl["clave"] for pl in planes if pl.get("curso_id") == curso_id}
        if not claves:
            continue
        _, por_plan = separar_pagos_examen(planes, pagos.get(a.id, []))
        for clave in claves:
            for p in por_plan.get(clave, []):
                inst = instancia_de(p, instancias)
                filas.append({"pago_id": p.id, "alumno_id": a.id, "legajo": a.legajo, "dni": a.dni, "apellido": a.apellido,
                              "nombre": a.nombre, "curso": a.curso, "importe": float(p.importe), "fecha": str(p.fecha),
                              "fecha_pago": str(p.fecha_pago) if p.fecha_pago else None, "canal": p.canal, "via": p.via,
                              "instancia_id": inst.id if inst else None, "manual": bool(p.instancia_id),
                              "mes_pago": fecha_imputacion(p).month})
    filas.sort(key=lambda f: (f["apellido"], f["nombre"], f["fecha"]))
    salida = []
    for i in instancias:
        de_esta = [f for f in filas if f["instancia_id"] == i.id]
        salida.append({**_inst_dto(i), "cantidad": len(de_esta), "alumnos": len({f["alumno_id"] for f in de_esta}),
                       "total": sum(f["importe"] for f in de_esta), "pagos": de_esta})
    sin = [f for f in filas if f["instancia_id"] is None]
    return {"curso": {"id": curso.id, "nombre": curso.nombre, "cuota": float(curso.cuota or 0)}, "anio": anio,
            "instancias": salida, "sin_instancia": sin,
            "meses_sin_instancia": sorted({f["mes_pago"] for f in sin}),
            "total_pagos": len(filas), "total": sum(f["importe"] for f in filas)}


class InstanciaIn(BaseModel):
    anio: int
    mes: int
    fecha: date | None = None
    descripcion: str | None = None


def _validar(db: Session, curso_id: int, data: InstanciaIn, excluir: int | None = None):
    if not 1 <= data.mes <= 12:
        raise HTTPException(400, "Mes inválido")
    if data.fecha and (data.fecha.year, data.fecha.month) != (data.anio, data.mes):
        raise HTTPException(400, "El día del examen tiene que ser del mes elegido.")
    otra = (db.query(InstanciaExamen).filter(InstanciaExamen.curso_id == curso_id, InstanciaExamen.anio == data.anio,
                                             InstanciaExamen.mes == data.mes, InstanciaExamen.id != (excluir or 0)).first())
    if otra:
        raise HTTPException(409, f"Ya hay una instancia en {MESES[data.mes - 1]} {data.anio}.")


@router.post("/{curso_id}/instancias")
def crear_instancia(curso_id: int, data: InstanciaIn, db: Session = Depends(get_db)):
    _curso_examen(db, curso_id)
    _validar(db, curso_id, data)
    i = InstanciaExamen(curso_id=curso_id, anio=data.anio, mes=data.mes, fecha=data.fecha,
                        descripcion=(data.descripcion or "").strip()[:120] or None)
    db.add(i)
    db.commit()
    return _inst_dto(i)


@router.put("/instancias/{inst_id}")
def editar_instancia(inst_id: int, data: InstanciaIn, db: Session = Depends(get_db)):
    i = db.get(InstanciaExamen, inst_id)
    if not i:
        raise HTTPException(404, "Instancia no encontrada")
    _validar(db, i.curso_id, data, inst_id)
    i.anio, i.mes, i.fecha = data.anio, data.mes, data.fecha
    i.descripcion = (data.descripcion or "").strip()[:120] or None
    db.commit()
    return _inst_dto(i)


@router.delete("/instancias/{inst_id}")
def borrar_instancia(inst_id: int, db: Session = Depends(get_db)):
    i = db.get(InstanciaExamen, inst_id)
    if not i:
        raise HTTPException(404, "Instancia no encontrada")
    db.query(PagoCuota).filter(PagoCuota.instancia_id == inst_id).update({PagoCuota.instancia_id: None})
    db.delete(i)
    db.commit()
    return {"ok": True, "mensaje": "Instancia eliminada: sus pagos vuelven a asignarse por la fecha de pago"}


class MoverPago(BaseModel):
    instancia_id: int | None = None  # None: vuelve a la asignación automática por fecha


@router.put("/pagos/{pago_id}/instancia")
def mover_pago(pago_id: int, data: MoverPago, db: Session = Depends(get_db)):
    p = db.get(PagoCuota, pago_id)
    if not p:
        raise HTTPException(404, "Pago no encontrado")
    if data.instancia_id and not db.get(InstanciaExamen, data.instancia_id):
        raise HTTPException(404, "Instancia no encontrada")
    p.instancia_id = data.instancia_id
    db.commit()
    return {"ok": True}
