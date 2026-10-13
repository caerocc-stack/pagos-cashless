"""
Portal de familias (padres): ingreso con el correo de los cupones, estado de cuenta,
tarjeta, legajo, cupones y consultas a la Asociación.

Seguridad:
- Clave inicial = DNI de cualquiera de los hijos; se obliga a cambiarla en el primer ingreso.
- Bloqueo de la cuenta por 15 min tras 5 intentos fallidos + límite por IP.
- Recuperación con link de un solo uso enviado al correo (nunca vuelve al DNI).
- Sesión en cookie propia (HttpOnly, Secure, SameSite=Strict), separada de la del personal.
- Cada pedido verifica que el alumno pertenezca a la cuenta (no se puede ver a otro alumno).
"""
import re
import os
from types import SimpleNamespace
from datetime import timedelta, datetime, timezone
from decimal import Decimal
from html import escape

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import SECRET_KEY, ALGORITHM, hash_password, verify_password, HASH_SENUELO, requiere_admin
from app.models.usuario import Usuario
from app.models.alumno import Alumno
from app.models.saldo import Saldo
from app.models.movimiento import Movimiento
from app.models.pago_cuota import PagoCuota
from app.models.curso import Curso
from app.models.portal import CuentaPadre, CuponEnviado, Consulta, MensajeConsulta
from app.routers.cuotas import detalle_alumno
from app.routers.cupones_siro import cupones_vigentes, ultimo_codigo_pago
from app.seguridad import (ip_cliente, auditar, segundos_bloqueo, registrar_fallo, limpiar_fallos, error_password,
                           crear_token_acceso, consumir_token_acceso)
from app.storage_util import crear_subida_firmada
from app import consultas_util as cu, config_util
from app.tz import ahora_ar

router = APIRouter(prefix="/api/portal", tags=["Portal de familias"])

APP_URL = (os.getenv("APP_URL") or "https://pagos-cashless.vercel.app").rstrip("/")
SESION_HORAS = 8
VISTA_MINUTOS = 30
MAX_FALLOS, BLOQUEO_MIN = 5, 15
MSG_CRED = "Correo o contraseña incorrectos."


# ---------------------------------------------------------------- helpers

def _norm_email(e: str | None) -> str:
    return (e or "").strip().lower()


def emails_de(texto: str | None) -> set[str]:
    """El campo email del alumno puede traer varios correos separados por ; , o espacios."""
    return {_norm_email(x) for x in re.split(r"[;,\s/]+", texto or "") if "@" in x}


def hijos_de(db: Session, email: str) -> list[Alumno]:
    email = _norm_email(email)
    if not email:
        return []
    candidatos = db.query(Alumno).filter(Alumno.activo.is_(True), func.lower(Alumno.email).contains(email)).all()
    return sorted([a for a in candidatos if email in emails_de(a.email)], key=lambda a: (a.apellido, a.nombre))


def _solo_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _token(c: CuentaPadre) -> str:
    return jwt.encode({"typ": "padre", "cid": c.id, "ver": c.version_sesion or 0,
                       "exp": datetime.now(timezone.utc) + timedelta(hours=SESION_HORAS)}, SECRET_KEY, algorithm=ALGORITHM)


def _cookie(resp: Response, token: str):
    resp.set_cookie("ptoken", token, httponly=True, secure=True, samesite="strict", max_age=SESION_HORAS * 3600, path="/")


