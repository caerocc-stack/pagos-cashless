"""
Cuentas de demostración: muestran el sistema y los portales tal cual los ve cada usuario,
pero no guardan cambios ni descargan archivos.

- Personal: usuario con rol "demo" (se crea con scripts/cuentas_demo.py).
- Portal de familias y portal de alumnos: la cuenta cuyo correo es DEMO_EMAIL (o un alumno con ese correo).

Todo lo que hacen estas cuentas queda en la auditoría (acciones "demo_vio" y "demo_bloqueado"),
para saber si alguien entró y qué miró o intentó hacer. Se lee con actividad() o en Usuarios y seguridad.
"""
import os
import re
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models.seguridad import Auditoria
from app.seguridad import auditar
from app.tz import ahora_ar

DEMO_EMAIL = (os.getenv("DEMO_EMAIL") or "demo@example.com").strip().lower()
MSG = "Modo demostración: se puede ver todo, pero no modificar datos ni descargar archivos."

METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}
# GET que bajan archivos (Excel, backup, plantillas, PDF de facturas, comprobantes, impresiones)
_DESCARGA = re.compile(r"(excel|exportar|backup|plantilla$|/archivo$|/adjuntos/)", re.I)

# Dónde estaba la cuenta demo (va en la columna "usuario" de la auditoría)
SISTEMA, FAMILIAS, ALUMNOS = "demo (sistema)", "demo (portal de familias)", "demo (portal de alumnos)"
VIO, BLOQUEADO = "demo_vio", "demo_bloqueado"
PRUEBAS_LOCALES = ("testclient", "127.0.0.1", "::1")  # pruebas hechas desde la compu de desarrollo: no cuentan
REPETIDO_MIN = 10  # la misma pantalla dentro de estos minutos no se vuelve a anotar


def es_correo_demo(email: str | None) -> bool:
    return DEMO_EMAIL in {e.strip().lower() for e in re.split(r"[;,\s/]+", email or "") if e.strip()}


def es_descarga(ruta: str) -> bool:
    return bool(_DESCARGA.search(ruta)) and not ruta.endswith("/vista")


def bloquea(metodo: str, ruta: str, salidas: tuple[str, ...] = ()) -> bool:
    return (metodo not in METODOS_LECTURA and ruta not in salidas) or (metodo in METODOS_LECTURA and es_descarga(ruta))


def controlar(db: Session, request: Request, cuenta: str, salidas: tuple[str, ...] = (), anotar_lecturas: bool = False):
    """Corta el pedido si modifica datos (salvo cerrar sesión) o si baja un archivo, y lo anota.
    Con anotar_lecturas también anota lo que mira (portales: cada pedido es una pantalla)."""
    metodo, ruta = request.method, request.url.path
    if bloquea(metodo, ruta, salidas):
        registrar(db, request, cuenta, f"{metodo} {ruta}", BLOQUEADO)
        raise HTTPException(403, MSG)
    if anotar_lecturas and metodo == "GET":
        registrar(db, request, cuenta, f"GET {ruta}")


