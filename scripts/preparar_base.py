"""
Crea/actualiza las tablas de la base y el usuario admin inicial.
Vercel lo corre en cada deploy (buildCommand de vercel.json); tambien se puede
correr a mano: python scripts/preparar_base.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.esquema import preparar_base

if __name__ == "__main__":
    preparar_base()
    print("Base preparada.")
