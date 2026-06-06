from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


class Tarjeta(Base):
    __tablename__ = "tarjetas"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id"), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    alumno: Mapped["Alumno"] = relationship(back_populates="tarjetas")
