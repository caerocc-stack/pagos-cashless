import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario

# Clave para firmar los tokens. Debe definirse en el entorno (SECRET_KEY).
# Si falta, se genera una aleatoria por proceso: es segura, pero las sesiones
# se invalidan al reiniciar (obliga a volver a iniciar sesion).
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
if not os.getenv("SECRET_KEY"):
    print("ADVERTENCIA: SECRET_KEY no definida. Usando una clave temporal. "
          "Cargá SECRET_KEY en el entorno para mantener las sesiones entre reinicios.")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 12
METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


# Hash fijo para comparar cuando el usuario no existe: el login tarda lo mismo
# exista o no la cuenta (no se puede averiguar que usuarios existen midiendo tiempos).
HASH_SENUELO = hash_password(secrets.token_hex(16))


def _firmar(payload: dict, minutos: int) -> str:
    payload = {**payload, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutos)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_token(usuario: Usuario) -> str:
    """Token de sesion del personal (cookie 'token')."""
    return _firmar({"typ": "sesion", "uid": usuario.id, "sub": usuario.username,
                    "nombre": usuario.nombre, "ver": usuario.version_sesion or 0},
                   TOKEN_EXPIRE_HOURS * 60)


def create_token_2fa(usuario: Usuario) -> str:
    """Token corto que habilita SOLO el paso del codigo 2FA (5 minutos)."""
    return _firmar({"typ": "2fa", "uid": usuario.id, "ver": usuario.version_sesion or 0}, 5)


def verify_token(token: str, tipo: str = "sesion") -> dict | None:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    return data if data.get("typ") == tipo else None


def poner_cookie_sesion(response: Response, token: str):
    response.set_cookie("token", token, httponly=True, samesite="strict", secure=True,
                        max_age=TOKEN_EXPIRE_HOURS * 3600, path="/")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """Dependencia de toda la API del personal: valida token, usuario activo, version de
    sesion (cambio de clave = cierra las demas sesiones) y permisos del rol."""
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(401, "No autenticado")
    payload = verify_token(token)
    if not payload or "uid" not in payload:
        raise HTTPException(401, "Sesión vencida. Volvé a iniciar sesión.")
    usuario = db.get(Usuario, payload["uid"])
    if not usuario or not usuario.activo or (usuario.version_sesion or 0) != payload.get("ver"):
        raise HTTPException(401, "Sesión vencida. Volvé a iniciar sesión.")

    ruta = request.url.path
    libre = ruta.startswith("/api/auth/")  # cuenta propia: clave, 2FA, salir
    if usuario.debe_cambiar_password and not libre:
        raise HTTPException(403, "Tenés que cambiar tu contraseña antes de continuar.")
    if usuario.rol == "lectura" and request.method not in METODOS_LECTURA and not libre:
        raise HTTPException(403, "Tu usuario es de solo lectura: no puede modificar datos.")

    return {"uid": usuario.id, "sub": usuario.username, "nombre": usuario.nombre,
            "rol": usuario.rol, "email": usuario.email}


def requiere_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["rol"] != "admin":
        raise HTTPException(403, "Solo un administrador puede hacer esto.")
    return user


def solo_nombres(nombre_completo: str) -> str:
    """Devuelve solo los nombres de pila (quita la ultima palabra = apellido)."""
    if not nombre_completo:
        return ""
    partes = nombre_completo.strip().split()
    if len(partes) <= 1:
        return partes[0] if partes else ""
    return " ".join(partes[:-1])


def crear_usuario_inicial(db: Session):
    """Crea el usuario admin si no existe ninguno. La clave inicial sale de
    ADMIN_PASSWORD (o 'apai2024' por defecto) y se obliga a cambiarla al primer ingreso."""
    if db.query(Usuario).count() == 0:
        clave = os.getenv("ADMIN_PASSWORD", "apai2024")
        admin = Usuario(
            username=os.getenv("ADMIN_USER", "admin"),
            password_hash=hash_password(clave),
            nombre="Administrador APAI",
            rol="admin",
            debe_cambiar_password=True,
        )
        db.add(admin)
        db.commit()
        print(">>> Usuario administrador inicial creado. Cambiá la contraseña al primer ingreso.")
