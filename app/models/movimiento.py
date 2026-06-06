from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


class Movimiento(Base):
    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # recarga, consumo, transferencia_in, transferencia_out, reintegro
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(200))
    referencia_id: Mapped[int | None] = mapped_column(Integer)
    operador: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    alumno: Mapped["Alumno"] = relationship(back_populates="movimientos")
