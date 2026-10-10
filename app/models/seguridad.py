from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.tz import ahora_ar


class IntentoLogin(Base):
    """Intentos fallidos de ingreso por IP (limite anti fuerza bruta compartido entre instancias)."""
    __tablename__ = "intentos_login"
    __table_args__ = (Index("ix_intentos_clave_fecha", "clave", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(120), nullable=False)  # "ip:1.2.3.4" o "portal:correo"
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar, nullable=False)


class TokenAcceso(Base):
    """Links de un solo uso (recuperar contrasena). Se guarda solo el hash del token."""
    __tablename__ = "tokens_acceso"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)      # reset_usuario / reset_padre
    ref_id: Mapped[int] = mapped_column(Integer, nullable=False)
    expira: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class Auditoria(Base):
    """Registro de acciones sensibles: ingresos, cambios de clave, 2FA, usuarios."""
    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_fecha", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar, nullable=False)
    usuario: Mapped[str | None] = mapped_column(String(150))
    accion: Mapped[str] = mapped_column(String(60), nullable=False)
    detalle: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(String(60))
