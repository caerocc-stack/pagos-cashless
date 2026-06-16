from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Date, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


class PagoCuota(Base):
    """Pago de cuota societaria importado del reporte de cobranzas SIRO."""
    __tablename__ = "pagos_cuota"

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int | None] = mapped_column(ForeignKey("alumnos.id"))  # NULL = sin asignar
    cliente_siro: Mapped[str | None] = mapped_column(String(20))
    via: Mapped[str | None] = mapped_column(String(12))   # 'legajo' / 'dni' / 'efectivo' / 'manual'
    caja_mov_id: Mapped[int | None] = mapped_column(ForeignKey("caja_movimientos.id"))  # pago en efectivo

    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)        # Fecha de Proceso
    fecha_pago: Mapped[date | None] = mapped_column(Date)            # Fecha de Pago (referencia)
    canal: Mapped[str | None] = mapped_column(String(15))           # TQR / PC / FSF...
    mes: Mapped[int] = mapped_column(Integer, nullable=False)        # mes de la Fecha de Proceso
    anio: Mapped[int] = mapped_column(Integer, nullable=False)

    origen: Mapped[str | None] = mapped_column(String(120))
    hash: Mapped[str] = mapped_column(String(40), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    alumno: Mapped["Alumno"] = relationship()
