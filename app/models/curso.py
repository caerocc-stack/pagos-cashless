from datetime import datetime
from decimal import Decimal
from datetime import date
from sqlalchemy import String, Boolean, DateTime, Date, Numeric, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.tz import ahora_ar


class Curso(Base):
    """Tipo de curso / carrera con sus parámetros de cuota (derivado de la hoja PARAMETROS)."""
    __tablename__ = "cursos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    area: Mapped[str | None] = mapped_column(String(40))
    # Prefijo del curso del alumno para mapear (ej "TCP", "DESP AER", "ORR").
    # Vacío = aplica por área (los cursos numéricos 1°A..7°B).
    patron: Mapped[str | None] = mapped_column(String(40))
    divisiones: Mapped[str | None] = mapped_column(String(120))  # lista separada por coma: "A,B"

    cuota: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    n_cuotas: Mapped[int] = mapped_column(Integer, default=10)       # cantidad de meses
    mes_inicio: Mapped[int] = mapped_column(Integer, default=3)      # mes de la primera cuota (ORR B: agosto)
    matricula: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cuota_anio_anterior: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cobra_cuotas_viejas: Mapped[bool] = mapped_column(Boolean, default=False)
    # Se rinde por examen (RAAC 147, Pericia): cada pago es la inscripción a una instancia, no una cuota.
    # No genera deuda y pagar varias veces no deja saldo a favor (rindió varias veces).
    por_examen: Mapped[bool] = mapped_column(Boolean, default=False)

    anio: Mapped[int] = mapped_column(Integer, default=2026)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class AlumnoCurso(Base):
    """Curso que hace un alumno en un año. Sirve para los que cursan más de uno a la vez
    (habitual en aeronavegantes y exámenes). Si un alumno no tiene filas, se usa el curso
    que surge de su campo `curso` (como siempre)."""
    __tablename__ = "alumno_cursos"
    __table_args__ = (UniqueConstraint("alumno_id", "curso_id", "anio", name="uq_alumno_curso_anio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id", ondelete="CASCADE"), nullable=False, index=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes_inicio: Mapped[int] = mapped_column(Integer, default=3)      # mes de la primera cuota
    principal: Mapped[bool] = mapped_column(Boolean, default=False)  # el curso del padrón
    etiqueta: Mapped[str | None] = mapped_column(String(30))         # cómo figura en el padrón (ORR B, TCP A)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class InstanciaExamen(Base):
    """Mes (y día, si se sabe) en que hubo examen de un curso que se rinde por examen."""
    __tablename__ = "examen_instancias"
    __table_args__ = (UniqueConstraint("curso_id", "anio", "mes", name="uq_examen_instancia"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), nullable=False, index=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[date | None] = mapped_column(Date)                 # día del examen (opcional)
    descripcion: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class CuponGenerado(Base):
    """Cupón que se le generó a un alumno para un curso en la planilla de SIRO (o que se registró después
    subiendo esa planilla). En los cursos por examen, los que recibieron cupón para una instancia son sus inscriptos."""
    __tablename__ = "cupones_generados"
    __table_args__ = (UniqueConstraint("alumno_id", "curso_id", "vencimiento", name="uq_cupon_generado"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id", ondelete="CASCADE"), nullable=False, index=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), nullable=False, index=True)
    cliente: Mapped[str | None] = mapped_column(String(20))           # Nro Cliente de SIRO (DNI o legajo)
    vencimiento: Mapped[date] = mapped_column(Date, nullable=False)   # 1º vencimiento
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    origen: Mapped[str] = mapped_column(String(20), default="planilla")  # planilla (generada acá) / importado
    lote: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
