"""Portal de alumnos: cuentas (ingreso con el DNI) y archivos enviados para imprimir en la fotocopiadora."""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


class CuentaAlumno(Base):
    """Se crea en el primer ingreso: usuario y clave inicial = DNI del alumno; después elige una propia.
    Borrarla vuelve el acceso al DNI (así se restablece la clave desde la oficina)."""
    __tablename__ = "cuentas_alumnos"

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id"), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    version_sesion: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_ingreso: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class PedidoImpresion(Base):
    """Un archivo enviado por un alumno. El archivo vive en un depósito privado de Storage;
    el registro queda siempre, aunque el archivo se borre a los 30 días de impreso o descartado."""
    __tablename__ = "pedidos_impresion"
    __table_args__ = (Index("ix_impresion_estado", "estado"), Index("ix_impresion_alumno", "alumno_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id"), nullable=False)
    archivo_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    archivo_ruta: Mapped[str] = mapped_column(String(300), nullable=False)
    tamanio: Mapped[int | None] = mapped_column(Integer)
    copias: Mapped[int] = mapped_column(Integer, default=1)
    doble_faz: Mapped[bool] = mapped_column(Boolean, default=False)
    hoja: Mapped[str | None] = mapped_column(String(10))               # A4 / A3 / Oficio (va también en el nombre)
    color: Mapped[bool] = mapped_column(Boolean, default=False)
    notas: Mapped[str | None] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(15), default="pendiente")   # pendiente / impreso / descartado / cancelado
    motivo: Mapped[str | None] = mapped_column(String(300))                # por qué se descartó
    resuelto_at: Mapped[datetime | None] = mapped_column(DateTime)         # fecha de impresión (o de descarte)
    resuelto_por: Mapped[str | None] = mapped_column(String(150))
    archivo_borrado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    alumno = relationship("Alumno")
