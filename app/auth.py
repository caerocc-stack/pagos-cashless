import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
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


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(username: str, nombre: str) -> str:
    payload = {
        "sub": username,
        "nombre": nombre,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def get_current_user(request: Request):
    """Dependencia para proteger endpoints de la API."""
    token = request.cookies.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(401, "No autenticado")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "Token invalido o expirado")
    return payload


def crear_usuario_inicial(db: Session):
    """Crea el usuario admin si no existe ninguno. La clave inicial sale de
    ADMIN_PASSWORD (o 'apai2024' por defecto, que DEBE cambiarse al primer ingreso)."""
    if db.query(Usuario).count() == 0:
        clave = os.getenv("ADMIN_PASSWORD", "apai2024")
        admin = Usuario(
            username=os.getenv("ADMIN_USER", "admin"),
            password_hash=hash_password(clave),
            nombre="Administrador APAI",
        )
        db.add(admin)
        db.commit()
        print(">>> Usuario administrador inicial creado. Cambiá la contraseña al primer ingreso.")
