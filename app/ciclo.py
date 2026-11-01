"""
Cambio de ciclo lectivo: ingresantes del año siguiente y configuración de los cursos de un año nuevo.

Ingresantes: alumnos que todavía no cursan (entran el año que viene). Se cargan con el área "Ingresantes"
y el curso "INGRESANTE <año>", sin división ni DNI hasta que llegue el padrón definitivo. Lo único que
pagan es la matrícula de ingreso, que queda en el área Ingresantes (separada de lo que pagan los que
cursan este año). Cuando empieza el ciclo pasan a 1° con la matrícula ya paga.
"""
import re
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


# ---------------------------------------------------------------- años cerrados: cómo estaba cada alumno
CAMPOS_ANIO = ("curso", "area", "division", "condicion", "modalidad", "matricula_paga", "deuda_anio_anterior",
               "deuda_anterior_detalle", "cuota_personalizada", "cuota_excluir", "activo")


class EnAnio:
    """El alumno como estaba en un ciclo ya cerrado: los datos del año salen de la foto (AlumnoAnio) y el resto
    (nombre, legajo, DNI, correo…) del alumno."""
    def __init__(self, alumno, foto):
        object.__setattr__(self, "_alumno", alumno)
        object.__setattr__(self, "_foto", foto)

    def __getattr__(self, campo):
        if campo in CAMPOS_ANIO:
            return getattr(self._foto, campo)
        return getattr(self._alumno, campo)


def fotos_del_anio(db: Session, anio: int, alumno_id: int | None = None) -> dict:
    from app.models.curso import AlumnoAnio
    q = db.query(AlumnoAnio).filter(AlumnoAnio.anio == anio)
    if alumno_id:
        q = q.filter(AlumnoAnio.alumno_id == alumno_id)
    return {f.alumno_id: f for f in q.all()}


def en_anio(alumnos, fotos: dict) -> list:
    """Los alumnos como estaban en el año de las fotos (sin foto: como están hoy)."""
    return [EnAnio(a, fotos[a.id]) if a.id in fotos else a for a in alumnos]


def fotos_anios(db: Session, alumno_id: int) -> list[int]:
    from app.models.curso import AlumnoAnio
    return [x for (x,) in db.query(AlumnoAnio.anio).filter(AlumnoAnio.alumno_id == alumno_id)]


def anios_cerrados(db: Session) -> list[int]:
    from app.models.curso import AlumnoAnio
    return sorted(x for (x,) in db.query(AlumnoAnio.anio).distinct())


# ---------------------------------------------------------------- pase de año
NIVEL = re.compile(r"^\s*(\d)\s*°\s*([A-Za-z])?\s*$")
PENDIENTE = "a definir"


def curso_siguiente(alumno, anio: int) -> tuple[str, str | None, str | None, str]:
    """(curso, área, división, motivo) del alumno en el ciclo siguiente.
    1°→2°, 2°→3°, 4°→5°, 5°→6° y 6°→7° en la misma división; 3° pasa a 4° sin división ni especialidad
    (se define con la lista del año que viene); 7° egresa. Los ingresantes pasan a 1° sin división.
    MMH sigue igual; los demás cursos de aeronavegantes y exámenes terminan con el año."""
    curso, area = (alumno.curso or "").strip(), alumno.area or ""
    if area == AREA_INGRESANTES:
        return "1°", "Ciclo Basico", None, "ingresante a 1°"
    m = NIVEL.match(curso)
    if m and area in AREAS_CUOTA_MENSUAL:
        nivel, div = int(m.group(1)), (m.group(2) or "").upper()
        if nivel == 7:
            return f"EGRESADO {anio}", "Egresados", None, "egresa"
        if nivel == 3:
            return f"4° ({PENDIENTE})", area, None, "3° a 4° (falta la especialidad)"
        return f"{nivel + 1}°{div}", area, div or None, f"{nivel}° a {nivel + 1}°"
    if curso.upper().startswith("MMH"):
        return curso, area, alumno.division, "sigue en MMH"
    if area in ("Aeronavegantes", "Examenes"):
        return f"FIN {curso}"[:20], "Egresados", None, "terminó el curso"
    return curso, area or None, alumno.division, "sin cambios"


def es_pendiente(curso: str | None) -> bool:
    """Curso provisorio del pase de año (se completa con el listado del año nuevo)."""
    c = (curso or "").strip()
    return PENDIENTE in c or c == "1°" or c.upper().startswith(PATRON_INGRESANTES)


def _situacion_al_cierre(db: Session, anio: int) -> dict:
    """Estado de cuenta de cada alumno al 31/12 de `anio` (todas las cuotas del año vencidas)."""
    from datetime import date
    from app.models.alumno import Alumno
    from app.cuenta_alumno import estado_cuenta
    from app.routers.cuotas import cursos_vigentes, extras_por_alumno, pagos_del_anio, planes_de
    cursos, extras, pagos = cursos_vigentes(db, anio), extras_por_alumno(db, anio), pagos_del_anio(db, anio)
    alumnos = en_anio(db.query(Alumno).all(), fotos_del_anio(db, anio))
    salida = {}
    for a in alumnos:
        planes = planes_de(a, cursos, extras.get(a.id, []))
        salida[a.id] = estado_cuenta(a, planes, pagos.get(a.id, []), anio, hoy=date(anio, 12, 31), mes_corte=12)
    return salida


