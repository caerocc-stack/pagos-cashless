from datetime import datetime
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.tz import ahora_ar


class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuit: Mapped[str] = mapped_column(String(13), unique=True, nullable=False)
    razon_social: Mapped[str] = mapped_column(String(160), nullable=False)
    nombre_fantasia: Mapped[str | None] = mapped_column(String(160))
    rubro: Mapped[str | None] = mapped_column(String(80))
    contacto: Mapped[str | None] = mapped_column(String(100))
    telefono: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(150))
    cbu: Mapped[str | None] = mapped_column(String(30))
    notas: Mapped[str | None] = mapped_column(String(400))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
