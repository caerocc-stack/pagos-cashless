"""
Portal de alumnos para mandar archivos a la fotocopiadora (/imprimir) y la cola de impresión de la oficina.

Alumno:
- Usuario = DNI. Clave inicial = DNI; en el primer ingreso se obliga a elegir una propia.
- Si se la olvida, en la oficina le restablecen el acceso (vuelve a entrar con el DNI).
- Bloqueo de la cuenta por 15 min tras 5 intentos fallidos + límite por IP.
- El archivo sube directo del celular al depósito privado (sin pasar por el servidor) y la ruta
  queda atada al alumno: nadie puede registrar ni ver archivos de otro.

Oficina:
- Pendientes / impresos / descartados, con la fecha y quién lo resolvió.
- Los archivos se borran a los 30 días de impresos o descartados; el registro queda.
"""
import re
import uuid
from datetime import timedelta, datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import SECRET_KEY, ALGORITHM, hash_password, verify_password, HASH_SENUELO, get_current_user
from app.models.alumno import Alumno
from app.models.impresion import CuentaAlumno, PedidoImpresion
from app.seguridad import ip_cliente, auditar, segundos_bloqueo, registrar_fallo, limpiar_fallos, error_password
from app import storage_util
from app.tz import ahora_ar

router = APIRouter(prefix="/api/imprimir", tags=["Portal de alumnos"])
oficina = APIRouter(prefix="/api/impresiones", tags=["Impresiones"])

SESION_DIAS = 30          # se usa desde el celular propio: que no tenga que entrar cada vez
MAX_FALLOS, BLOQUEO_MIN = 5, 15
DIAS_ARCHIVO = 30
MAX_PENDIENTES = 20
EXTENSIONES = {"pdf", "jpg", "jpeg", "png", "webp", "heic", "heif", "doc", "docx", "odt"}
MSG_CRED = "DNI o contraseña incorrectos."
COOKIE = "atoken"


def _solo_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _alumno_por_dni(db: Session, dni: str) -> Alumno | None:
    d = _solo_digitos(dni)
    if len(d) < 6:
        return None
    return db.query(Alumno).filter(Alumno.dni == d, Alumno.activo.is_(True)).first()


def _token(c: CuentaAlumno) -> str:
    return jwt.encode({"typ": "alumno", "cid": c.id, "ver": c.version_sesion or 0,
                       "exp": datetime.now(timezone.utc) + timedelta(days=SESION_DIAS)}, SECRET_KEY, algorithm=ALGORITHM)


def _cookie(resp: Response, token: str):
    resp.set_cookie(COOKIE, token, httponly=True, secure=True, samesite="strict", max_age=SESION_DIAS * 86400, path="/")