def get_padre(request: Request, db: Session = Depends(get_db)) -> CuentaPadre:
    tok = request.cookies.get("ptoken")
    try:
        data = jwt.decode(tok or "", SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Tu sesión venció. Ingresá de nuevo.")
    if data.get("typ") == "padre_vista":
        return _vista_admin(request, db, data)
    c = db.get(CuentaPadre, data.get("cid")) if data.get("typ") == "padre" else None
    if not c or not c.activo or (c.version_sesion or 0) != data.get("ver"):
        raise HTTPException(401, "Tu sesión venció. Ingresá de nuevo.")
    libre = request.url.path in ("/api/portal/me", "/api/portal/cambiar-password", "/api/portal/logout")
    if c.debe_cambiar_password and not libre:
        raise HTTPException(403, "Antes de continuar tenés que crear tu contraseña personal.")
    return c


def _vista_admin(request: Request, db: Session, data: dict):
    """Vista previa del portal para un administrador: ve exactamente lo mismo que la familia,
    pero en solo lectura (no envía consultas, no cambia claves, no marca mensajes como leídos)."""
    admin = db.get(Usuario, data.get("uid"))
    if (not admin or not admin.activo or admin.rol != "admin"
            or (admin.version_sesion or 0) != data.get("ver")):
        raise HTTPException(401, "La vista previa venció. Abrila de nuevo desde el sistema.")
    if request.method not in ("GET", "HEAD") and request.url.path != "/api/portal/logout":
        raise HTTPException(403, "Estás en vista previa: no se pueden enviar consultas ni cambiar datos de la familia.")
    email = _norm_email(data.get("email"))
    c = db.query(CuentaPadre).filter(CuentaPadre.email == email).first()
    # Si la familia todavía no ingresó nunca, no tiene cuenta: id 0 no coincide con ninguna consulta
    return SimpleNamespace(id=c.id if c else 0, email=email, activo=True, debe_cambiar_password=False,
                           vista_admin=admin.nombre)


def _es_vista(c) -> bool:
    return bool(getattr(c, "vista_admin", None))


def _hijo(db: Session, cuenta: CuentaPadre, alumno_id: int) -> Alumno:
    """Devuelve el alumno solo si pertenece a la cuenta (evita ver datos de otros alumnos)."""
    for a in hijos_de(db, cuenta.email):
        if a.id == alumno_id:
            return a
    raise HTTPException(404, "Alumno no encontrado.")


def _cuando(request: Request) -> str:
    return f"<p><b>Fecha:</b> {ahora_ar():%d/%m/%Y %H:%M} (hora Argentina) · <b>IP:</b> {escape(ip_cliente(request))}</p>"


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


# ---------------------------------------------------------------- ingreso

class Login(BaseModel):
    email: str
    password: str


class CambioClave(BaseModel):
    password_actual: str
    password_nueva: str


class Olvide(BaseModel):
    email: str


class Restablecer(BaseModel):
    token: str
    password_nueva: str


@router.post("/login")
def login(data: Login, request: Request, db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    if (espera := segundos_bloqueo(db, f"portal-ip:{ip}", 20, 15)):
        raise HTTPException(429, f"Demasiados intentos. Esperá {(espera + 59) // 60} minuto(s) y probá de nuevo.")
    email = _norm_email(data.email)
    cuenta = db.query(CuentaPadre).filter(CuentaPadre.email == email).first() if email else None
    if cuenta and cuenta.bloqueado_hasta and cuenta.bloqueado_hasta > ahora_ar():
        minutos = int((cuenta.bloqueado_hasta - ahora_ar()).total_seconds() // 60) + 1
        raise HTTPException(429, f"La cuenta está bloqueada por intentos fallidos. Probá en {minutos} minuto(s) "
                                 "o usá «Olvidé mi contraseña».")
    hijos = hijos_de(db, email) if email else []
    dni_ok = bool(hijos) and _solo_digitos(data.password) in {_solo_digitos(a.dni) for a in hijos if a.dni}
    if cuenta:
        ok = cuenta.activo and (verify_password(data.password, cuenta.password_hash)
                                or (cuenta.debe_cambiar_password and dni_ok))
    else:
        verify_password(data.password, HASH_SENUELO)  # mismo tiempo de respuesta exista o no la cuenta
        ok = dni_ok
        if ok:  # primer ingreso: se crea la cuenta con el DNI como clave inicial
            cuenta = CuentaPadre(email=email, password_hash=hash_password(data.password), debe_cambiar_password=True)
            db.add(cuenta)
            db.flush()
            auditar(db, "portal_cuenta_creada", email, f"{len(hijos)} alumno(s)", request)
    if not ok or not hijos:
        registrar_fallo(db, f"portal-ip:{ip}")
        if cuenta and cuenta.id:
            cuenta.intentos_fallidos = (cuenta.intentos_fallidos or 0) + 1
            if cuenta.intentos_fallidos >= MAX_FALLOS:
                cuenta.bloqueado_hasta = ahora_ar() + timedelta(minutes=BLOQUEO_MIN)
                cuenta.intentos_fallidos = 0
                auditar(db, "portal_cuenta_bloqueada", email, None, request)
                cu.avisar_padre(email, "Bloqueamos el acceso por seguridad",
                                f"<p>Hubo {MAX_FALLOS} intentos fallidos de ingreso al portal con tu correo. "
                                f"Bloqueamos el acceso por {BLOQUEO_MIN} minutos.</p>{_cuando(request)}"
                                "<p>Si no fuiste vos, cambiá tu contraseña con «Olvidé mi contraseña».</p>", f"{APP_URL}/portal")
        db.commit()
        raise HTTPException(401, MSG_CRED)

    limpiar_fallos(db, f"portal-ip:{ip}")
    avisar = not cuenta.ultimo_ingreso or ahora_ar() - cuenta.ultimo_ingreso > timedelta(hours=6)
    cuenta.intentos_fallidos = 0
    cuenta.bloqueado_hasta = None
    cuenta.ultimo_ingreso = ahora_ar()
    auditar(db, "portal_ingreso", email, None, request)
    db.commit()
    if avisar and not cuenta.debe_cambiar_password:
        cu.avisar_padre(email, "Ingreso al portal", "<p>Se ingresó al Portal de familias con tu cuenta.</p>"
                        f"{_cuando(request)}<p>Si no fuiste vos, cambiá tu contraseña de inmediato.</p>", f"{APP_URL}/portal")
    resp = JSONResponse({"ok": True, "debe_cambiar_password": bool(cuenta.debe_cambiar_password)})
    _cookie(resp, _token(cuenta))
    return resp


@router.post("/logout")
def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie("ptoken", path="/", secure=True, httponly=True, samesite="strict")
    return r


@router.get("/me")
def me(c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    hijos = hijos_de(db, c.email)
    no_leidas = db.query(Consulta).filter(Consulta.cuenta_id == c.id, Consulta.leida_autor.is_(False)).count()
    return {"email": c.email, "debe_cambiar_password": bool(c.debe_cambiar_password), "consultas_sin_leer": no_leidas,
            "vista_admin": getattr(c, "vista_admin", None), "tarjeta_activa": config_util.tarjeta_activa(db),
            "hijos": [{"id": a.id, "nombre": a.nombre, "apellido": a.apellido, "curso": a.curso,
                       "division": a.division, "legajo": a.legajo} for a in hijos]}


@router.post("/cambiar-password")
def cambiar_password(data: CambioClave, request: Request, c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    dni_ok = c.debe_cambiar_password and _solo_digitos(data.password_actual) in {
        _solo_digitos(a.dni) for a in hijos_de(db, c.email) if a.dni}
    if not (verify_password(data.password_actual, c.password_hash) or dni_ok):
        raise HTTPException(400, "La contraseña actual es incorrecta.")
    if (motivo := error_password(data.password_nueva, minimo=8)):
        raise HTTPException(400, motivo)
    if _solo_digitos(data.password_nueva) in {_solo_digitos(a.dni) for a in hijos_de(db, c.email) if a.dni}:
        raise HTTPException(400, "La contraseña nueva no puede ser el DNI de un alumno.")
    c.password_hash = hash_password(data.password_nueva)
    c.debe_cambiar_password = False
    c.version_sesion = (c.version_sesion or 0) + 1
    auditar(db, "portal_cambio_password", c.email, None, request)
    db.commit()
    cu.avisar_padre(c.email, "Tu contraseña cambió", "<p>Se cambió la contraseña de tu cuenta del portal.</p>"
                    f"{_cuando(request)}<p>Si no fuiste vos, usá «Olvidé mi contraseña» y avisá a la Asociación.</p>",
                    f"{APP_URL}/portal")
    resp = JSONResponse({"ok": True, "mensaje": "Contraseña actualizada"})
    _cookie(resp, _token(c))
    return resp


@router.post("/olvide")
def olvide(data: Olvide, request: Request, db: Session = Depends(get_db)):
    """Manda un link para crear una contraseña nueva al correo. Responde siempre lo mismo."""
    ip = ip_cliente(request)
    if segundos_bloqueo(db, f"portal-olvide:{ip}", 5, 60):
        raise HTTPException(429, "Demasiados pedidos. Probá de nuevo en una hora.")
    registrar_fallo(db, f"portal-olvide:{ip}")
    email = _norm_email(data.email)
    if email and hijos_de(db, email):
        c = db.query(CuentaPadre).filter(CuentaPadre.email == email).first()
        if not c:  # la cuenta todavía no existía: se crea sin clave usable (la elige con el link)
            import secrets
            c = CuentaPadre(email=email, password_hash=hash_password(secrets.token_urlsafe(24)), debe_cambiar_password=False)
            db.add(c)
            db.flush()
        token = crear_token_acceso(db, "reset_padre", c.id, minutos=30)
        auditar(db, "portal_pedido_reset", email, None, request)
        db.commit()
        cu.avisar_padre(email, "Crear una contraseña nueva",
                        "<p>Recibimos un pedido para cambiar la contraseña del Portal de familias.</p>"
                        "<p>El link vence en 30 minutos y sirve una sola vez. Si no lo pediste, ignorá este correo.</p>",
                        f"{APP_URL}/portal?reset={token}")
    else:
        db.commit()
    return {"ok": True, "mensaje": "Si el correo está registrado, te enviamos un link para crear una contraseña nueva. "
                                   "Revisá también la carpeta de correo no deseado."}


@router.post("/restablecer")
def restablecer(data: Restablecer, request: Request, db: Session = Depends(get_db)):
    if (motivo := error_password(data.password_nueva, minimo=8)):
        raise HTTPException(400, motivo)
    t = consumir_token_acceso(db, data.token, "reset_padre")
    c = db.get(CuentaPadre, t.ref_id) if t else None
    if not c or not c.activo:
        raise HTTPException(400, "El link no es válido o ya venció. Pedí uno nuevo.")
    c.password_hash = hash_password(data.password_nueva)
    c.debe_cambiar_password = False
    c.intentos_fallidos = 0
    c.bloqueado_hasta = None
    c.version_sesion = (c.version_sesion or 0) + 1
    auditar(db, "portal_reset_password", c.email, None, request)
    db.commit()
    return {"ok": True, "mensaje": "Listo. Ya podés ingresar con tu contraseña nueva."}


# ---------------------------------------------------------------- información del alumno

@router.get("/alumno/{alumno_id}")
def resumen_alumno(alumno_id: int, c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    a = _hijo(db, c, alumno_id)
    e = detalle_alumno(db, a)
    saldo = db.get(Saldo, a.id)
    movs = db.query(Movimiento).filter(Movimiento.alumno_id == a.id).order_by(Movimiento.created_at.desc()).limit(60).all()
    return {
        "alumno": {"id": a.id, "nombre": a.nombre, "apellido": a.apellido, "legajo": a.legajo, "dni": a.dni,
                   "curso": a.curso, "division": a.division, "area": a.area, "condicion": a.condicion or "Regular",
                   "modalidad": a.modalidad, "email": a.email, "telefono": a.telefono,
                   "fecha_nacimiento": str(a.fecha_nacimiento) if a.fecha_nacimiento else None,
                   "codigo_pago": ultimo_codigo_pago(db, a.id)},
        "cuotas": {k: e.get(k) for k in (
            "anio", "estado", "pagado", "esperado", "deuda", "deuda_anterior", "deuda_total", "items", "pagos",
            "cuotas_adeudadas", "matricula_adeudada", "meses_adeudados", "detalle_deuda", "proximo", "saldo_a_favor",
            "cursos")}
        | {"curso": e.get("curso_param")},
        "tarjeta": {
            "saldo": float(saldo.monto) if saldo else 0.0,
            "movimientos": [{"fecha": _fmt(m.created_at), "tipo": m.tipo, "monto": float(m.monto),
                             "descripcion": m.descripcion} for m in movs],
        },
        "cupones": cupones_vigentes(db, a.id),
    }


# ---------------------------------------------------------------- consultas (mesa de ayuda)

class NuevaConsulta(BaseModel):
    categoria: str
    alumno_id: int | None = None
    asunto: str | None = None
    texto: str
    adjunto_url: str | None = None


class NuevoMensaje(BaseModel):
    texto: str
    adjunto_url: str | None = None


def _url_adjunto_valida(url: str | None) -> str | None:
    """Solo se aceptan adjuntos subidos al Storage del sistema (evita links arbitrarios)."""
    if not url:
        return None
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    if base and url.startswith(base + "/storage/v1/object/public/"):
        return url[:500]
    raise HTTPException(400, "Adjunto inválido.")


def _dto_consulta(x: Consulta, db: Session, con_mensajes=False) -> dict:
    a = db.get(Alumno, x.alumno_id) if x.alumno_id else None
    d = {"id": x.id, "categoria": x.categoria, "categoria_titulo": cu.titulo(x.categoria), "asunto": x.asunto,
         "estado": x.estado, "creada": _fmt(x.created_at), "actualizada": _fmt(x.actualizada),
         "alumno": f"{a.apellido}, {a.nombre}" if a else None, "sin_leer": not x.leida_autor}
    if con_mensajes:
        d["mensajes"] = [{"autor": m.autor, "autor_nombre": "Asociación (APAI)" if m.autor == "admin" else m.autor_nombre,
                          "texto": m.texto, "adjunto_url": m.adjunto_url, "fecha": _fmt(m.created_at)} for m in x.mensajes]
    return d


@router.get("/ayuda")
def ayuda(db: Session = Depends(get_db)):
    sin_tarjeta = not config_util.tarjeta_activa(db)
    return [{"id": k, "titulo": v["titulo"], "desc": v["desc"], "ayuda": v["ayuda"], "comprobante": v["comprobante"]}
            for k, v in cu.CATEGORIAS.items() if k in cu.CATEGORIAS_PORTAL and not (sin_tarjeta and k == "tarjeta")]


@router.post("/adjunto-firma")
def adjunto_firma(datos: dict, c: CuentaPadre = Depends(get_padre)):
    if int(datos.get("tamanio") or 0) > 8 * 1024 * 1024:
        raise HTTPException(400, "El archivo supera los 8 MB.")
    try:
        return crear_subida_firmada(str(datos.get("nombre") or "comprobante.jpg"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/consultas")
def mis_consultas(c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    lista = db.query(Consulta).filter(Consulta.cuenta_id == c.id).order_by(Consulta.actualizada.desc()).limit(100).all()
    return [_dto_consulta(x, db) for x in lista]


@router.post("/consultas")
def crear_consulta(data: NuevaConsulta, request: Request, c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    if data.categoria not in cu.CATEGORIAS_PORTAL:
        raise HTTPException(400, "Tipo de consulta inválido.")
    texto = (data.texto or "").strip()
    if len(texto) < 5:
        raise HTTPException(400, "Contanos un poco más en el mensaje.")
    if segundos_bloqueo(db, f"portal-consulta:{c.id}", 10, 60):
        raise HTTPException(429, "Enviaste muchas consultas seguidas. Probá de nuevo más tarde.")
    registrar_fallo(db, f"portal-consulta:{c.id}")
    alumno = _hijo(db, c, data.alumno_id) if data.alumno_id else None
    x = Consulta(origen="portal", cuenta_id=c.id, alumno_id=alumno.id if alumno else None, categoria=data.categoria,
                 asunto=((data.asunto or "").strip() or cu.titulo(data.categoria))[:160], estado="abierta",
                 leida_admin=False, leida_autor=True)
    db.add(x)
    db.flush()
    db.add(MensajeConsulta(consulta_id=x.id, autor="padre", autor_nombre=c.email, texto=texto[:4000],
                           adjunto_url=_url_adjunto_valida(data.adjunto_url)))
    auditar(db, "portal_consulta", c.email, f"#{x.id} {cu.titulo(data.categoria)}", request)
    db.commit()
    quien = f"{alumno.apellido}, {alumno.nombre} ({alumno.curso})" if alumno else c.email
    cu.avisar_admins(db, f"Nueva consulta: {cu.titulo(data.categoria)}",
                     f"<p><b>{escape(quien)}</b> envió una consulta desde el portal:</p>"
                     f"<p><b>{escape(x.asunto)}</b><br>{escape(texto[:600])}</p>", f"{APP_URL}/#consultas")
    return {"ok": True, "id": x.id, "mensaje": "Consulta enviada. Te avisamos por correo cuando haya respuesta."}


@router.get("/consultas/{cid}")
def ver_consulta(cid: int, c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    x = db.get(Consulta, cid)
    if not x or x.cuenta_id != c.id:
        raise HTTPException(404, "Consulta no encontrada.")
    if not x.leida_autor and not _es_vista(c):
        x.leida_autor = True
        db.commit()
    return _dto_consulta(x, db, con_mensajes=True)


@router.post("/consultas/{cid}/mensajes")
def responder(cid: int, data: NuevoMensaje, c: CuentaPadre = Depends(get_padre), db: Session = Depends(get_db)):
    x = db.get(Consulta, cid)
    if not x or x.cuenta_id != c.id:
        raise HTTPException(404, "Consulta no encontrada.")
    texto = (data.texto or "").strip()
    if not texto:
        raise HTTPException(400, "Escribí un mensaje.")
    db.add(MensajeConsulta(consulta_id=x.id, autor="padre", autor_nombre=c.email, texto=texto[:4000],
                           adjunto_url=_url_adjunto_valida(data.adjunto_url)))
    x.estado = "abierta"
    x.leida_admin = False
    x.actualizada = ahora_ar()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- vista previa para administradores

class VistaPrevia(BaseModel):
    alumno_id: int


@router.post("/vista-previa")
def vista_previa(data: VistaPrevia, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    """Abre el portal tal cual lo ve la familia del alumno (solo lectura, 30 minutos)."""
    a = db.get(Alumno, data.alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado.")
    correos = sorted(emails_de(a.email), key=lambda e: (a.email or "").lower().find(e))
    if not correos:
        raise HTTPException(400, "El alumno no tiene correo cargado: las familias ingresan al portal con ese correo.")
    usuario = db.get(Usuario, admin["uid"])
    token = jwt.encode({"typ": "padre_vista", "uid": usuario.id, "ver": usuario.version_sesion or 0, "email": correos[0],
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=VISTA_MINUTOS)}, SECRET_KEY, algorithm=ALGORITHM)
    auditar(db, "portal_vista_admin", admin["sub"], f"{correos[0]} ({a.apellido}, {a.nombre})", request)
    db.commit()
    resp = JSONResponse({"ok": True, "email": correos[0], "url": "/portal"})
    resp.set_cookie("ptoken", token, httponly=True, secure=True, samesite="strict", max_age=VISTA_MINUTOS * 60, path="/")
    return resp
