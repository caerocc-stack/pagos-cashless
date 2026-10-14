"""Pedidos de materiales y servicios que cargan los profesores y el personal desde el formulario /pedidos."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Integer, Numeric, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar

ESTADOS = {
    "nuevo": "Nuevo",
    "en_revision": "En revisión",
    "presupuestando": "Pidiendo presupuestos",
    "aprobado": "Aprobado",
    "comprado": "Comprado",
    "entregado": "Entregado",
    "rechazado": "Rechazado",
}


class PedidoMaterial(Base):
    __tablename__ = "pedidos_materiales"
    __table_args__ = (Index("ix_pedido_estado", "estado"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), default="materiales")       # materiales / servicio / ambos
    # Quién lo pide (no sale en el PDF para presupuestos)
    solicitante: Mapped[str] = mapped_column(String(120), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(40))
    # Para qué y para dónde
    sector: Mapped[str] = mapped_column(String(120), nullable=False)          # sector/área de destino
    motivo: Mapped[str | None] = mapped_column(Text)
    necesario_para: Mapped[date | None] = mapped_column(Date)
    urgente: Mapped[bool] = mapped_column(default=False)
    # Gestión
    estado: Mapped[str] = mapped_column(String(20), default="nuevo")
    notas: Mapped[str | None] = mapped_column(Text)                          # notas internas de la administración
    ip: Mapped[str | None] = mapped_column(String(60))
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
    actualizado: Mapped[datetime | None] = mapped_column(DateTime)

    items: Mapped[list["PedidoItem"]] = relationship(back_populates="pedido", cascade="all, delete-orphan",
                                                      order_by="PedidoItem.orden")


class PedidoItem(Base):
    __tablename__ = "pedidos_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_materiales.id", ondelete="CASCADE"), nullable=False, index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    producto: Mapped[str] = mapped_column(String(160), nullable=False)
    marca: Mapped[str | None] = mapped_column(String(80))
    modelo: Mapped[str | None] = mapped_column(String(80))
    color: Mapped[str | None] = mapped_column(String(60))
    tamanio: Mapped[str | None] = mapped_column(String(80))                   # tamaño / medida
    caracteristicas: Mapped[str | None] = mapped_column(String(300))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unidad: Mapped[str] = mapped_column(String(30), default="Unidad")
    descripcion: Mapped[str | None] = mapped_column(Text)                    # descripción adicional

    pedido: Mapped[PedidoMaterial] = relationship(back_populates="items")
