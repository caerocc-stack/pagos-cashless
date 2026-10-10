"""Gestion de usuarios del personal y auditoria (solo administradores)."""
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import requiere_admin, hash_password
from app.models.usuario import Usuario, ROLES
from app.models.seguridad import Auditoria
from app.seguridad import auditar, error_password, crear_token_acceso
from app.email_util import enviar_email, email_configurado
from app.routers.auth import APP_URL
from app.tz import ahora_ar

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"], dependencies=[Depends(requiere_admin)])


def _fmt(dt):
    return dt.strftime("%d/%m/%Y %H:%M") if dt else None


def _dto(u: Usuario) -> dict:
    return {
        "id": u.id, "username": u.username, "nombre": u.nombre, "email": u.email,
        "rol": u.rol, "rol_nombre": ROLES.get(u.rol, u.rol), "activo": bool(u.activo),
        "totp_activo": bool(u.totp_activo), "debe_cambiar_password": bool(u.debe_cambiar_password),
        "bloqueado": bool(u.bloqueado_hasta and u.bloqueado_hasta > ahora_ar()),
        "ultimo_ingreso": _fmt(u.ultimo_ingreso), "creado": _fmt(u.created_at),
    }


def _admins_activos(db: Session, excepto: int | None = None) -> int:
    q = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.activo.is_(True))
    if excepto:
        q = q.filter(Usuario.id != excepto)
    return q.count()


def _existe(db: Session, valor: str, excepto: int | None = None) -> bool:
    v = valor.strip().lower()
    q = db.query(Usuario).filter((func.lower(Usuario.username) == v) | (func.lower(Usuario.email) == v))
    if excepto:
        q = q.filter(Usuario.id != excepto)
    return q.first() is not None


def _enviar_link(db: Session, u: Usuario, bienvenida: bool) -> bool:
    if not u.email or not email_configurado():
        return False
    token = crear_token_acceso(db, "reset_usuario", u.id, minutos=60 * 48 if bienvenida else 60)
    link = f"{APP_URL}/restablecer?t={token}"
    titulo = "Te dieron acceso a APAI Pay" if bienvenida else "Crear una contraseña nueva"
    texto = (f"Te crearon un usuario <b>{escape(ROLES.get(u.rol, u.rol))}</b> en el sistema de gestión de APAI. "
             f"Tu usuario es <b>{escape(u.username)}</b> (también podés entrar con este correo)."
             if bienvenida else "El administrador del sistema te envió un link para crear una contraseña nueva.")
    vence = "48 horas" if bienvenida else "1 hora"
    db.commit()
    try:
        enviar_email(u.email, f"APAI Pay · {titulo}", f"""
            <div style="font-family:Arial,sans-serif;max-width:520px;color:#1e293b">
              <h2 style="color:#15233b">APAI Pay</h2>
              <p>Hola {escape(u.nombre)},</p><p>{texto}</p>
              <p><a href="{link}" style="display:inline-block;background:#15233b;color:#fff;padding:12px 22px;
                 border-radius:8px;text-decoration:none;font-weight:bold">Crear mi contraseña</a></p>
              <p style="color:#64748b;font-size:13px">El link vence en {vence} y sirve una sola vez.
              Te recomendamos activar la verificación en 2 pasos desde "Mi cuenta".</p>
            </div>""")
        return True
    except Exception as e:
        print("No se pudo enviar el link:", e)
        return False


class UsuarioCrear(BaseModel):
    nombre: str
    username: str
    email: str | None = None
    rol: str = "lectura"
    password: str | None = None  # si no se indica, se envia un link por correo


class UsuarioEditar(BaseModel):
    nombre: str | None = None
    email: str | None = None
    rol: str | None = None
    activo: bool | None = None


class ClaveTemporal(BaseModel):
    password: str


@router.get("/")
def listar(db: Session = Depends(get_db)):
    return [_dto(u) for u in db.query(Usuario).order_by(Usuario.activo.desc(), Usuario.nombre).all()]


@router.get("/roles")
def roles():
    return [{"id": k, "nombre": v} for k, v in ROLES.items()]


