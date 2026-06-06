from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy import text

from app.database import engine, Base, SessionLocal
from app.auth import verify_token, crear_usuario_inicial
from app.routers import alumnos, tarjetas, operaciones, reportes, admin
from app.routers import auth as auth_router

Base.metadata.create_all(bind=engine)


def _asegurar_columnas():
    """Migracion ligera e idempotente: agrega columnas nuevas sin perder datos."""
    migraciones = [
        "ALTER TABLE alumnos ADD COLUMN IF NOT EXISTS email VARCHAR(150)",
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def headers_seguridad(request: Request, call_next):
    """Agrega encabezados de seguridad a todas las respuestas."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


app.include_router(auth_router.router)
app.include_router(alumnos.router)
app.include_router(tarjetas.router)
app.include_router(operaciones.router)
app.include_router(reportes.router)
app.include_router(admin.router)

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
