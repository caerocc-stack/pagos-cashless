"""
Cuentas de demostración: muestran el sistema y los portales tal cual los ve cada usuario,
pero no guardan cambios ni descargan archivos.

- Personal: usuario con rol "demo" (se crea con scripts/cuentas_demo.py).
- Portal de familias y portal de alumnos: la cuenta cuyo correo es DEMO_EMAIL (o un alumno con ese correo).
"""
import os
import re

from fastapi import HTTPException

DEMO_EMAIL = (os.getenv("DEMO_EMAIL") or "demo@example.com").strip().lower()
MSG = "Modo demostración: se puede ver todo, pero no modificar datos ni descargar archivos."

METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}
# GET que bajan archivos (Excel, backup, plantillas, PDF de facturas, comprobantes, impresiones)
_DESCARGA = re.compile(r"(excel|exportar|backup|plantilla$|/archivo$|/adjuntos/)", re.I)


def es_correo_demo(email: str | None) -> bool:
    return DEMO_EMAIL in {e.strip().lower() for e in re.split(r"[;,\s/]+", email or "") if e.strip()}


def es_descarga(ruta: str) -> bool:
    return bool(_DESCARGA.search(ruta)) and not ruta.endswith("/vista")


def controlar(metodo: str, ruta: str, salidas: tuple[str, ...] = ()):
    """Corta el pedido si modifica datos (salvo cerrar sesión) o si baja un archivo."""
    if (metodo not in METODOS_LECTURA and ruta not in salidas) or (metodo in METODOS_LECTURA and es_descarga(ruta)):
        raise HTTPException(403, MSG)
