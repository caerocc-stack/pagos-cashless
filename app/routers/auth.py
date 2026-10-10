import os
from datetime import timedelta
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario, ROLES
from app.auth import (verify_password, hash_password, create_token, create_token_2fa, verify_token,
                      get_current_user, poner_cookie_sesion, HASH_SENUELO)
from app.seguridad import (ip_cliente, auditar, segundos_bloqueo, registrar_fallo, limpiar_fallos,
                           error_password, cifrar, descifrar, nuevo_secreto_totp, verificar_totp,
                           uri_totp, qr_svg_data_uri, nuevos_codigos_respaldo, usar_codigo_respaldo,
                           crear_token_acceso, consumir_token_acceso)
from app.email_util import enviar_email, email_configurado
from app.tz import ahora_ar

router = APIRouter(prefix="/api/auth", tags=["Autenticacion"])

APP_URL = (os.getenv("APP_URL") or "https://pagos-cashless.vercel.app").rstrip("/")
MAX_FALLOS_CUENTA = 5      # por cuenta -> bloqueo de la cuenta
BLOQUEO_CUENTA_MIN = 15
MAX_FALLOS_IP = 15         # por IP (varias cuentas) -> bloqueo de la IP
VENTANA_IP_MIN = 15
MSG_CREDENCIALES = "Usuario/correo o contraseña incorrectos."


# ---------------------------------------------------------------- helpers

def _buscar(db: Session, identificador: str) -> Usuario | None:
    i = (identificador or "").strip().lower()
    if not i:
        return None
    return db.query(Usuario).filter(
        (func.lower(Usuario.username) == i) | (func.lower(Usuario.email) == i)
    ).first()


def _usuario_de(db: Session, user: dict) -> Usuario:
    u = db.get(Usuario, user["uid"])
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    return u


def _notificar(u: Usuario, asunto: str, mensaje_html: str):
    """Aviso de seguridad por correo (si el usuario tiene email). Nunca rompe el flujo."""
    if not u.email or not email_configurado():
        return
    try:
        enviar_email(u.email, f"APAI Pay · {asunto}", f"""
            <div style="font-family:Arial,sans-serif;max-width:520px;color:#1e293b">
              <h2 style="color:#15233b;margin:0 0 12px">APAI Pay</h2>
              <p>Hola {escape(u.nombre)},</p>
              {mensaje_html}
              <p style="color:#64748b;font-size:13px;margin-top:24px">
                Si no fuiste vos, cambiá tu contraseña de inmediato o avisá al administrador del sistema.
              </p>
            </div>""")
    except Exception as e:
        print("No se pudo enviar el aviso de seguridad:", e)


def _cuando_y_donde(request: Request) -> str:
    return (f"<p><b>Fecha:</b> {ahora_ar().strftime('%d/%m/%Y %H:%M')} (hora Argentina)<br>"
            f"<b>IP:</b> {escape(ip_cliente(request))}</p>")


def _respuesta_sesion(db: Session, u: Usuario, request: Request) -> JSONResponse:
    u.ultimo_ingreso = ahora_ar()
    auditar(db, "ingreso", u.username, "2FA" if u.totp_activo else "clave", request)
    db.commit()
    resp = JSONResponse({"ok": True, "nombre": u.nombre, "debe_cambiar_password": bool(u.debe_cambiar_password)})
    poner_cookie_sesion(resp, create_token(u))
    return resp


def _fallo_cuenta(db: Session, u: Usuario, request: Request, motivo: str):
    u.intentos_fallidos = (u.intentos_fallidos or 0) + 1
    auditar(db, "ingreso_fallido", u.username, motivo, request)
    if u.intentos_fallidos >= MAX_FALLOS_CUENTA:
        u.bloqueado_hasta = ahora_ar() + timedelta(minutes=BLOQUEO_CUENTA_MIN)
        u.intentos_fallidos = 0
        auditar(db, "cuenta_bloqueada", u.username, f"{MAX_FALLOS_CUENTA} intentos fallidos", request)
        _notificar(u, "Cuenta bloqueada temporalmente",
                   f"<p>Tu cuenta se bloqueó por {BLOQUEO_CUENTA_MIN} minutos después de "
                   f"{MAX_FALLOS_CUENTA} intentos fallidos de ingreso.</p>" + _cuando_y_donde(request))


# ---------------------------------------------------------------- login

class LoginRequest(BaseModel):
    usuario: str | None = None
    username: str | None = None  # compatibilidad con la pantalla anterior
    password: str