@router.post("/")
def crear(data: UsuarioCrear, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    nombre, username = data.nombre.strip(), data.username.strip()
    email = (data.email or "").strip().lower() or None
    if not nombre or len(username) < 3 or "@" in username:
        raise HTTPException(400, "Completá el nombre y un usuario de al menos 3 caracteres (sin @).")
    if data.rol not in ROLES:
        raise HTTPException(400, "Rol inválido.")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        raise HTTPException(400, "El correo no es válido.")
    if _existe(db, username) or (email and _existe(db, email)):
        raise HTTPException(409, "Ya existe un usuario con ese nombre de usuario o correo.")
    if data.password:
        if (motivo := error_password(data.password)):
            raise HTTPException(400, motivo)
        clave = data.password
    elif email:
        import secrets
        clave = secrets.token_urlsafe(24)  # inutilizable: el usuario elige la suya con el link
    else:
        raise HTTPException(400, "Indicá un correo (para enviarle el link) o una contraseña temporal.")

    u = Usuario(nombre=nombre[:100], username=username, email=email, rol=data.rol,
                password_hash=hash_password(clave), debe_cambiar_password=bool(data.password))
    db.add(u)
    db.flush()
    auditar(db, "usuario_creado", admin["sub"], f"{username} ({ROLES[data.rol]})", request)
    db.commit()
    enviado = False if data.password else _enviar_link(db, u, bienvenida=True)
    msg = "Usuario creado."
    if not data.password:
        msg += " Le enviamos un correo para que cree su contraseña." if enviado else \
               " No se pudo enviar el correo: generale una contraseña temporal."
    else:
        msg += " Va a tener que cambiar la contraseña en su primer ingreso."
    return {"ok": True, "mensaje": msg, "usuario": _dto(u)}


@router.put("/{uid}")
def editar(uid: int, data: UsuarioEditar, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    pierde_admin = (data.rol and data.rol != "admin" and u.rol == "admin") or (data.activo is False and u.activo)
    if pierde_admin and u.rol == "admin" and _admins_activos(db, excepto=u.id) == 0:
        raise HTTPException(400, "Tiene que quedar al menos un administrador activo.")
    if u.id == admin["uid"] and pierde_admin:
        raise HTTPException(400, "No podés quitarte el rol de administrador ni desactivarte a vos mismo.")
    cambios = []
    if data.nombre and data.nombre.strip():
        u.nombre = data.nombre.strip()[:100]
    if data.email is not None:
        email = data.email.strip().lower() or None
        if email and _existe(db, email, excepto=u.id):
            raise HTTPException(409, "Ese correo ya está en uso.")
        u.email = email
    if data.rol and data.rol != u.rol:
        if data.rol not in ROLES:
            raise HTTPException(400, "Rol inválido.")
        cambios.append(f"rol {ROLES.get(u.rol)} → {ROLES[data.rol]}")
        u.rol = data.rol
        u.version_sesion = (u.version_sesion or 0) + 1  # que vuelva a entrar con el permiso nuevo
    if data.activo is not None and data.activo != u.activo:
        cambios.append("activado" if data.activo else "desactivado")
        u.activo = data.activo
        u.version_sesion = (u.version_sesion or 0) + 1
    auditar(db, "usuario_editado", admin["sub"], f"{u.username}: {', '.join(cambios) or 'datos'}", request)
    db.commit()
    return {"ok": True, "usuario": _dto(u)}


@router.post("/{uid}/enviar-link")
def enviar_link(uid: int, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u or not u.email:
        raise HTTPException(400, "El usuario no tiene correo cargado.")
    auditar(db, "link_reset_enviado", admin["sub"], u.username, request)
    if not _enviar_link(db, u, bienvenida=False):
        raise HTTPException(502, "No se pudo enviar el correo.")
    return {"ok": True, "mensaje": f"Link enviado a {u.email}."}


@router.post("/{uid}/clave-temporal")
def clave_temporal(uid: int, data: ClaveTemporal, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    if (motivo := error_password(data.password)):
        raise HTTPException(400, motivo)
    u.password_hash = hash_password(data.password)
    u.debe_cambiar_password = True
    u.bloqueado_hasta = None
    u.intentos_fallidos = 0
    u.version_sesion = (u.version_sesion or 0) + 1
    auditar(db, "clave_temporal", admin["sub"], u.username, request)
    db.commit()
    return {"ok": True, "mensaje": "Contraseña temporal asignada. Deberá cambiarla al ingresar."}


@router.post("/{uid}/reiniciar-2fa")
def reiniciar_2fa(uid: int, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    """Para cuando alguien perdió el celular: desactiva su 2FA para que lo vuelva a configurar."""
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    u.totp_activo = False
    u.totp_secreto = None
    u.codigos_respaldo = None
    u.totp_ultimo_paso = None
    u.version_sesion = (u.version_sesion or 0) + 1
    auditar(db, "2fa_reiniciado", admin["sub"], u.username, request)
    db.commit()
    return {"ok": True, "mensaje": "Verificación en 2 pasos reiniciada. El usuario debe volver a activarla."}


@router.post("/{uid}/desbloquear")
def desbloquear(uid: int, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    u.bloqueado_hasta = None
    u.intentos_fallidos = 0
    auditar(db, "usuario_desbloqueado", admin["sub"], u.username, request)
    db.commit()
    return {"ok": True}


@router.post("/{uid}/cerrar-sesiones")
def cerrar_sesiones(uid: int, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    u.version_sesion = (u.version_sesion or 0) + 1
    auditar(db, "sesiones_cerradas", admin["sub"], u.username, request)
    db.commit()
    return {"ok": True, "mensaje": "Se cerraron todas las sesiones de ese usuario."}


@router.get("/auditoria")
def auditoria(limite: int = 200, db: Session = Depends(get_db)):
    filas = db.query(Auditoria).order_by(Auditoria.fecha.desc()).limit(min(limite, 1000)).all()
    return [{"fecha": _fmt(a.fecha), "usuario": a.usuario, "accion": a.accion,
             "detalle": a.detalle, "ip": a.ip} for a in filas]