def _deuda_y_matricula(a, info: dict, anio: int) -> tuple[Decimal, str | None, bool]:
    """Deuda que pasa al año siguiente, cuánto es de cada año ("2025:…;2026:…") y si la matrícula del año
    siguiente ya está paga."""
    if es_ingresante(a):  # la matrícula de ingreso es la del año que empieza: si no la pagó, no es deuda vieja
        pago = any(it.get("es_matricula") and it["pagado"] >= it["importe"] > 0 for it in info.get("items", []))
        return Decimal(0), None, pago
    por_anio = {x["anio"]: Decimal(str(round(x["saldo"], 2))) for x in info.get("deuda_anterior_por_anio", []) if x["saldo"] > 0}
    del_anio = Decimal(str(round(info.get("deuda", 0) or 0, 2)))  # cuotas del año que quedaron sin pagar
    if del_anio > 0:
        por_anio[anio] = del_anio
    deuda = sum(por_anio.values(), Decimal(0))
    detalle = ";".join(f"{y}:{imp:.2f}" for y, imp in sorted(por_anio.items())) or None
    return deuda, detalle, (info.get("matricula_siguiente_pagada") or 0) > 0


def vista_pase(db: Session, anio: int) -> list[dict]:
    """Qué le pasaría a cada alumno al cerrar `anio` (sin guardar nada)."""
    from app.models.alumno import Alumno
    infos = _situacion_al_cierre(db, anio)
    filas = []
    for a in db.query(Alumno).order_by(Alumno.apellido, Alumno.nombre).all():
        curso, area, div, motivo = curso_siguiente(a, anio) if a.activo else (a.curso, a.area, a.division, "inactivo")
        deuda, detalle, mat = _deuda_y_matricula(a, infos.get(a.id, {}), anio)
        filas.append({"id": a.id, "alumno": f"{a.apellido}, {a.nombre}", "legajo": a.legajo, "curso": a.curso, "area": a.area,
                      "curso_nuevo": curso, "area_nueva": area, "division_nueva": div, "motivo": motivo,
                      "deuda_anterior": float(deuda), "deuda_detalle": detalle, "matricula_paga": mat})
    return filas


def cerrar_ciclo(db: Session, anio: int) -> dict:
    """Cierra `anio`: guarda cómo estaba cada alumno (foto del año) y lo pasa al ciclo siguiente con su curso
    nuevo, la deuda que le quedó como deuda del año anterior y la matrícula marcada como paga si la pagó por
    adelantado (o, los ingresantes, la de ingreso)."""
    from collections import Counter
    from app.models.alumno import Alumno
    from app.models.curso import AlumnoAnio
    if db.query(AlumnoAnio).filter(AlumnoAnio.anio == anio).first():
        raise ValueError(f"El ciclo {anio} ya está cerrado.")
    if not db.query(Curso).filter(Curso.anio == anio + 1).first():
        raise ValueError(f"Primero prepará los cursos {anio + 1} (Cursos y parámetros → Preparar ciclo {anio + 1}).")
    filas = {f["id"]: f for f in vista_pase(db, anio)}
    resumen = Counter()
    for a in db.query(Alumno).all():
        db.add(AlumnoAnio(alumno_id=a.id, anio=anio, **{c: getattr(a, c) for c in CAMPOS_ANIO}))
        f = filas[a.id]
        a.curso, a.area, a.division = f["curso_nuevo"][:20], f["area_nueva"], f["division_nueva"]
        a.deuda_anio_anterior = Decimal(str(f["deuda_anterior"])) or None
        a.deuda_anterior_detalle = f["deuda_detalle"]
        a.matricula_paga = f["matricula_paga"]
        resumen[f["motivo"]] += 1
    db.commit()
    return dict(resumen)


def deshacer_cierre(db: Session, anio: int) -> int:
    """Vuelve a todos los alumnos a como estaban en `anio` (la foto del cierre) y borra el cierre."""
    from app.models.alumno import Alumno
    from app.models.curso import AlumnoAnio
    fotos = fotos_del_anio(db, anio)
    if not fotos:
        raise ValueError(f"El ciclo {anio} no está cerrado.")
    if db.query(AlumnoAnio).filter(AlumnoAnio.anio > anio).first():
        raise ValueError(f"Ya se cerró un ciclo posterior a {anio}: deshacé ese primero.")
    for a in db.query(Alumno).filter(Alumno.id.in_(list(fotos))).all():
        for c in CAMPOS_ANIO:
            setattr(a, c, getattr(fotos[a.id], c))
    db.query(AlumnoAnio).filter(AlumnoAnio.anio == anio).delete()
    db.commit()
    return len(fotos)


def recalcular_deuda_anterior(db: Session, anio: int) -> int:
    """Después del cierre pueden entrar pagos de `anio` (lo pagado en diciembre se procesa en enero): vuelve a
    calcular la deuda que pasa al año siguiente. Devuelve a cuántos alumnos les cambió."""
    from app.models.alumno import Alumno
    fotos = fotos_del_anio(db, anio)
    if not fotos:
        raise ValueError(f"El ciclo {anio} no está cerrado.")
    infos = _situacion_al_cierre(db, anio)
    n = 0
    for a in db.query(Alumno).filter(Alumno.id.in_(list(fotos))).all():
        deuda, detalle, mat = _deuda_y_matricula(EnAnio(a, fotos[a.id]), infos.get(a.id, {}), anio)
        if (Decimal(str(a.deuda_anio_anterior or 0)) != deuda or (a.deuda_anterior_detalle or None) != detalle
                or (mat and not a.matricula_paga)):
            a.deuda_anio_anterior = deuda or None
            a.deuda_anterior_detalle = detalle
            a.matricula_paga = a.matricula_paga or mat
            n += 1
    db.commit()
    return n
