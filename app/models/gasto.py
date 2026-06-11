from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, ForeignKey, DateTime, Date, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


# Categorias generales (= hojas del Excel de Carlos)
CATEGORIAS = [
    "Gastos de Oficina",
    "Infraestructura",
    "Gastos de la Escuela",
    "Honorarios",
]

# Formas de pago
FORMAS_PAGO = ["Efectivo", "Transferencia", "Débito", "Tarjeta", "Cheque", "Otro"]

# Tipos de comprobante
TIPOS_COMPROBANTE = [
    "Factura A", "Factura B", "Factura C",
    "Ticket", "Recibo", "Nota de Crédito", "Comprobante",
]


class Gasto(Base):
    __tablename__ = "gastos"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Comprobante
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo_comprobante: Mapped[str | None] = mapped_column(String(40))
    punto_venta: Mapped[str | None] = mapped_column(String(10))
    numero: Mapped[str | None] = mapped_column(String(20))

    # Proveedor (FK + datos congelados al momento del gasto)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    razon_social: Mapped[str | None] = mapped_column(String(160))
    cuit: Mapped[str | None] = mapped_column(String(13))

    # Importe (IVA incluido; las notas de credito van en negativo)
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Clasificacion
    concepto: Mapped[str | None] = mapped_column(String(200))
    rubro: Mapped[str | None] = mapped_column(String(80))
    categoria: Mapped[str | None] = mapped_column(String(40))
    destino: Mapped[str | None] = mapped_column(String(160))

    # Pago
    forma_pago: Mapped[str | None] = mapped_column(String(30))
    fecha_pago: Mapped[date | None] = mapped_column(Date)

    # Respaldo (foto/PDF en Supabase Storage)
    adjunto_url: Mapped[str | None] = mapped_column(String(400))

    # Nota de credito vinculada a la factura original
    nc_de_id: Mapped[int | None] = mapped_column(ForeignKey("gastos.id"))

    # Conciliacion bancaria (se completa en la Sesion 4)
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False)

    notas: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    proveedor: Mapped["Proveedor"] = relationship()
