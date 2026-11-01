from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import requiere_admin
from app.database import get_db
from app.models.curso import Curso
from app.ciclo import vista_pase, cerrar_ciclo, deshacer_cierre, recalcular_deuda_anterior, anios_cerrados
from app.tz import ahora_ar

router = APIRouter(prefix="/api/ciclo", tags=["Ciclo lectivo"], dependencies=[Depends(requiere_admin)])


class Anio(BaseModel):
    anio: int


@router.get("/")
def estado_ciclo(db: Session = Depends(get_db)):
    """Qué ciclos están cerrados y cuál es el próximo a cerrar."""
    cerrados = anios_cerrados(db)
    hoy = ahora_ar().year
    a_cerrar = (max(cerrados) + 1) if cerrados else min(hoy, max([c for (c,) in db.query(Curso.anio).distinct()] or [hoy]))
    return {"cerrados": cerrados, "a_cerrar": a_cerrar,
            "cursos_siguiente": bool(db.query(Curso).filter(Curso.anio == a_cerrar + 1).first())}


@router.get("/vista")
def vista(anio: int, db: Session = Depends(get_db)):
    """Qué le pasaría a cada alumno al cerrar el ciclo (no guarda nada)."""
    filas = vista_pase(db, anio)
    return {"anio": anio, "resumen": dict(Counter(f["motivo"] for f in filas)),
            "deuda_que_pasa": round(sum(f["deuda_anterior"] for f in filas), 2),
            "matriculas_pagas": sum(1 for f in filas if f["matricula_paga"]), "alumnos": filas}


@router.post("/cerrar")
def cerrar(data: Anio, db: Session = Depends(get_db)):
    try:
        resumen = cerrar_ciclo(db, data.anio)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "resumen": resumen,
            "mensaje": f"Ciclo {data.anio} cerrado: los alumnos pasaron a {data.anio + 1}. El {data.anio} se sigue viendo eligiendo el año."}


@router.post("/deshacer")
def deshacer(data: Anio, db: Session = Depends(get_db)):
    try:
        n = deshacer_cierre(db, data.anio)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mensaje": f"Se deshizo el cierre de {data.anio}: {n} alumnos volvieron a como estaban."}


@router.post("/recalcular-deuda")
def recalcular(data: Anio, db: Session = Depends(get_db)):
    try:
        n = recalcular_deuda_anterior(db, data.anio)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "mensaje": f"Deuda {data.anio} recalculada: cambió en {n} alumnos."}
