from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import engine, Base, SessionLocal
from app.auth import verify_token, crear_usuario_inicial
from app.routers import alumnos, tarjetas, operaciones
from app.routers import auth as auth_router

Base.metadata.create_all(bind=engine)

# Crear usuario admin inicial si no existe
db = SessionLocal()
try:
    crear_usuario_inicial(db)
finally:
    db.close()

app = FastAPI(
    title="APAI Pagos Cashless",
    description="Sistema de pagos cashless para el colegio — APAI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router.router)
app.include_router(alumnos.router)
app.include_router(tarjetas.router)
app.include_router(operaciones.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root(request: Request):
    token = request.cookies.get("token")
    if not token or not verify_token(token):
        return FileResponse(str(STATIC_DIR / "login.html"))
    return FileResponse(str(STATIC_DIR / "index.html"))
