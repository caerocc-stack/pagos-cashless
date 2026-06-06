from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import get_db
from app.models.usuario import Usuario
from app.auth import verify_password, create_token, hash_password, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Autenticacion"])

# --- Proteccion anti fuerza bruta (en memoria) ---
MAX_INTENTOS = 5
BLOQUEO_MINUTOS = 10
_intentos_fallidos: dict[str, list] = {}  # ip -> [datetime, datetime, ...]


def _ip_cliente(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def _esta_bloqueado(ip: str) -> int:
    """Devuelve segundos restantes de bloqueo, o 0 si no esta bloqueado."""
    ahora = datetime.utcnow()
    intentos = _intentos_fallidos.get(ip, [])
    # Filtrar intentos dentro de la ventana de bloqueo
    recientes = [t for t in intentos if ahora - t < timedelta(minutes=BLOQUEO_MINUTOS)]
    _intentos_fallidos[ip] = recientes
    if len(recientes) >= MAX_INTENTOS:
        mas_viejo = min(recientes)
        restante = timedelta(minutes=BLOQUEO_MINUTOS) - (ahora - mas_viejo)
        return max(1, int(restante.total_seconds()))
    return 0


def _registrar_fallo(ip: str):
    _intentos_fallidos.setdefault(ip, []).append(datetime.utcnow())


def _limpiar_intentos(ip: str):
    _intentos_fallidos.pop(ip, None)


class LoginRequest(BaseModel):
    username: str
    password: str


class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


class ActualizarCuentaRequest(BaseModel):
    username: str | None = None
    nombre: str | None = None


@router.post("/login")
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _ip_cliente(request)

    bloqueo = _esta_bloqueado(ip)
    if bloqueo:
        minutos = (bloqueo + 59) // 60
        raise HTTPException(
            429,
            f"Demasiados intentos fallidos. Espera {minutos} minuto(s) e intenta de nuevo.",
        )

    usuario = db.query(Usuario).filter(Usuario.username == data.username).first()
    if not usuario or not verify_password(data.password, usuario.password_hash):
        _registrar_fallo(ip)
        restantes = MAX_INTENTOS - len(_intentos_fallidos.get(ip, []))
        msg = "Usuario o contraseña incorrectos"
        if 0 < restantes <= 2:
            msg += f". Te quedan {restantes} intento(s) antes del bloqueo."
        raise HTTPException(401, msg)
    if not usuario.activo:
        raise HTTPException(403, "Usuario desactivado")

    _limpiar_intentos(ip)
    token = create_token(usuario.username, usuario.nombre)
    response = JSONResponse({"ok": True, "nombre": usuario.nombre, "token": token})
    response.set_cookie("token", token, httponly=False, samesite="lax", max_age=43200, secure=True)
    return response


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("token", path="/", samesite="lax")
    return response


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"username": user["sub"], "nombre": user["nombre"]}


@router.post("/cambiar-password")
def cambiar_password(data: CambiarPasswordRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.username == user["sub"]).first()
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")
    if not verify_password(data.password_actual, usuario.password_hash):
        raise HTTPException(400, "Contraseña actual incorrecta")
    usuario.password_hash = hash_password(data.password_nueva)
    db.commit()
    return {"ok": True, "mensaje": "Contraseña actualizada"}


@router.post("/actualizar-cuenta")
def actualizar_cuenta(data: ActualizarCuentaRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza el nombre de usuario (login) y/o el nombre para mostrar."""
    usuario = db.query(Usuario).filter(Usuario.username == user["sub"]).first()
    if not usuario:
        raise HTTPException(404, "Usuario no encontrado")

    nuevo_username = (data.username or "").strip()
    nuevo_nombre = (data.nombre or "").strip()

    if nuevo_username and nuevo_username != usuario.username:
        if len(nuevo_username) < 3:
            raise HTTPException(400, "El nombre de usuario debe tener al menos 3 caracteres")
        existe = db.query(Usuario).filter(Usuario.username == nuevo_username).first()
        if existe:
            raise HTTPException(409, "Ese nombre de usuario ya está en uso")
        usuario.username = nuevo_username

    if nuevo_nombre:
        usuario.nombre = nuevo_nombre

    db.commit()

    # Emitir un token nuevo para que la sesion siga valida con los datos actualizados
    token = create_token(usuario.username, usuario.nombre)
    response = JSONResponse({
        "ok": True,
        "username": usuario.username,
        "nombre": usuario.nombre,
        "mensaje": "Cuenta actualizada",
    })
    response.set_cookie("token", token, httponly=False, samesite="lax", max_age=43200, secure=True)
    return response
