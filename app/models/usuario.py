from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.tz import ahora_ar

ROLES = {
    "admin": "Administrador",
    "lectura": "Solo lectura",
}


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), default="admin", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Segundo factor (TOTP, app de autenticacion). El secreto se guarda cifrado.
    totp_secreto: Mapped[str | None] = mapped_column(String(300))
    totp_activo: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_ultimo_paso: Mapped[int | None] = mapped_column(Integer)  # evita reusar el mismo codigo
    codigos_respaldo: Mapped[str | None] = mapped_column(String(1200))  # hashes separados por ";"

    # Bloqueo por intentos fallidos (persistente: en Vercel la memoria no se comparte)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)

    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=False)
    # Se incrementa al cambiar la clave o cerrar todas las sesiones: invalida tokens viejos
    version_sesion: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_ingreso: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
