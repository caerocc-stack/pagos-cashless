from datetime import datetime
from decimal import Decimal
from sqlalchemy import ForeignKey, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Saldo(Base):
    __tablename__ = "saldos"

    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id"), primary_key=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    alumno: Mapped["Alumno"] = relationship(back_populates="saldo")
