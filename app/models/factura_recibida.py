"""Facturas que los proveedores suben desde el portal público /facturas."""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, LargeBinary, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.tz import ahora_ar

ESTADOS = {
    "cargada": "Cargada como gasto (por revisar)",
    "revisar": "Hay que cargarla a mano",
    "duplicada": "Ya estaba cargada",
    "descartada": "Descartada",
}


class FacturaRecibida(Base):
    __tablename__ = "facturas_recibidas"
    __table_args__ = (Index("ix_factrec_estado", "estado"), Index("ix_factrec_hash", "sha256"))

    id: Mapped[int] = mapped_column(primary_key=True)
    envio: Mapped[str] = mapped_column(String(40), nullable=False)          # agrupa los archivos de una misma carga
    archivo_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    ruta_storage: Mapped[str | None] = mapped_column(String(300))           # depósito privado de Supabase
    contenido: Mapped[bytes | None] = mapped_column(LargeBinary)             # solo si no hay Storage (pruebas locales)
    tamanio: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Lo que escribió quien subió la factura (opcional)
    proveedor_declarado: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(150))
    comentario: Mapped[str | None] = mapped_column(String(500))
    ip: Mapped[str | None] = mapped_column(String(60))
    # Resultado del procesamiento
    estado: Mapped[str] = mapped_column(String(20), default="revisar")
    motivo: Mapped[str | None] = mapped_column(String(300))
    datos: Mapped[str | None] = mapped_column(Text)                          # JSON con lo extraído
    gasto_id: Mapped[int | None] = mapped_column(Integer)                    # gasto creado (sin FK: evita ciclo con gastos)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
