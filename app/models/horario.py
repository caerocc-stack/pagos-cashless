from datetime import datetime, date, time
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Date, Time, Numeric, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


# Tipos de día de la jornada
TIPOS_DIA = ["Normal", "Vacaciones", "Feriado", "Licencia", "Franco", "Ausente"]


class Empleado(Base):
    __tablename__ = "empleados"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    puesto: Mapped[str | None] = mapped_column(String(80))
    horas_diarias: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=8)  # jornada esperada
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class RegistroHorario(Base):
    """Una fichada por día y empleado."""
    __tablename__ = "registros_horario"
    __table_args__ = (UniqueConstraint("empleado_id", "fecha", name="uq_empleado_fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), default="Normal")  # Normal / Vacaciones / ...
    entrada: Mapped[time | None] = mapped_column(Time)
    salida: Mapped[time | None] = mapped_column(Time)
    notas: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    empleado: Mapped["Empleado"] = relationship()


class LiquidacionHoras(Base):
    """Horas extras liquidadas (pagadas) a un empleado en un mes."""
    __tablename__ = "liquidaciones_horas"
    __table_args__ = (UniqueConstraint("empleado_id", "anio", "mes", name="uq_liq_emp_mes"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empleado_id: Mapped[int] = mapped_column(ForeignKey("empleados.id"), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    horas: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
