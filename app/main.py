import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse

from app.auth import verify_token, get_current_user
from app.esquema import preparar_base
from app.routers import alumnos, tarjetas, operaciones, reportes, admin, cupones, config, proveedores, gastos, caja, conciliacion, cursos, cuotas, horario
from app.routers import auth as auth_router, usuarios, mantenimiento, importar_gastos, portal, consultas, cupones_siro, facturas_recibidas, planilla_siro, pedidos, escaneo

# En Vercel la base se prepara una vez por deploy (scripts/preparar_base.py),
# no en cada instancia que arranca.
if not os.getenv("VERCEL"):
    preparar_base()

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
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "worker-src 'self' blob:; "  # OCR de facturas escaneadas (Tesseract.js)
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https://*.supabase.co; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self' data: https://*.supabase.co https://cdn.jsdelivr.net; "  # Storage; datos del OCR (jsDelivr)
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def headers_seguridad(request: Request, call_next):
    """Agrega encabezados de seguridad y bloquea pedidos que modifican datos desde otros sitios (CSRF)."""
    if request.method not in METODOS_SEGUROS and request.url.path.startswith("/api/"):
        origen = request.headers.get("origin") or request.headers.get("referer") or ""
        host = request.headers.get("host", "")
        permitidos = {f"https://{host}", f"http://{host}", *_origenes}
        if origen and not any(origen == p or origen.startswith(p + "/") for p in permitidos):
            return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = CSP
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # datos personales: que no queden en caché
    elif request.url.path.startswith("/static/") or request.url.path in ("/", "/login", "/restablecer", "/portal", "/facturas", "/pedidos"):
        # Siempre revalidar (ETag): después de cada actualización nadie queda con CSS/JS viejos
        response.headers["Cache-Control"] = "no-cache"
    return response


# Todos los endpoints de la API (salvo login/logout) requieren sesion iniciada.
# Se aplica la dependencia a nivel de router para que cualquier endpoint nuevo
# quede protegido por defecto (defensa en profundidad).
_auth = [Depends(get_current_user)]


def _tarjeta_habilitada(request: Request):
    """La tarjeta APAI puede estar suspendida: se puede consultar el historial, pero no operar."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    from app.database import SessionLocal
    from app import config_util
    db = SessionLocal()
    try:
        activa = config_util.tarjeta_activa(db)
    finally:
        db.close()
    if not activa:
        from fastapi import HTTPException
        raise HTTPException(403, "La tarjeta APAI está suspendida temporalmente.")


_tarjeta = _auth + [Depends(_tarjeta_habilitada)]
app.include_router(auth_router.router)
app.include_router(alumnos.router, dependencies=_auth)
app.include_router(tarjetas.router, dependencies=_tarjeta)
app.include_router(operaciones.router, dependencies=_tarjeta)
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
app.include_router(horario.router, dependencies=_auth)
app.include_router(usuarios.router, dependencies=_auth)
app.include_router(mantenimiento.router, dependencies=_auth)
app.include_router(importar_gastos.router, dependencies=_auth)
app.include_router(consultas.router, dependencies=_auth)
app.include_router(planilla_siro.router, dependencies=_auth)  # antes que cupones_siro
app.include_router(cupones_siro.router, dependencies=_auth)
app.include_router(facturas_recibidas.router, dependencies=_auth)
app.include_router(facturas_recibidas.publico)  # portal público de facturas (sin cuenta)
app.include_router(pedidos.router, dependencies=_auth)
app.include_router(escaneo.router, dependencies=_auth)
app.include_router(pedidos.publico)  # formulario público de pedidos de materiales (sin cuenta)
# Portal de familias: tiene su propia sesión (cookie 'ptoken'), no usa la del personal
app.include_router(portal.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(str(STATIC_DIR / "logo.png"))


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    """Endpoint liviano para el keep-alive (responde a GET y HEAD; no toca la base ni requiere sesion)."""
    return {"ok": True}


# Versión publicada (commit de Vercel): la pantalla la consulta para avisar que hay una actualización
VERSION = (os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("VERCEL_DEPLOYMENT_ID") or "local")[:12]


@app.get("/api/version")
def version():
    return {"version": VERSION}


@app.get("/login")
def login_page():
    return FileResponse(str(STATIC_DIR / "login.html"))


@app.get("/portal")
def portal_page():
    return FileResponse(str(STATIC_DIR / "portal.html"))


@app.get("/facturas")
def facturas_page():
    """Portal público para que los proveedores suban sus facturas (sin cuenta)."""
    return FileResponse(str(STATIC_DIR / "facturas.html"))


@app.get("/pedidos")
def pedidos_page():
    """Formulario público para que profesores y personal pidan materiales o servicios (sin cuenta)."""
    return FileResponse(str(STATIC_DIR / "pedidos.html"))


@app.get("/restablecer")
def restablecer_page():
    return FileResponse(str(STATIC_DIR / "restablecer.html"))


@app.api_route("/", methods=["GET", "HEAD"])
def root(request: Request):
    token = request.cookies.get("token")
    if not token or not verify_token(token):
        return FileResponse(str(STATIC_DIR / "login.html"))
    return FileResponse(str(STATIC_DIR / "index.html"))
