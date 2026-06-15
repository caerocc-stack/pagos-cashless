from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Numeric, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


class Alumno(Base):
    __tablename__ = "alumnos"

    id: Mapped[int] = mapped_column(primary_key=True)
    legajo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    dni: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    curso: Mapped[str] = mapped_column(String(20), nullable=False)
    area: Mapped[str | None] = mapped_column(String(30))
    division: Mapped[str | None] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(40))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    condicion: Mapped[str | None] = mapped_column(String(20))   # Regular / Becado / Exento
    modalidad: Mapped[str | None] = mapped_column(String(20))   # Mensual / ...
    legajo_completo: Mapped[str | None] = mapped_column(String(20))  # 6 dig con verificador
    cuota_excluir: Mapped[bool] = mapped_column(Boolean, default=False)
    cuota_personalizada: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    @property
    def codigo_siro(self) -> str:
        """Codigo de cliente SIRO: ultimos 5 digitos del legajo, completado a 10 con ceros."""
        solo_digitos = "".join(c for c in str(self.legajo) if c.isdigit())
        return solo_digitos[-5:].zfill(10)

    tarjetas: Mapped[list["Tarjeta"]] = relationship(back_populates="alumno")
    saldo: Mapped["Saldo"] = relationship(back_populates="alumno", uselist=False)
    movimientos: Mapped[list["Movimiento"]] = relationship(back_populates="alumno")
