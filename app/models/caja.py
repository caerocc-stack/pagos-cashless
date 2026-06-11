from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.tz import ahora_ar


# Tipos de movimiento de caja (categorias sugeridas para el desplegable)
TIPOS_MOVIMIENTO = [
    "Cuota", "Recarga ApaiCard", "Venta", "Reintegro", "Aporte", "Otro ingreso",
    "Compra", "Pago proveedor", "Sueldo", "Servicio", "Retiro", "Otro egreso",
]


class MovimientoCaja(Base):
    __tablename__ = "caja_movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    concepto: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_movimiento: Mapped[str | None] = mapped_column(String(60))
    # tipo: 'ingreso' o 'egreso'. El monto siempre se guarda positivo.
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notas: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
