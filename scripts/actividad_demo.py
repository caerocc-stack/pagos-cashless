"""
Muestra qué hizo la cuenta de demostración (sistema, portal de familias y portal de alumnos):
ingresos, pantallas que abrió e intentos bloqueados. Lo mismo se ve en el sistema, en Usuarios y seguridad.

    python scripts/actividad_demo.py
"""
import os
import sys

from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
load_dotenv(os.path.join(RAIZ, ".env"))

from app.database import SessionLocal  # noqa: E402
import app.esquema  # noqa: E402,F401
from app import demo  # noqa: E402

if __name__ == "__main__":
    db = SessionLocal()
    try:
        filas = list(reversed(demo.actividad(db, limite=2000)))
    finally:
        db.close()
    if not filas:
        print("Todavía no entró nadie con la cuenta de demostración.")
    for f in filas:
        marca = "  [BLOQUEADO]" if f["bloqueado"] else ""
        print(f"{f['fecha']}  {f['donde']:<19} {f['que']}{marca}  ({f['dispositivo'] or '-'}, IP {f['ip'] or '-'})")
