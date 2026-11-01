"""
Cambio de ciclo lectivo: ingresantes del año siguiente y configuración de los cursos de un año nuevo.

Ingresantes: alumnos que todavía no cursan (entran el año que viene). Se cargan con el área "Ingresantes"
y el curso "INGRESANTE <año>", sin división ni DNI hasta que llegue el padrón definitivo. Lo único que
pagan es la matrícula de ingreso, que queda en el área Ingresantes (separada de lo que pagan los que
cursan este año). Cuando empieza el ciclo pasan a 1° con la matrícula ya paga.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.curso import Curso

AREA_INGRESANTES = "Ingresantes"
PATRON_INGRESANTES = "INGRESANTE"
MATRICULA_INGRESO = Decimal(60000)
# Áreas de la escuela y MMH: cuota mensual y matrícula (las que cambian de valor al empezar un ciclo)
AREAS_CUOTA_MENSUAL = {"Ciclo Basico", "Mecanica", "Avionica"}


def curso_ingresantes(anio_ingreso: int) -> str:
    return f"{PATRON_INGRESANTES} {anio_ingreso}"


def asegurar_curso_ingreso(db: Session, anio: int) -> Curso:
    """Curso de los ingresantes que entran en `anio + 1`: solo la matrícula de ingreso, que vence en
    diciembre (hasta entonces no es deuda). Se configura en el año en curso para que lo cobrado entre ahí."""
    c = db.query(Curso).filter(Curso.anio == anio, Curso.patron == PATRON_INGRESANTES).first()
    if not c:
        c = Curso(nombre=f"Ingreso {anio + 1}", area=AREA_INGRESANTES, patron=PATRON_INGRESANTES, divisiones="",
                  cuota=Decimal(0), n_cuotas=0, mes_inicio=12, matricula=MATRICULA_INGRESO,
                  cuota_anio_anterior=Decimal(0), cobra_cuotas_viejas=False, anio=anio, activo=True)
        db.add(c)
        db.flush()
    return c


def es_ingresante(alumno) -> bool:
    return (getattr(alumno, "area", None) or "") == AREA_INGRESANTES


def preparar_cursos(db: Session, anio: int, cuota: Decimal, matricula: Decimal) -> list[Curso]:
    """Crea los cursos de `anio` copiando los del año anterior. Los de cuota mensual (escuela y MMH) toman
    la cuota y la matrícula nuevas; el resto conserva sus valores (se ajustan después desde Cursos).
    No duplica: si ya hay cursos de ese año, no hace nada."""
    if db.query(Curso).filter(Curso.anio == anio).first():
        return []
    nuevos = []
    for c in db.query(Curso).filter(Curso.anio == anio - 1, Curso.activo.is_(True)).all():
        if c.patron == PATRON_INGRESANTES:
            continue  # los ingresantes de este año pasan a 1°; el de los próximos se crea al cargarlos
        mensual = c.area in AREAS_CUOTA_MENSUAL or (c.patron or "").upper() == "MMH"
        nuevos.append(Curso(
            nombre=c.nombre, area=c.area, patron=c.patron, divisiones=c.divisiones,
            cuota=cuota if mensual else c.cuota, n_cuotas=c.n_cuotas, mes_inicio=c.mes_inicio,
            matricula=matricula if mensual and (c.matricula or 0) > 0 else c.matricula,
            cuota_anio_anterior=c.cuota if mensual else c.cuota_anio_anterior,
            cobra_cuotas_viejas=c.cobra_cuotas_viejas, por_examen=c.por_examen, anio=anio, activo=True))
    db.add_all(nuevos)
    db.flush()
    return nuevos
