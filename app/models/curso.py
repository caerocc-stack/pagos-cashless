from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Numeric, Integer
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
    matricula: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cuota_anio_anterior: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    cobra_cuotas_viejas: Mapped[bool] = mapped_column(Boolean, default=False)

    anio: Mapped[int] = mapped_column(Integer, default=2026)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