class Login2FARequest(BaseModel):
    desafio: str
    codigo: str


@router.post("/login")
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    espera = segundos_bloqueo(db, f"ip:{ip}", MAX_FALLOS_IP, VENTANA_IP_MIN)
    if espera:
        raise HTTPException(429, f"Demasiados intentos desde esta conexión. Esperá {(espera + 59) // 60} minuto(s).")

    u = _buscar(db, data.usuario or data.username or "")
    if u and u.bloqueado_hasta and u.bloqueado_hasta > ahora_ar():
        minutos = int((u.bloqueado_hasta - ahora_ar()).total_seconds() // 60) + 1
        raise HTTPException(429, f"La cuenta está bloqueada por intentos fallidos. Probá en {minutos} minuto(s).")

    ok = verify_password(data.password, u.password_hash if u else HASH_SENUELO)
    if not u or not ok or not u.activo:
        registrar_fallo(db, f"ip:{ip}")
        if u and not ok:
            _fallo_cuenta(db, u, request, "contraseña incorrecta")
        db.commit()
        raise HTTPException(401, MSG_CREDENCIALES)

    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    limpiar_fallos(db, f"ip:{ip}")
    if u.totp_activo:
        db.commit()
        return {"requiere_2fa": True, "desafio": create_token_2fa(u)}
    return _respuesta_sesion(db, u, request)


@router.post("/login/2fa")
def login_2fa(data: Login2FARequest, request: Request, db: Session = Depends(get_db)):
    payload = verify_token(data.desafio, "2fa")
    if not payload:
        raise HTTPException(401, "El tiempo para ingresar el código venció. Volvé a iniciar sesión.")
    u = db.get(Usuario, payload["uid"])
    if not u or not u.activo or not u.totp_activo or (u.version_sesion or 0) != payload.get("ver"):
        raise HTTPException(401, "Volvé a iniciar sesión.")
    if u.bloqueado_hasta and u.bloqueado_hasta > ahora_ar():
        raise HTTPException(429, "La cuenta está bloqueada por intentos fallidos. Probá más tarde.")

    secreto = descifrar(u.totp_secreto or "")
    paso = verificar_totp(secreto, data.codigo, u.totp_ultimo_paso) if secreto else None
    if paso is not None:
        u.totp_ultimo_paso = paso
    else:
        restantes = usar_codigo_respaldo(u.codigos_respaldo, data.codigo)
        if restantes is None:
            _fallo_cuenta(db, u, request, "código 2FA incorrecto")
            db.commit()
            raise HTTPException(401, "Código incorrecto. Revisá la app de autenticación.")
        u.codigos_respaldo = restantes
        auditar(db, "codigo_respaldo_usado", u.username, None, request)
        _notificar(u, "Ingreso con código de respaldo",
                   "<p>Se ingresó a tu cuenta usando un código de respaldo de la verificación en 2 pasos.</p>"
                   + _cuando_y_donde(request))
    u.intentos_fallidos = 0
    return _respuesta_sesion(db, u, request)


@router.post("/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("token", path="/", samesite="strict", secure=True, httponly=True)
    return response


@router.post("/cerrar-sesiones")
def cerrar_sesiones(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Cierra la sesión en todos los dispositivos (invalida todos los tokens emitidos)."""
    u = _usuario_de(db, user)
    u.version_sesion = (u.version_sesion or 0) + 1
    auditar(db, "cerrar_sesiones", u.username, None, request)
    db.commit()
    return logout()


@router.get("/me")
def me(user=Depends(get_current_user), db: Session = Depends(get_db)):
    u = _usuario_de(db, user)
    return {
        "username": u.username, "nombre": u.nombre, "email": u.email,
        "rol": u.rol, "rol_nombre": ROLES.get(u.rol, u.rol),
        "totp_activo": bool(u.totp_activo),
        "codigos_respaldo_restantes": len([h for h in (u.codigos_respaldo or "").split(";") if h]),
        "debe_cambiar_password": bool(u.debe_cambiar_password),
        "ultimo_ingreso": u.ultimo_ingreso.strftime("%d/%m/%Y %H:%M") if u.ultimo_ingreso else None,
    }


# ---------------------------------------------------------------- cuenta propia

class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


class ActualizarCuentaRequest(BaseModel):
    username: str | None = None
    nombre: str | None = None
    email: str | None = None


@router.post("/cambiar-password")
def cambiar_password(data: CambiarPasswordRequest, request: Request,
                     user=Depends(get_current_user), db: Session = Depends(get_db)):
    u = _usuario_de(db, user)
    if not verify_password(data.password_actual, u.password_hash):
        raise HTTPException(400, "La contraseña actual es incorrecta.")
    if (motivo := error_password(data.password_nueva)):
        raise HTTPException(400, motivo)
    if verify_password(data.password_nueva, u.password_hash):
        raise HTTPException(400, "La contraseña nueva tiene que ser distinta de la actual.")
    u.password_hash = hash_password(data.password_nueva)
    u.debe_cambiar_password = False
    u.version_sesion = (u.version_sesion or 0) + 1  # cierra las otras sesiones abiertas
    auditar(db, "cambio_password", u.username, None, request)
    _notificar(u, "Tu contraseña cambió", "<p>La contraseña de tu cuenta se cambió correctamente.</p>"
               + _cuando_y_donde(request))
    db.commit()
    resp = JSONResponse({"ok": True, "mensaje": "Contraseña actualizada"})
    poner_cookie_sesion(resp, create_token(u))
    return resp


@router.post("/actualizar-cuenta")
def actualizar_cuenta(data: ActualizarCuentaRequest, request: Request,
                      user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza el nombre de usuario, el nombre para mostrar y/o el correo."""
    u = _usuario_de(db, user)
    nuevo_username = (data.username or "").strip()
    nuevo_nombre = (data.nombre or "").strip()

    if nuevo_username and nuevo_username != u.username:
        if len(nuevo_username) < 3 or "@" in nuevo_username:
            raise HTTPException(400, "El usuario debe tener al menos 3 caracteres y no puede contener @.")
        if _buscar(db, nuevo_username):
            raise HTTPException(409, "Ese nombre de usuario ya está en uso.")
        u.username = nuevo_username
    if nuevo_nombre:
        u.nombre = nuevo_nombre[:100]
    if data.email is not None:
        email = data.email.strip().lower() or None
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            raise HTTPException(400, "El correo no es válido.")
        if email and email != (u.email or "") and _buscar(db, email):
            raise HTTPException(409, "Ese correo ya está en uso por otro usuario.")
        u.email = email
    auditar(db, "actualizar_cuenta", u.username, None, request)
    db.commit()

    resp = JSONResponse({"ok": True, "username": u.username, "nombre": u.nombre, "email": u.email,
                         "mensaje": "Cuenta actualizada"})
    poner_cookie_sesion(resp, create_token(u))
    return resp


# ---------------------------------------------------------------- 2FA

class CodigoRequest(BaseModel):
    codigo: str


class Desactivar2FARequest(BaseModel):
    password: str
    codigo: str


@router.post("/2fa/iniciar")
def iniciar_2fa(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Genera un secreto nuevo (todavia no activo) y devuelve el QR para escanear."""
    u = _usuario_de(db, user)
    if u.totp_activo:
        raise HTTPException(400, "La verificación en 2 pasos ya está activa.")
    secreto = nuevo_secreto_totp()
    u.totp_secreto = cifrar(secreto)
    u.totp_ultimo_paso = None
    db.commit()
    uri = uri_totp(secreto, u.email or u.username)
    return {"qr": qr_svg_data_uri(uri), "secreto": " ".join(secreto[i:i + 4] for i in range(0, len(secreto), 4))}


@router.post("/2fa/activar")
def activar_2fa(data: CodigoRequest, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    u = _usuario_de(db, user)
    secreto = descifrar(u.totp_secreto or "")
    if not secreto:
        raise HTTPException(400, "Primero generá el código QR.")
    paso = verificar_totp(secreto, data.codigo)
    if paso is None:
        raise HTTPException(400, "El código no coincide. Fijate que la hora del celular esté bien y probá con el código nuevo.")
    codigos, hashes = nuevos_codigos_respaldo()
    u.totp_activo = True
    u.totp_ultimo_paso = paso
    u.codigos_respaldo = hashes
    auditar(db, "2fa_activado", u.username, None, request)
    _notificar(u, "Verificación en 2 pasos activada",
               "<p>Activaste la verificación en 2 pasos. A partir de ahora vas a necesitar el código de tu app para ingresar.</p>"
               + _cuando_y_donde(request))
    db.commit()
    return {"ok": True, "codigos_respaldo": codigos}


@router.post("/2fa/desactivar")
def desactivar_2fa(data: Desactivar2FARequest, request: Request,
                   user=Depends(get_current_user), db: Session = Depends(get_db)):
    u = _usuario_de(db, user)
    if not u.totp_activo:
        raise HTTPException(400, "La verificación en 2 pasos no está activa.")
    if not verify_password(data.password, u.password_hash):
        raise HTTPException(400, "La contraseña es incorrecta.")
    secreto = descifrar(u.totp_secreto or "")
    if not (secreto and verificar_totp(secreto, data.codigo, u.totp_ultimo_paso) is not None) \
            and usar_codigo_respaldo(u.codigos_respaldo, data.codigo) is None:
        raise HTTPException(400, "El código es incorrecto.")
    u.totp_activo = False
    u.totp_secreto = None
    u.codigos_respaldo = None
    u.totp_ultimo_paso = None
    auditar(db, "2fa_desactivado", u.username, None, request)
    _notificar(u, "Verificación en 2 pasos DESACTIVADA",
               "<p>Se desactivó la verificación en 2 pasos de tu cuenta.</p>" + _cuando_y_donde(request))
    db.commit()
    return {"ok": True}


@router.post("/2fa/codigos-respaldo")
def regenerar_codigos(data: CodigoRequest, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    u = _usuario_de(db, user)
    secreto = descifrar(u.totp_secreto or "")
    paso = verificar_totp(secreto, data.codigo, u.totp_ultimo_paso) if (u.totp_activo and secreto) else None
    if paso is None:
        raise HTTPException(400, "El código es incorrecto.")
    u.totp_ultimo_paso = paso
    codigos, u.codigos_respaldo = nuevos_codigos_respaldo()
    auditar(db, "2fa_codigos_regenerados", u.username, None, request)
    db.commit()
    return {"codigos_respaldo": codigos}


# ---------------------------------------------------------------- olvide mi contrasena

class OlvideRequest(BaseModel):
    usuario: str


class RestablecerRequest(BaseModel):
    token: str
    password_nueva: str


@router.post("/olvide")
def olvide(data: OlvideRequest, request: Request, db: Session = Depends(get_db)):
    """Envía un link para crear una contraseña nueva. Responde siempre lo mismo
    (no revela si la cuenta existe)."""
    ip = ip_cliente(request)
    if segundos_bloqueo(db, f"olvide:{ip}", 5, 60):
        raise HTTPException(429, "Demasiados pedidos. Probá de nuevo en una hora.")
    registrar_fallo(db, f"olvide:{ip}")
    u = _buscar(db, data.usuario)
    if u and u.activo and u.email and email_configurado():
        token = crear_token_acceso(db, "reset_usuario", u.id, minutos=30)
        link = f"{APP_URL}/restablecer?t={token}"
        auditar(db, "pedido_reset", u.username, None, request)
        db.commit()
        try:
            enviar_email(u.email, "APAI Pay · Crear una contraseña nueva", f"""
                <div style="font-family:Arial,sans-serif;max-width:520px;color:#1e293b">
                  <h2 style="color:#15233b">APAI Pay</h2>
                  <p>Hola {escape(u.nombre)}, recibimos un pedido para cambiar tu contraseña.</p>
                  <p><a href="{link}" style="display:inline-block;background:#15233b;color:#fff;padding:12px 22px;
                     border-radius:8px;text-decoration:none;font-weight:bold">Crear contraseña nueva</a></p>
                  <p style="color:#64748b;font-size:13px">El link vence en 30 minutos y sirve una sola vez.
                  Si no lo pediste, ignorá este correo: tu contraseña no cambia.</p>
                </div>""")
        except Exception as e:
            print("No se pudo enviar el correo de recuperación:", e)
    else:
        db.commit()
    return {"ok": True, "mensaje": "Si los datos corresponden a una cuenta con correo, te enviamos un link para crear una contraseña nueva."}


@router.post("/restablecer")
def restablecer(data: RestablecerRequest, request: Request, db: Session = Depends(get_db)):
    if (motivo := error_password(data.password_nueva)):
        raise HTTPException(400, motivo)
    t = consumir_token_acceso(db, data.token, "reset_usuario")
    u = db.get(Usuario, t.ref_id) if t else None
    if not u or not u.activo:
        raise HTTPException(400, "El link no es válido o ya venció. Pedí uno nuevo.")
    u.password_hash = hash_password(data.password_nueva)
    u.debe_cambiar_password = False
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    u.version_sesion = (u.version_sesion or 0) + 1
    auditar(db, "reset_password", u.username, None, request)
    _notificar(u, "Tu contraseña cambió", "<p>Se creó una contraseña nueva desde el link de recuperación.</p>"
               + _cuando_y_donde(request))
    db.commit()
    return {"ok": True, "mensaje": "Listo. Ya podés ingresar con tu contraseña nueva."}
