from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.curso import Curso
from app.models.alumno import Alumno
from app.schemas.curso import CursoCreate, CursoUpdate, CursoResponse

router = APIRouter(prefix="/api/cursos", tags=["Cursos"])


# Configuración inicial derivada de la hoja PARAMETROS del Excel de Carlos
SEED = [
    # nombre, area, patron, divisiones, cuota, n_cuotas, matricula, cuota_ant, viejas
    ("Ciclo Básico", "Ciclo Basico", None, "A,B,C,D", 45000, 10, 50000, 30000, True),
    ("Mecánica", "Mecanica", None, "A,B", 45000, 10, 50000, 30000, True),
    ("Aviónica", "Avionica", None, "A,B", 45000, 10, 50000, 30000, True),
    ("MMH (Aeronavegantes)", "Aeronavegantes", "MMH", "", 45000, 10, 50000, 0, False),
    ("ORR (Exámenes)", "Examenes", "ORR", "", 180000, 3, 0, 0, False),
    ("TCP", "Aeronavegantes", "TCP", "A,B", 50000, 1, 0, 0, False),
    ("DESP AER", "Aeronavegantes", "DESP AER", "A,B", 50000, 1, 0, 0, False),
    ("PCA-HVI", "Aeronavegantes", "PCA-HVI", "A,B", 50000, 1, 0, 0, False),
]


def curso_de_alumno(alumno: Alumno, cursos: list[Curso]) -> Curso | None:
    """Devuelve el curso/parámetro que aplica a un alumno (por patrón de curso, o por área)."""
    txt = (alumno.curso or "").strip().upper()
    for c in cursos:
        if c.patron and txt.startswith(c.patron.upper()):
            return c
    for c in cursos:
        if not c.patron and c.area and alumno.area and c.area.lower() == alumno.area.lower():
            return c
    return None


@router.get("/", response_model=list[CursoResponse])
def listar(anio: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Curso)
    if anio:
        q = q.filter(Curso.anio == anio)
    return q.order_by(Curso.area, Curso.nombre).all()


@router.post("/seed")
def seed(anio: int = 2026, db: Session = Depends(get_db)):
    """Carga la configuración inicial de cursos si todavía no hay ninguno para el año."""
    if db.query(Curso).filter(Curso.anio == anio).first():
        return {"ok": True, "mensaje": "Ya había cursos cargados para ese año", "creados": 0}
    n = 0
    for nombre, area, patron, divs, cuota, ncu, matric, ant, viejas in SEED:
        db.add(Curso(
            nombre=nombre, area=area, patron=patron, divisiones=divs,
            cuota=Decimal(str(cuota)), n_cuotas=ncu, matricula=Decimal(str(matric)),
            cuota_anio_anterior=Decimal(str(ant)), cobra_cuotas_viejas=viejas, anio=anio,
        ))
        n += 1
    db.commit()
    return {"ok": True, "mensaje": f"Se cargaron {n} cursos", "creados": n}


@router.post("/", response_model=CursoResponse, status_code=201)
def crear(data: CursoCreate, db: Session = Depends(get_db)):
    c = Curso(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{curso_id}", response_model=CursoResponse)
def actualizar(curso_id: int, data: CursoUpdate, db: Session = Depends(get_db)):
    c = db.get(Curso, curso_id)
    if not c:
        raise HTTPException(404, "Curso no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(c, campo, valor)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{curso_id}")
def eliminar(curso_id: int, db: Session = Depends(get_db)):
    c = db.get(Curso, curso_id)
    if not c:
        raise HTTPException(404, "Curso no encontrado")
    db.delete(c)
    db.commit()
    return {"ok": True, "mensaje": f"Curso {c.nombre} eliminado"}
