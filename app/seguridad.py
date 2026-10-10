"""
Utilidades de seguridad compartidas: IP real del cliente, limite de intentos,
auditoria, politica de contrasenas, 2FA (TOTP, RFC 6238), codigos de respaldo
y links de un solo uso.
"""
import os
import re
import hmac
import time
import base64
import struct
import hashlib
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request
from sqlalchemy.orm import Session

from app.tz import ahora_ar
from app.models.seguridad import IntentoLogin, TokenAcceso, Auditoria

EMISOR_2FA = "APAI Pay"


# ---------------------------------------------------------------- red

def ip_cliente(request: Request) -> str:
    """IP real del visitante. Vercel pone la verdadera en x-vercel-forwarded-for / x-real-ip."""
    for h in ("x-vercel-forwarded-for", "x-real-ip", "x-forwarded-for"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()[:60]
    return request.client.host if request.client else "desconocida"


# ---------------------------------------------------------------- auditoria

def auditar(db: Session, accion: str, usuario: str | None = None, detalle: str | None = None,
            request: Request | None = None):
    db.add(Auditoria(
        accion=accion, usuario=(usuario or "")[:150] or None,
        detalle=(detalle or "")[:400] or None,
        ip=ip_cliente(request) if request else None,
    ))


# ---------------------------------------------------------------- limite de intentos

def segundos_bloqueo(db: Session, clave: str, maximo: int, minutos: int) -> int:
    """Si 'clave' tuvo >= maximo fallos en los ultimos 'minutos', devuelve los segundos que faltan."""
    desde = ahora_ar() - timedelta(minutes=minutos)
    fechas = [f for (f,) in db.query(IntentoLogin.fecha)
              .filter(IntentoLogin.clave == clave, IntentoLogin.fecha >= desde)
              .order_by(IntentoLogin.fecha).all()]
    if len(fechas) < maximo:
        return 0
    libera = fechas[-maximo] + timedelta(minutes=minutos)
    return max(1, int((libera - ahora_ar()).total_seconds()))


def registrar_fallo(db: Session, clave: str):
    db.add(IntentoLogin(clave=clave[:120]))
    # Limpieza ocasional de registros viejos
    if secrets.randbelow(20) == 0:
        db.query(IntentoLogin).filter(IntentoLogin.fecha < ahora_ar() - timedelta(days=2)).delete()


def limpiar_fallos(db: Session, clave: str):
    db.query(IntentoLogin).filter(IntentoLogin.clave == clave).delete()


# ---------------------------------------------------------------- contrasenas

_COMUNES = {"password", "contrasena", "contraseña", "12345678", "123456789", "1234567890",
            "qwerty123", "apai2024", "apai2025", "apai2026", "admin1234", "inac1234"}


def error_password(password: str, minimo: int = 10) -> str | None:
    """Devuelve el motivo si la contrasena no cumple la politica, o None si es valida."""
    p = password or ""
    if len(p) < minimo:
        return f"La contraseña debe tener al menos {minimo} caracteres."
    if len(p) > 128:
        return "La contraseña es demasiado larga."
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", p) or not re.search(r"\d", p):
        return "La contraseña debe combinar letras y números."
    if p.lower() in _COMUNES:
        return "Esa contraseña es demasiado común. Elegí otra."
    return None


# ---------------------------------------------------------------- 2FA (TOTP)

def _fernet() -> Fernet:
    base = os.getenv("SECRET_KEY") or ""
    if not base:
        raise RuntimeError("Falta SECRET_KEY: es necesaria para cifrar los secretos de 2FA.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("totp:" + base).encode()).digest()))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(texto: str) -> str | None:
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def nuevo_secreto_totp() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _codigo_totp(secreto: str, paso: int) -> str:
    clave = base64.b32decode(secreto + "=" * (-len(secreto) % 8), casefold=True)
    h = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    n = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{n:06d}"


def verificar_totp(secreto: str, codigo: str, ultimo_paso: int | None = None) -> int | None:
    """Valida el codigo de 6 digitos (tolera +-30 s). Devuelve el paso usado, o None.
    Rechaza un paso ya usado (no se puede reutilizar un codigo interceptado)."""
    codigo = re.sub(r"\D", "", codigo or "")
    if len(codigo) != 6:
        return None
    actual = int(time.time()) // 30
    for paso in (actual - 1, actual, actual + 1):
        if ultimo_paso is not None and paso <= ultimo_paso:
            continue
        if hmac.compare_digest(_codigo_totp(secreto, paso), codigo):
            return paso
    return None


def uri_totp(secreto: str, cuenta: str) -> str:
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(EMISOR_2FA)}:{quote(cuenta)}"
            f"?secret={secreto}&issuer={quote(EMISOR_2FA)}&digits=6&period=30")


def qr_svg_data_uri(texto: str) -> str:
    import segno
    return segno.make(texto, error="m").svg_data_uri(scale=5, border=2)


# ---------------------------------------------------------------- codigos de respaldo

def _hash_codigo(c: str) -> str:
    return hashlib.sha256(re.sub(r"[^A-Z0-9]", "", c.upper()).encode()).hexdigest()


def nuevos_codigos_respaldo(cantidad: int = 8) -> tuple[list[str], str]:
    """Devuelve (codigos en claro para mostrar UNA vez, hashes para guardar)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codigos = ["".join(secrets.choice(alfabeto) for _ in range(4)) + "-" +
               "".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(cantidad)]
    return codigos, ";".join(_hash_codigo(c) for c in codigos)


def usar_codigo_respaldo(guardados: str | None, codigo: str) -> str | None:
    """Si el codigo es valido devuelve la lista actualizada (sin ese codigo); si no, None."""
    hashes = [h for h in (guardados or "").split(";") if h]
    h = _hash_codigo(codigo or "")
    if h not in hashes:
        return None
    hashes.remove(h)
    return ";".join(hashes)


# ---------------------------------------------------------------- links de un solo uso

def _hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def crear_token_acceso(db: Session, tipo: str, ref_id: int, minutos: int = 30) -> str:
    # Un link nuevo invalida los anteriores del mismo tipo y destinatario
    db.query(TokenAcceso).filter(TokenAcceso.tipo == tipo, TokenAcceso.ref_id == ref_id,
                                 TokenAcceso.usado.is_(False)).update({"usado": True})
    token = secrets.token_urlsafe(32)
    db.add(TokenAcceso(token_hash=_hash_token(token), tipo=tipo, ref_id=ref_id,
                       expira=ahora_ar() + timedelta(minutes=minutos)))
    return token


def consumir_token_acceso(db: Session, token: str, tipo: str, marcar_usado: bool = True) -> TokenAcceso | None:
    t = db.query(TokenAcceso).filter(TokenAcceso.token_hash == _hash_token(token or ""),
                                     TokenAcceso.tipo == tipo).first()
    if not t or t.usado or t.expira < ahora_ar():
        return None
    if marcar_usado:
        t.usado = True
    return t
