from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.auth import verify_password, create_token, hash_password, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Autenticacion"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.username == data.username).first()
    if not usuario or not verify_password(data.password, usuario.password_hash):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    if not usuario.activo:
        raise HTTPException(403, "Usuario desactivado")

    token = create_token(usuario.username, usuario.nombre)
    response = JSONResponse({"ok": True, "nombre": usuario.nombre, "token": token})
    response.set_cookie("token", token, httponly=False, samesite="lax", max_age=43200)
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
