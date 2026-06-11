from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Date, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


# Conceptos del extracto que SÍ se concilian (egresos a proveedores)
CONCEPTOS_CONCILIABLES = {
    "190": "Transferencia a distinto titular",
    "F30": "DEBIN (débito inmediato)",
}


class MovimientoBanco(Base):
    __tablename__ = "banco_movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    cuenta: Mapped[str | None] = mapped_column(String(20))
    comprobante: Mapped[str | None] = mapped_column(String(30))
    concepto: Mapped[str | None] = mapped_column(String(10))      # codigo 190 / F30
    descripcion: Mapped[str | None] = mapped_column(String(250))
    cuit: Mapped[str | None] = mapped_column(String(13))          # extraido de la descripcion
    razon_social: Mapped[str | None] = mapped_column(String(160))  # texto tras el CUIT
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # negativo (egreso)

    # Conciliacion con una factura cargada en Gastos
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"))
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False)
    conciliado_manual: Mapped[bool] = mapped_column(Boolean, default=False)

    origen: Mapped[str | None] = mapped_column(String(120))       # nombre del archivo importado
    hash: Mapped[str] = mapped_column(String(40), unique=True)    # evita duplicados al re-importar
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    gasto: Mapped["Gasto"] = relationship()
