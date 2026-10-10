"""
Restaura las tablas de la app desde un backup de Supabase (db_cluster-*.backup.gz,
el que se descarga desde Database > Backups) en la base de NEW_DATABASE_URL.

Solo carga las tablas del esquema public (los datos del sistema); ignora roles,
auth, storage, etc. La base destino tiene que estar vacia.

Uso:
  python scripts/restaurar_backup.py "C:\\ruta\\db_cluster-....backup.gz"
"""
import os
import sys
import gzip
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv

load_dotenv(RAIZ / ".env")


def leer_copias(ruta):
    """Devuelve {tabla: (columnas, texto_COPY)} de las tablas public del dump."""
    abrir = gzip.open if str(ruta).endswith(".gz") else open
    copias, actual, cols, lineas = {}, None, None, []
    with abrir(ruta, "rt", encoding="utf-8") as f:
        for l in f:
            if actual is None:
                if l.startswith("COPY public."):
                    actual = l.split()[1].split(".", 1)[1].strip('"')
                    cols = l[l.index("(") + 1:l.index(")")]
                    lineas = []
            elif l.startswith("\\."):
                copias[actual] = (cols, "".join(lineas))
                actual = None
            else:
                lineas.append(l)
    return copias


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    nueva = (os.getenv("NEW_DATABASE_URL") or "").strip()
    if not nueva:
        sys.exit("Falta NEW_DATABASE_URL en el .env")
    # La app (app.database) usa DATABASE_URL: la apuntamos a la base nueva
    os.environ["DATABASE_URL"] = nueva

    from sqlalchemy import text, select, func
    from app.database import engine, Base
    from app.esquema import preparar_base

    copias = leer_copias(sys.argv[1])
    print("Tablas en el backup:")
    for t, (_, datos) in copias.items():
        print(f"  {t:<25}{datos.count(chr(10)):>7} filas")

    tablas = {t.name: t for t in Base.metadata.sorted_tables}
    desconocidas = set(copias) - set(tablas)
    if desconocidas:
        sys.exit(f"El backup tiene tablas que la app no conoce: {desconocidas}")

    preparar_base()  # crea tablas, columnas e indices como en produccion

    with engine.connect() as c:
        ocupadas = [n for n in tablas if n != "usuarios" and c.execute(text(f'select exists(select 1 from "{n}")')).scalar()]
    if ocupadas:
        sys.exit(f"La base nueva ya tiene datos en: {', '.join(ocupadas)}. No restauro para no duplicar.")

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("delete from usuarios")  # el admin que crea preparar_base: traemos los reales
        for nombre in tablas:  # orden que respeta las claves foraneas
            if nombre not in copias:
                continue
            cols, datos = copias[nombre]
            with cur.copy(f'COPY public."{nombre}" ({cols}) FROM STDIN') as cp:
                cp.write(datos)
            print(f"  ✓ {nombre}")
        # Contadores de IDs: que el proximo registro siga despues del ultimo
        for nombre, t in tablas.items():
            for col in t.primary_key.columns:
                cur.execute("select pg_get_serial_sequence(%s, %s)", (f'public."{nombre}"', col.name))
                seq = cur.fetchone()[0]
                if seq:
                    cur.execute(f'select setval(%s, coalesce((select max("{col.name}") from "{nombre}"), 0) + 1, false)', (seq,))
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

    # Verificacion
    with engine.connect() as c:
        dif = []
        for nombre, (_, datos) in copias.items():
            esperado = datos.count("\n")
            real = c.execute(select(func.count()).select_from(tablas[nombre])).scalar()
            if esperado != real:
                dif.append((nombre, esperado, real))
    if dif:
        sys.exit(f"¡Diferencias en la cantidad de filas! {dif}")
    print("\n✅ Restauración completa: todas las tablas tienen la misma cantidad de filas que el backup.")


if __name__ == "__main__":
    main()