def _dispositivo(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return "celular" if re.search(r"Mobi|Android|iPhone|iPad", ua) else "computadora"


def registrar(db: Session, request: Request, cuenta: str, que: str, accion: str = VIO):
    """Anota una pantalla vista o un intento bloqueado. No repite lo mismo dentro de REPETIDO_MIN minutos
    (el sistema consulta algunas cosas solo, cada tanto). Nunca hace fallar el pedido."""
    try:
        detalle = f"{que} | {_dispositivo(request)}"[:400]
        desde = ahora_ar() - timedelta(minutes=REPETIDO_MIN)
        ya = (db.query(Auditoria.id)
              .filter(Auditoria.accion == accion, Auditoria.usuario == cuenta,
                      Auditoria.detalle == detalle, Auditoria.fecha >= desde).first())
        if not ya:
            auditar(db, accion, cuenta, detalle, request)
            db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------- lectura del registro

SECCIONES = {
    "inicio": "Inicio (tablero)", "cuotas": "Cuotas y estado de cuenta", "alumnos": "Alumnos",
    "importar": "Importar padrón", "cupones-siro": "Cupones de pago", "examenes": "Exámenes por instancia",
    "impresiones": "Impresiones de alumnos", "consultas": "Consultas de familias", "cobrar": "Cobrar",
    "operaciones": "Recargas y cupones", "tarjetas": "Tarjetas", "reportes": "Consumos y reportes",
    "gastos": "Gastos y facturas", "proveedores": "Proveedores", "pedidos": "Pedidos de materiales",
    "caja": "Libro de caja", "conciliacion": "Conciliación bancaria", "horario": "Control horario",
    "usuarios": "Usuarios y seguridad", "cuenta": "Mi cuenta",
}
# Prefijo de la API -> sección del sistema (para nombrar los intentos bloqueados)
_API_SECCION = {
    "alumnos": "alumnos", "cuotas": "cuotas", "ciclo": "cuotas", "cursos": "cuotas", "cupones": "cupones-siro",
    "cupones-siro": "cupones-siro", "examenes": "examenes", "impresiones": "impresiones", "consultas": "consultas",
    "operaciones": "operaciones", "tarjetas": "tarjetas", "reportes": "reportes", "gastos": "gastos",
    "importar-gastos": "gastos", "escaneo-facturas": "gastos", "facturas-recibidas": "gastos",
    "proveedores": "proveedores", "pedidos": "pedidos", "caja": "caja", "conciliacion": "conciliacion",
    "horario": "horario", "usuarios": "usuarios", "config": "usuarios", "mantenimiento": "usuarios",
    "auth": "cuenta", "sectores": "pedidos",
}
_VERBO = {"POST": "guardar o crear algo", "PUT": "modificar datos", "PATCH": "modificar datos", "DELETE": "borrar algo"}


def _seccion_api(ruta: str) -> str:
    partes = ruta.split("/")  # ["", "api", "alumnos", ...]
    clave = partes[2] if len(partes) > 2 else ""
    if clave == "cupones-siro" and "planilla" in ruta:
        clave = "cupones-siro"
    return SECCIONES.get(_API_SECCION.get(clave, ""), clave or ruta)


def describir(cuenta: str | None, accion: str, detalle: str | None) -> str:
    """Pasa un registro de la auditoría a una frase que se entiende."""
    que = (detalle or "").split(" | ")[0]
    if accion in ("ingreso", "portal_ingreso"):
        return "Inició sesión"
    if accion in ("ingreso_fallido",):
        return f"Intentó entrar con una clave equivocada ({detalle or ''})".replace(" ()", "")
    if accion in ("cuenta_bloqueada", "portal_cuenta_bloqueada"):
        return "Se bloqueó la cuenta por varios intentos fallidos"
    if que.startswith("seccion:"):
        nombre, _, extra = que[len("seccion:"):].partition(":")
        texto = SECCIONES.get(nombre, nombre)
        return f"Intentó descargar un PDF en {texto}" if extra == "descarga" else f"Abrió {texto}"
    if que == "ingreso":
        return "Inició sesión"
    metodo, _, ruta = que.partition(" ")
    if accion == BLOQUEADO:
        if metodo in METODOS_LECTURA:
            return f"Intentó descargar un archivo en {_seccion_api(ruta)} (bloqueado)"
        if cuenta == FAMILIAS and ruta.startswith("/api/portal/consultas"):
            return "Intentó enviar una consulta (bloqueado)"
        if cuenta == FAMILIAS and "password" in ruta:
            return "Intentó cambiar la contraseña (bloqueado)"
        if cuenta == ALUMNOS and ruta.startswith("/api/imprimir/pedidos"):
            return "Intentó mandar un archivo a imprimir (bloqueado)"
        if cuenta == ALUMNOS and "password" in ruta:
            return "Intentó cambiar la contraseña (bloqueado)"
        donde = _seccion_api(ruta) if cuenta == SISTEMA else ("el portal" if cuenta else ruta)
        return f"Intentó {_VERBO.get(metodo, 'hacer un cambio')} en {donde} (bloqueado)"
    if ruta == "/api/portal/me":
        return "Entró al portal de familias"
    if ruta.startswith("/api/portal/alumno/"):
        return "Vio el estado de cuenta de la alumna (pagos, deuda y cupones)"
    if ruta == "/api/portal/ayuda":
        return "Abrió la ayuda del portal"
    if ruta == "/api/portal/consultas":
        return "Abrió sus consultas"
    if ruta.startswith("/api/portal/consultas/"):
        return "Leyó una consulta y su respuesta"
    if ruta == "/api/imprimir/me":
        return "Entró al portal de alumnos"
    if ruta.startswith("/api/imprimir/pedidos"):
        return "Vio sus envíos a imprimir"
    return que


def _donde(cuenta: str | None) -> str:
    return {SISTEMA: "Sistema", FAMILIAS: "Portal de familias", ALUMNOS: "Portal de alumnos",
            "demo": "Sistema", DEMO_EMAIL: "Portal de familias"}.get(cuenta or "", cuenta or "")


def actividad(db: Session, limite: int = 500) -> list[dict]:
    """Todo lo que hicieron las cuentas de demostración, lo más nuevo primero."""
    filas = (db.query(Auditoria)
             .filter((Auditoria.accion.in_((VIO, BLOQUEADO)))
                     | ((Auditoria.usuario == "demo") & Auditoria.accion.in_(("ingreso", "ingreso_fallido", "cuenta_bloqueada")))
                     | ((Auditoria.usuario == DEMO_EMAIL) & Auditoria.accion.in_(("portal_ingreso", "portal_cuenta_bloqueada"))))
             .filter((Auditoria.ip.is_(None)) | ~Auditoria.ip.in_(PRUEBAS_LOCALES))
             .order_by(Auditoria.fecha.desc(), Auditoria.id.desc()).limit(limite).all())
    out = []
    for a in filas:
        disp = (a.detalle or "").split(" | ")[1] if " | " in (a.detalle or "") else ""
        que = describir(a.usuario, a.accion, a.detalle)
        out.append({"fecha": a.fecha.strftime("%d/%m/%Y %H:%M"), "donde": _donde(a.usuario), "que": que,
                    "bloqueado": a.accion != VIO and a.accion not in ("ingreso", "portal_ingreso") or que.startswith("Intentó"),
                    "dispositivo": disp, "ip": a.ip or ""})
    return out
