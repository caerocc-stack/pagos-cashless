"""Portal de padres: cuentas, cupones enviados y consultas (mesa de ayuda)."""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, Date, Integer, Numeric, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.tz import ahora_ar


class CuentaPadre(Base):
    """Una cuenta por correo (el mismo al que llegan los cupones). Ve a todos los hijos con ese correo.
    Se crea sola en el primer ingreso con el DNI de cualquiera de los hijos como clave inicial."""
    __tablename__ = "cuentas_padres"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    version_sesion: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_ingreso: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)


class CuponEnviado(Base):
    """Registro de cada cupón de pago generado: el padre lo puede volver a abrir desde el portal."""
    __tablename__ = "cupones_enviados"
    __table_args__ = (Index("ix_cupon_alumno", "alumno_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)       # cuota / recarga
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    concepto: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500))
    email_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
    # Cupones leídos del PDF de SIRO (origen "siro_pdf"): datos para pagar desde el portal
    origen: Mapped[str | None] = mapped_column(String(20))           # sistema / siro_pdf
    lote: Mapped[str | None] = mapped_column(String(40))             # una carga de PDF
    archivo: Mapped[str | None] = mapped_column(String(150))
    identificador: Mapped[str | None] = mapped_column(String(20))    # DNI o 000+legajo
    nombre_cupon: Mapped[str | None] = mapped_column(String(150))
    periodo: Mapped[str | None] = mapped_column(String(40))          # OCTUBRE 2026
    vencimiento: Mapped[date | None] = mapped_column(Date)           # 1er vencimiento (monto = 1er importe)
    vencimiento2: Mapped[date | None] = mapped_column(Date)
    monto2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vencimiento3: Mapped[date | None] = mapped_column(Date)
    monto3: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vence_ultimo: Mapped[date | None] = mapped_column(Date)          # después de esta fecha no se muestra
    codigo_pago: Mapped[str | None] = mapped_column(String(30))      # código de pago electrónico
    codigo_barras: Mapped[str | None] = mapped_column(String(80))
    pago_url: Mapped[str | None] = mapped_column(String(300))        # botón de pago SIRO
    qr_texto: Mapped[str | None] = mapped_column(Text)
    qr_imagen: Mapped[str | None] = mapped_column(Text)              # data:image/png (si el QR no se pudo leer)
    barras_imagen: Mapped[str | None] = mapped_column(Text)          # data:image/png del código de barras


class Consulta(Base):
    """Consulta o reporte: de un padre (portal) o de un usuario del sistema (reportar un problema)."""
    __tablename__ = "consultas"
    __table_args__ = (Index("ix_consulta_estado", "estado"), Index("ix_consulta_cuenta", "cuenta_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    origen: Mapped[str] = mapped_column(String(10), default="portal")     # portal / sistema
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuentas_padres.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    alumno_id: Mapped[int | None] = mapped_column(ForeignKey("alumnos.id"))
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)
    asunto: Mapped[str] = mapped_column(String(160), nullable=False)
    estado: Mapped[str] = mapped_column(String(15), default="abierta")   # abierta / respondida / cerrada
    leida_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    leida_autor: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)
    actualizada: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    mensajes: Mapped[list["MensajeConsulta"]] = relationship(back_populates="consulta", order_by="MensajeConsulta.id",
                                                              cascade="all, delete-orphan")


class MensajeConsulta(Base):
    __tablename__ = "mensajes_consulta"

    id: Mapped[int] = mapped_column(primary_key=True)
    consulta_id: Mapped[int] = mapped_column(ForeignKey("consultas.id"), nullable=False)
    autor: Mapped[str] = mapped_column(String(10), nullable=False)        # padre / admin / usuario
    autor_nombre: Mapped[str | None] = mapped_column(String(150))
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    adjunto_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora_ar)

    consulta: Mapped["Consulta"] = relationship(back_populates="mensajes")