def get_alumno(request: Request, db: Session = Depends(get_db)) -> CuentaAlumno:
    try:
        data = jwt.decode(request.cookies.get(COOKIE) or "", SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Tu sesión venció. Ingresá de nuevo.")
    c = db.get(CuentaAlumno, data.get("cid")) if data.get("typ") == "alumno" else None
    a = db.get(Alumno, c.alumno_id) if c else None
    if not c or not a or not a.activo or (c.version_sesion or 0) != data.get("ver"):
        raise HTTPException(401, "Tu sesión venció. Ingresá de nuevo.")
    libre = request.url.path in ("/api/imprimir/me", "/api/imprimir/cambiar-password", "/api/imprimir/logout")
    if c.debe_cambiar_password and not libre:
        raise HTTPException(403, "Antes de continuar tenés que crear tu contraseña personal.")
    c.alumno = a
    return c


def _dto(p: PedidoImpresion, con_alumno=False) -> dict:
    d = {"id": p.id, "archivo": p.archivo_nombre, "tamanio": p.tamanio, "copias": p.copias, "doble_faz": bool(p.doble_faz),
         "notas": p.notas, "estado": p.estado, "motivo": p.motivo, "enviado": _fmt(p.created_at),
         "resuelto": _fmt(p.resuelto_at), "resuelto_por": p.resuelto_por if con_alumno else None,
         "archivo_disponible": not p.archivo_borrado}
    if con_alumno and p.alumno:
        a = p.alumno
        d["alumno"] = {"id": a.id, "nombre": f"{a.apellido}, {a.nombre}", "curso": a.curso, "division": a.division,
                       "legajo": a.legajo, "dni": a.dni}
    return d


# ---------------------------------------------------------------- ingreso del alumno

class Login(BaseModel):
    dni: str
    password: str


class CambioClave(BaseModel):
    password_actual: str
    password_nueva: str


@router.post("/login")
def login(data: Login, request: Request, db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    if (espera := segundos_bloqueo(db, f"imprimir-ip:{ip}", 20, 15)):
        raise HTTPException(429, f"Demasiados intentos. Esperá {(espera + 59) // 60} minuto(s) y probá de nuevo.")
    a = _alumno_por_dni(db, data.dni)
    cuenta = db.query(CuentaAlumno).filter(CuentaAlumno.alumno_id == a.id).first() if a else None
    if cuenta and cuenta.bloqueado_hasta and cuenta.bloqueado_hasta > ahora_ar():
        minutos = int((cuenta.bloqueado_hasta - ahora_ar()).total_seconds() // 60) + 1
        raise HTTPException(429, f"La cuenta está bloqueada por intentos fallidos. Probá en {minutos} minuto(s) "
                                 "o pedí en la oficina de APAI que te restablezcan el acceso.")
    dni_ok = bool(a) and _solo_digitos(data.password) == a.dni
    if cuenta:
        ok = verify_password(data.password, cuenta.password_hash) or (cuenta.debe_cambiar_password and dni_ok)
    else:
        verify_password(data.password, HASH_SENUELO)  # mismo tiempo de respuesta exista o no la cuenta
        ok = dni_ok
        if ok:  # primer ingreso: la clave inicial es el DNI
            cuenta = CuentaAlumno(alumno_id=a.id, password_hash=hash_password(a.dni), debe_cambiar_password=True)
            db.add(cuenta)
            db.flush()
            auditar(db, "imprimir_cuenta_creada", f"alumno {a.legajo}", None, request)
    if not ok:
        registrar_fallo(db, f"imprimir-ip:{ip}")
        if cuenta and cuenta.id:
            cuenta.intentos_fallidos = (cuenta.intentos_fallidos or 0) + 1
            if cuenta.intentos_fallidos >= MAX_FALLOS:
                cuenta.bloqueado_hasta = ahora_ar() + timedelta(minutes=BLOQUEO_MIN)
                cuenta.intentos_fallidos = 0
                auditar(db, "imprimir_cuenta_bloqueada", f"alumno {a.legajo}", None, request)
        db.commit()
        raise HTTPException(401, MSG_CRED)

    limpiar_fallos(db, f"imprimir-ip:{ip}")
    cuenta.intentos_fallidos = 0
    cuenta.bloqueado_hasta = None
    cuenta.ultimo_ingreso = ahora_ar()
    db.commit()
    resp = JSONResponse({"ok": True, "debe_cambiar_password": bool(cuenta.debe_cambiar_password)})
    _cookie(resp, _token(cuenta))
    return resp


@router.post("/logout")
def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return r


@router.get("/me")
def me(c: CuentaAlumno = Depends(get_alumno)):
    a = c.alumno
    return {"nombre": a.nombre, "apellido": a.apellido, "curso": a.curso, "division": a.division, "legajo": a.legajo,
            "debe_cambiar_password": bool(c.debe_cambiar_password), "max_mb": storage_util.MAX_IMPRESION_MB,
            "extensiones": sorted(EXTENSIONES)}


@router.post("/cambiar-password")
def cambiar_password(data: CambioClave, request: Request, c: CuentaAlumno = Depends(get_alumno), db: Session = Depends(get_db)):
    a = c.alumno
    dni_ok = c.debe_cambiar_password and _solo_digitos(data.password_actual) == a.dni
    if not (verify_password(data.password_actual, c.password_hash) or dni_ok):
        raise HTTPException(400, "La contraseña actual es incorrecta.")
    if (motivo := error_password(data.password_nueva, minimo=8)):
        raise HTTPException(400, motivo)
    if _solo_digitos(data.password_nueva) == a.dni:
        raise HTTPException(400, "La contraseña nueva no puede ser tu DNI.")
    c.password_hash = hash_password(data.password_nueva)
    c.debe_cambiar_password = False
    c.version_sesion = (c.version_sesion or 0) + 1
    auditar(db, "imprimir_cambio_password", f"alumno {a.legajo}", None, request)
    db.commit()
    resp = JSONResponse({"ok": True, "mensaje": "Contraseña guardada"})
    _cookie(resp, _token(c))
    return resp


# ---------------------------------------------------------------- envíos del alumno

class Firma(BaseModel):
    nombre: str
    tamanio: int


class NuevoPedido(BaseModel):
    ruta: str
    nombre: str
    tamanio: int | None = None
    copias: int = 1
    doble_faz: bool = False
    notas: str | None = None


def _extension(nombre: str) -> str:
    return (nombre.rsplit(".", 1)[-1] if "." in nombre else "").lower()


@router.post("/firma")
def firma(data: Firma, c: CuentaAlumno = Depends(get_alumno)):
    """Devuelve dónde subir el archivo. La ruta lleva el id del alumno y se valida al registrar el envío."""
    ext = _extension(data.nombre)
    if ext not in EXTENSIONES:
        raise HTTPException(400, "Ese tipo de archivo no se puede imprimir. Mandá un PDF, una foto o un Word.")
    if data.tamanio > storage_util.MAX_IMPRESION_MB * 1024 * 1024:
        raise HTTPException(400, f"El archivo pesa más de {storage_util.MAX_IMPRESION_MB} MB. Si es un PDF, probá exportarlo más liviano.")
    ruta = f"{c.alumno_id}/{ahora_ar():%Y%m}/{uuid.uuid4().hex}.{ext}"
    try:
        return {"upload_url": storage_util.firmar_subida_impresion(ruta), "ruta": ruta}
    except ValueError as e:
        raise HTTPException(503, str(e))


@router.post("/pedidos")
def crear_pedido(data: NuevoPedido, request: Request, c: CuentaAlumno = Depends(get_alumno), db: Session = Depends(get_db)):
    if not re.fullmatch(rf"{c.alumno_id}/\d{{6}}/[0-9a-f]{{32}}\.[a-z]{{3,4}}", data.ruta or ""):
        raise HTTPException(400, "El archivo no se subió bien. Probá de nuevo.")
    if db.query(PedidoImpresion).filter(PedidoImpresion.archivo_ruta == data.ruta).first():
        raise HTTPException(400, "Ese archivo ya fue enviado.")
    pendientes = db.query(PedidoImpresion).filter(PedidoImpresion.alumno_id == c.alumno_id,
                                                  PedidoImpresion.estado == "pendiente").count()
    if pendientes >= MAX_PENDIENTES:
        raise HTTPException(400, f"Ya tenés {MAX_PENDIENTES} archivos esperando. Esperá que se impriman para mandar más.")
    nombre = re.sub(r"[\x00-\x1f]", "", (data.nombre or "").strip())[:200] or f"archivo.{_extension(data.ruta)}"
    p = PedidoImpresion(alumno_id=c.alumno_id, archivo_nombre=nombre, archivo_ruta=data.ruta, tamanio=data.tamanio,
                        copias=max(1, min(int(data.copias or 1), 50)), doble_faz=bool(data.doble_faz),
                        notas=(data.notas or "").strip()[:300] or None)
    db.add(p)
    db.commit()
    return {"ok": True, "pedido": _dto(p)}


@router.get("/pedidos")
def mis_pedidos(c: CuentaAlumno = Depends(get_alumno), db: Session = Depends(get_db)):
    q = (db.query(PedidoImpresion).filter(PedidoImpresion.alumno_id == c.alumno_id)
         .order_by(PedidoImpresion.id.desc()).limit(60))
    return [_dto(p) for p in q]


@router.post("/pedidos/{pid}/cancelar")
def cancelar(pid: int, c: CuentaAlumno = Depends(get_alumno), db: Session = Depends(get_db)):
    p = db.get(PedidoImpresion, pid)
    if not p or p.alumno_id != c.alumno_id:
        raise HTTPException(404, "No encontramos ese envío.")
    if p.estado != "pendiente":
        raise HTTPException(400, "Ese archivo ya no está esperando: no se puede cancelar.")
    p.estado, p.resuelto_at = "cancelado", ahora_ar()
    _borrar_archivos(db, [p])
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- oficina (personal del sistema)

def _borrar_archivos(db: Session, pedidos: list[PedidoImpresion]):
    try:
        storage_util.borrar_impresiones([p.archivo_ruta for p in pedidos])
    except Exception:
        return  # se reintenta en la próxima limpieza
    for p in pedidos:
        p.archivo_borrado = True


def limpiar_viejos(db: Session):
    """Borra los archivos impresos/descartados hace más de 30 días (el registro queda)."""
    limite = ahora_ar() - timedelta(days=DIAS_ARCHIVO)
    viejos = (db.query(PedidoImpresion).filter(PedidoImpresion.estado != "pendiente",
                                               PedidoImpresion.archivo_borrado.is_(False),
                                               PedidoImpresion.resuelto_at < limite).limit(100).all())
    if viejos:
        _borrar_archivos(db, viejos)
        db.commit()


@oficina.get("/contador")
def contador(db: Session = Depends(get_db)):
    return {"pendientes": db.query(PedidoImpresion).filter(PedidoImpresion.estado == "pendiente").count()}


@oficina.get("/")
def listar(estado: str = "pendiente", q: str = "", db: Session = Depends(get_db)):
    limpiar_viejos(db)
    consulta = db.query(PedidoImpresion).join(Alumno, Alumno.id == PedidoImpresion.alumno_id)
    if estado:
        consulta = consulta.filter(PedidoImpresion.estado == estado)
    if (q := q.strip()):
        patron = f"%{q}%"
        consulta = consulta.filter(Alumno.apellido.ilike(patron) | Alumno.nombre.ilike(patron) | Alumno.dni.ilike(patron)
                                   | Alumno.legajo.ilike(patron) | PedidoImpresion.archivo_nombre.ilike(patron))
    # pendientes: el más viejo primero (orden de llegada); el resto: lo último resuelto primero
    orden = PedidoImpresion.id.asc() if estado == "pendiente" else PedidoImpresion.id.desc()
    return [_dto(p, con_alumno=True) for p in consulta.order_by(orden).limit(300)]


@oficina.get("/{pid}/archivo")
def archivo(pid: int, descargar: bool = False, db: Session = Depends(get_db)):
    p = db.get(PedidoImpresion, pid)
    if not p:
        raise HTTPException(404, "No encontramos ese envío.")
    if p.archivo_borrado:
        raise HTTPException(410, f"El archivo se borró ({DIAS_ARCHIVO} días después de resuelto). Queda solo el registro.")
    try:
        return RedirectResponse(storage_util.url_impresion_firmada(p.archivo_ruta, p.archivo_nombre if descargar else None), 302)
    except Exception:
        raise HTTPException(502, "No se pudo abrir el archivo. Probá de nuevo en un momento.")


class Resolver(BaseModel):
    estado: str               # impreso / descartado / pendiente (deshacer)
    motivo: str | None = None


@oficina.post("/{pid}/estado")
def resolver(pid: int, data: Resolver, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(PedidoImpresion, pid)
    if not p:
        raise HTTPException(404, "No encontramos ese envío.")
    if data.estado not in ("impreso", "descartado", "pendiente"):
        raise HTTPException(400, "Estado inválido.")
    if p.estado == "cancelado":
        raise HTTPException(400, "El alumno canceló este envío.")
    if data.estado == "pendiente" and p.archivo_borrado:
        raise HTTPException(400, "El archivo ya se borró: el alumno tiene que mandarlo de nuevo.")
    if data.estado == "descartado" and not (data.motivo or "").strip():
        raise HTTPException(400, "Escribí el motivo: el alumno lo ve en su portal para corregirlo.")
    p.estado = data.estado
    p.motivo = ((data.motivo or "").strip()[:300] or None) if data.estado == "descartado" else None
    p.resuelto_at = ahora_ar() if data.estado != "pendiente" else None
    p.resuelto_por = user["nombre"] if data.estado != "pendiente" else None
    db.commit()
    return {"ok": True, "pedido": _dto(p, con_alumno=True)}


class Restablecer(BaseModel):
    dni: str


@oficina.post("/restablecer-acceso")
def restablecer_acceso(data: Restablecer, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """El alumno se olvidó la clave: vuelve a entrar con su DNI (y elige una nueva)."""
    a = _alumno_por_dni(db, data.dni)
    if not a:
        raise HTTPException(404, "No hay ningún alumno activo con ese DNI.")
    c = db.query(CuentaAlumno).filter(CuentaAlumno.alumno_id == a.id).first()
    if c:
        db.delete(c)
    auditar(db, "imprimir_acceso_restablecido", user["sub"], f"{a.apellido}, {a.nombre} ({a.legajo})", request)
    db.commit()
    return {"ok": True, "mensaje": f"Listo: {a.nombre} {a.apellido} ya puede entrar con su DNI como usuario y como contraseña."}
