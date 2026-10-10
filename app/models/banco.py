from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Date, Numeric, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


# Conceptos del extracto que SÍ se concilian (egresos a proveedores)
#  - 190 / F30: códigos del extracto en Excel (.xls)
#  - el resto: códigos del extracto en PDF de Banco Roela
CONCEPTOS_CONCILIABLES = {
    "190": "Transferencia a distinto titular",
    "F30": "DEBIN (débito inmediato)",
    "190100": "Transferencia a terceros",
    "F30100": "DEBIN (débito inmediato)",
    "146": "Débito directo",
}


class ExtractoBancario(Base):
    """Un extracto importado: período, saldos, control de cierre y totales por tipo."""
    __tablename__ = "extractos_bancarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    banco: Mapped[str] = mapped_column(String(40), default="Banco Roela")
    archivo: Mapped[str | None] = mapped_column(String(160))
    desde: Mapped[date | None] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    saldo_inicial: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    saldo_final: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    cierra: Mapped[bool] = mapped_column(Boolean, default=False)       # saldo inicial + movimientos == saldo final
    movimientos: Mapped[int] = mapped_column(Integer, default=0)
    resumen: Mapped[str | None] = mapped_column(Text)                  # JSON: totales por categoría
    comisiones_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class MovimientoBanco(Base):
    __tablename__ = "banco_movimientos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    cuenta: Mapped[str | None] = mapped_column(String(20))
    comprobante: Mapped[str | None] = mapped_column(String(30))
    concepto: Mapped[str | None] = mapped_column(String(10))      # código del banco (190100, F30100, 146...)
    categoria: Mapped[str | None] = mapped_column(String(20))     # pago / otro_egreso
    descripcion: Mapped[str | None] = mapped_column(String(250))
    cuit: Mapped[str | None] = mapped_column(String(13))          # extraido de la descripcion
    razon_social: Mapped[str | None] = mapped_column(String(160))  # texto tras el CUIT
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # negativo (egreso)

    # Conciliacion con una factura cargada en Gastos
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"))
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False)
    conciliado_manual: Mapped[bool] = mapped_column(Boolean, default=False)

    extracto_id: Mapped[int | None] = mapped_column(ForeignKey("extractos_bancarios.id"))
    origen: Mapped[str | None] = mapped_column(String(120))       # nombre del archivo importado
    hash: Mapped[str] = mapped_column(String(40), unique=True)    # evita duplicados al re-importar
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    gasto: Mapped["Gasto"] = relationship()
