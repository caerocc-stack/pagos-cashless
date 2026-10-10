"""
Preparacion de la base: crea tablas, aplica migraciones livianas y el usuario admin inicial.

En Render se ejecuta al arrancar la app. En Vercel cada instancia nueva arrancaria y
repetiria ~20 consultas, asi que ahi se corre una sola vez por deploy (buildCommand de
vercel.json -> scripts/preparar_base.py).
"""
from sqlalchemy import text

from app.database import engine, Base, SessionLocal
from app.auth import crear_usuario_inicial
from app import models  # noqa: F401 (registra las tablas principales)
from app.models import configuracion, proveedor, gasto, caja, banco, curso, pago_cuota, horario, seguridad, portal  # noqa: F401

MIGRACIONES = [
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS email VARCHAR(150)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS area VARCHAR(30)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS cuota_excluir BOOLEAN DEFAULT FALSE",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS cuota_personalizada NUMERIC(12,2)",
    # Clasificar el area automaticamente segun el curso (solo donde falta)
    "UPDATE alumnos SET area='Ciclo Basico' WHERE area IS NULL AND curso ILIKE '%ciclo%'",
    "UPDATE alumnos SET area='Avionica' WHERE area IS NULL AND curso ILIKE '%avionica%'",
    "UPDATE alumnos SET area='Mecanica' WHERE area IS NULL AND curso ILIKE '%mecanica%'",
    # Indices para acelerar historial, reportes y envios por curso/area
    "CREATE INDEX IF NOT EXISTS ix_mov_alumno ON movimientos (alumno_id)",
    "CREATE INDEX IF NOT EXISTS ix_mov_fecha ON movimientos (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_alumno_curso ON alumnos (curso)",
    "CREATE INDEX IF NOT EXISTS ix_alumno_area ON alumnos (area)",
    # Gastos: vinculo a un movimiento de caja en efectivo (forma de pago)
    "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS caja_mov_id INTEGER",
    # Alumnos: datos del padron ALUMNOS 2026 (cuotas)
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS division VARCHAR(10)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS telefono VARCHAR(40)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS fecha_nacimiento DATE",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS condicion VARCHAR(20)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS modalidad VARCHAR(20)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS legajo_completo VARCHAR(20)",
    "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS deuda_anio_anterior NUMERIC(12,2)",
    # Pagos de cuota: vínculo a un movimiento de caja (pago en efectivo)
    "ALTER TABLE pagos_cuota ADD COLUMN IF NOT EXISTS caja_mov_id INTEGER",
    # Usuarios: correo, roles, 2FA y bloqueo por intentos (seguridad, oct 2026)
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email VARCHAR(150) UNIQUE",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rol VARCHAR(20) NOT NULL DEFAULT 'admin'",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_secreto VARCHAR(300)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_activo BOOLEAN DEFAULT FALSE",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_ultimo_paso INTEGER",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS codigos_respaldo VARCHAR(1200)",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS intentos_fallidos INTEGER DEFAULT 0",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_hasta TIMESTAMP",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN DEFAULT FALSE",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS version_sesion INTEGER DEFAULT 0",
    "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ultimo_ingreso TIMESTAMP",
    # Conciliación con extracto PDF de Banco Roela (oct 2026)
    "ALTER TABLE banco_movimientos ADD COLUMN IF NOT EXISTS categoria VARCHAR(20)",
    "ALTER TABLE banco_movimientos ADD COLUMN IF NOT EXISTS extracto_id INTEGER REFERENCES extractos_bancarios(id)",
    "CREATE INDEX IF NOT EXISTS ix_gasto_fecha ON gastos (fecha)",
    "CREATE INDEX IF NOT EXISTS ix_gasto_proveedor ON gastos (proveedor_id)",
    "CREATE INDEX IF NOT EXISTS ix_banco_fecha ON banco_movimientos (fecha)",
    # Haberes (256) y pagos automáticos (880100) NO se concilian: sacarlos de la conciliación.
    # Si un gasto real estaba vinculado, queda pendiente de pago; los creados desde el extracto se borran.
    "UPDATE gastos SET conciliado = FALSE, forma_pago = NULL, fecha_pago = NULL WHERE id IN "
    "(SELECT gasto_id FROM banco_movimientos WHERE concepto IN ('256','880100') AND gasto_id IS NOT NULL) "
    "AND (notas IS NULL OR notas NOT LIKE 'Creado desde el extracto:%')",
    "WITH m AS (DELETE FROM banco_movimientos WHERE concepto IN ('256','880100') RETURNING gasto_id) "
    "DELETE FROM gastos WHERE id IN (SELECT gasto_id FROM m) AND notas LIKE 'Creado desde el extracto:%'",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS origen VARCHAR(20)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS lote VARCHAR(40)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS archivo VARCHAR(150)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS identificador VARCHAR(20)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS nombre_cupon VARCHAR(150)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS periodo VARCHAR(40)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS vencimiento DATE",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS vencimiento2 DATE",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS monto2 NUMERIC(12,2)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS vencimiento3 DATE",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS monto3 NUMERIC(12,2)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS vence_ultimo DATE",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS codigo_pago VARCHAR(30)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS codigo_barras VARCHAR(80)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS pago_url VARCHAR(300)",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS qr_texto TEXT",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS qr_imagen TEXT",
    "ALTER TABLE cupones_enviados ADD COLUMN IF NOT EXISTS barras_imagen TEXT",
    "CREATE INDEX IF NOT EXISTS ix_cupon_vence ON cupones_enviados (alumno_id, vence_ultimo)",
    "CREATE INDEX IF NOT EXISTS ix_cupon_lote ON cupones_enviados (lote)",
]


def _asegurar_columnas():
    """Migracion ligera e idempotente: agrega columnas nuevas sin perder datos."""
    if engine.dialect.name != "postgresql":
        return  # base local de pruebas (SQLite): create_all ya crea todo
    for sql in MIGRACIONES:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception as e:
            print("Aviso de migracion:", e)


def preparar_base():
    Base.metadata.create_all(bind=engine)
    _asegurar_columnas()
    db = SessionLocal()
    try:
        crear_usuario_inicial(db)
    finally:
        db.close()
