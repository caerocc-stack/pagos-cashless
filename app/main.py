import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy import text

from app.database import engine, Base, SessionLocal
from app.auth import verify_token, crear_usuario_inicial, get_current_user
from app.routers import alumnos, tarjetas, operaciones, reportes, admin, cupones, config, proveedores, gastos, caja, conciliacion, cursos, cuotas
from app.routers import auth as auth_router
from app.models import configuracion as _configuracion  # noqa: F401 (registra la tabla)
from app.models import proveedor as _proveedor  # noqa: F401 (registra la tabla)
from app.models import gasto as _gasto  # noqa: F401 (registra la tabla)
from app.models import caja as _caja  # noqa: F401 (registra la tabla)
from app.models import banco as _banco  # noqa: F401 (registra la tabla)
from app.models import curso as _curso  # noqa: F401 (registra la tabla)
from app.models import pago_cuota as _pago_cuota  # noqa: F401 (registra la tabla)

Base.metadata.create_all(bind=engine)


def _asegurar_columnas():
    """Migracion ligera e idempotente: agrega columnas nuevas sin perder datos."""
    migraciones = [
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
    ]
    for sql in migraciones:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception as e:
            print("Aviso de migracion:", e)


_asegurar_columnas()

# Crear usuario admin inicial si no existe
db = SessionLocal()
try:
    crear_usuario_inicial(db)
finally:
    db.close()

app = FastAPI(
    title="APAI Pay",
    description="Sistema de pagos cashless para el colegio — APAI",
    version="2.0.0",
    docs_url=None,       # deshabilita Swagger UI publico
    redoc_url=None,      # deshabilita ReDoc publico
    openapi_url=None,    # no expone el esquema de la API
)

# CORS: solo se permiten los origenes definidos en APP_ORIGIN (separados por coma).
# Como la interfaz se sirve desde el mismo dominio, por defecto no se permite cross-origin.
_origenes = [o.strip() for o in os.getenv("APP_ORIGIN", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origenes,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https://*.supabase.co; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def headers_seguridad(request: Request, call_next):
    """Agrega encabezados de seguridad a todas las respuestas."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = CSP
    return response


# Todos los endpoints de la API (salvo login/logout) requieren sesion iniciada.
# Se aplica la dependencia a nivel de router para que cualquier endpoint nuevo
# quede protegido por defecto (defensa en profundidad).
_auth = [Depends(get_current_user)]
app.include_router(auth_router.router)
app.include_router(alumnos.router, dependencies=_auth)
app.include_router(tarjetas.router, dependencies=_auth)
app.include_router(operaciones.router, dependencies=_auth)
app.include_router(cupones.router, dependencies=_auth)
app.include_router(reportes.router, dependencies=_auth)
app.include_router(admin.router, dependencies=_auth)
app.include_router(config.router, dependencies=_auth)
app.include_router(proveedores.router, dependencies=_auth)
app.include_router(gastos.router, dependencies=_auth)
app.include_router(caja.router, dependencies=_auth)
app.include_router(conciliacion.router, dependencies=_auth)
app.include_router(cursos.router, dependencies=_auth)
app.include_router(cuotas.router, dependencies=_auth)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(str(STATIC_DIR / "logo.png"))


@app.get("/login")
def login_page():
    return FileResponse(str(STATIC_DIR / "login.html"))


@app.get("/")
def root(request: Request):
    token = request.cookies.get("token")
    if not token or not verify_token(token):
        return FileResponse(str(STATIC_DIR / "login.html"))
    return FileResponse(str(STATIC_DIR / "index.html"))
