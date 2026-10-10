"""
Copia todo del proyecto de Supabase viejo al nuevo:
  1. Tablas y datos (respetando el orden de las relaciones y los contadores de IDs)
  2. Archivos del bucket de Storage (fotos/PDF de comprobantes)
  3. Links guardados en la base que apuntan al proyecto viejo -> proyecto nuevo

Variables en .env:
  DATABASE_URL              base VIEJA (la que usa hoy Render)
  NEW_DATABASE_URL          base NUEVA (Transaction pooler, puerto 6543)
  OLD_SUPABASE_URL / OLD_SUPABASE_SERVICE_KEY
  NEW_SUPABASE_URL / NEW_SUPABASE_SERVICE_KEY
  SUPABASE_BUCKET           opcional, por defecto 'comprobantes'

Uso:
  python scripts/migrar_supabase.py              -> solo muestra lo que haria (no escribe nada)
  python scripts/migrar_supabase.py --confirmar  -> copia de verdad

La base vieja solo se LEE, nunca se modifica.
"""
import os
import sys
import json
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, select, text, func, String, Text
from sqlalchemy.pool import NullPool

load_dotenv(RAIZ / ".env")

CONFIRMAR = "--confirmar" in sys.argv
LOTE = 500


def _env(nombre):
    v = (os.getenv(nombre) or "").strip()
    if not v:
        sys.exit(f"Falta {nombre} en el archivo .env")
    return v


def _motor(url):
    url = url.replace("postgresql://", "postgresql+psycopg://")
    return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})


def _base_supabase(u):
    u = u.strip().rstrip("/")
    for suf in ("/rest/v1", "/storage/v1", "/auth/v1"):
        if u.endswith(suf):
            u = u[: -len(suf)]
    return u


# ---------------------------------------------------------------- base de datos

def copiar_base(viejo, nuevo):
    meta = MetaData()
    meta.reflect(bind=viejo, schema="public")
    tablas = meta.sorted_tables  # ordenadas para respetar las claves foraneas

    with viejo.connect() as cv:
        cuentas = {t.name: cv.execute(select(func.count()).select_from(t)).scalar() for t in tablas}
    print("\nTablas en la base vieja:")
    for t in tablas:
        print(f"  {t.name:<25} {cuentas[t.name]:>7} filas")

    # La nueva tiene que estar vacia para no duplicar datos
    with nuevo.connect() as cn:
        existentes = set(cn.execute(text(
            "select table_name from information_schema.tables where table_schema='public'"
        )).scalars())
        ocupadas = [t.name for t in tablas if t.name in existentes and
                    cn.execute(text(f'select exists(select 1 from "{t.name}")')).scalar()]
    if ocupadas:
        sys.exit(f"\nLa base nueva ya tiene datos en: {', '.join(ocupadas)}. "
                 "No copio para no duplicar. Vacía esas tablas o usá un proyecto nuevo.")

    if not CONFIRMAR:
        return tablas

    # Crea la estructura con los modelos de la app (mismos tipos e indices que produccion)
    # y despues cualquier tabla extra que exista en la vieja.
    os.environ["DATABASE_URL"] = os.environ["NEW_DATABASE_URL"]
    from app.esquema import preparar_base
    preparar_base()
    meta.create_all(bind=nuevo, checkfirst=True)

    with viejo.connect() as cv, nuevo.begin() as cn:
        # preparar_base crea el usuario admin si no hay ninguno: lo borramos para traer los reales
        cn.execute(text("delete from usuarios"))
        for t in tablas:
            # columnas que apuntan a la misma tabla (ej. gastos.nc_de_id): se cargan en una 2da pasada
            auto = [fk.parent.name for fk in t.foreign_keys if fk.column.table.name == t.name]
            pendientes = []
            orden = list(t.primary_key.columns) or list(t.columns)[:1]
            res = cv.execution_options(stream_results=True).execute(select(t).order_by(*orden))
            n = 0
            while filas := res.mappings().fetchmany(LOTE):
                filas = [dict(f) for f in filas]
                for f in filas:
                    if any(f.get(c) is not None for c in auto):
                        pendientes.append({c: f[c] for c in auto} | {k.name: f[k.name] for k in t.primary_key.columns})
                        for c in auto:
                            f[c] = None
                cn.execute(t.insert(), filas)
                n += len(filas)
            for p in pendientes:
                cond = [t.c[k.name] == p[k.name] for k in t.primary_key.columns]
                cn.execute(t.update().where(*cond).values({c: p[c] for c in auto}))
            print(f"  ✓ {t.name}: {n} filas copiadas")

        # Ajusta los contadores de IDs para que los proximos registros no choquen
        for t in tablas:
            for col in t.primary_key.columns:
                seq = cn.execute(text("select pg_get_serial_sequence(:t, :c)"),
                                 {"t": f'public."{t.name}"', "c": col.name}).scalar()
                if seq:
                    cn.execute(text(
                        f'select setval(:s, coalesce((select max("{col.name}") from "{t.name}"), 0) + 1, false)'
                    ), {"s": seq})

    # Verificacion: mismas cantidades de filas en ambas bases
    with nuevo.connect() as cn:
        malas = [(t.name, cuentas[t.name], cn.execute(select(func.count()).select_from(t)).scalar())
                 for t in tablas]
        malas = [m for m in malas if m[1] != m[2]]
    if malas:
        sys.exit(f"¡Diferencias en la cantidad de filas! {malas}")
    print("  ✓ Verificado: todas las tablas tienen la misma cantidad de filas.")
    return tablas


# ---------------------------------------------------------------- storage

def _http(metodo, url, key, datos=None, tipo=None, extra=None):
    h = {"Authorization": f"Bearer {key}", "apikey": key}
    if tipo:
        h["Content-Type"] = tipo
    h.update(extra or {})
    return urllib.request.urlopen(urllib.request.Request(url, data=datos, headers=h, method=metodo), timeout=60)


def _listar(url, key, bucket, prefijo=""):
    """Lista recursivamente todos los archivos del bucket."""
    archivos, offset = [], 0
    while True:
        cuerpo = json.dumps({"prefix": prefijo, "limit": 1000, "offset": offset}).encode()
        with _http("POST", f"{url}/storage/v1/object/list/{bucket}", key, cuerpo, "application/json") as r:
            items = json.loads(r.read())
        for it in items:
            ruta = f"{prefijo}{it['name']}"
            if it.get("id") is None:  # es una carpeta
                archivos += _listar(url, key, bucket, ruta + "/")
            else:
                archivos.append((ruta, (it.get("metadata") or {}).get("mimetype")))
        if len(items) < 1000:
            return archivos
        offset += 1000


def copiar_storage(url_v, key_v, url_n, key_n, bucket):
    try:
        archivos = _listar(url_v, key_v, bucket)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            print(f"\nEl bucket '{bucket}' no existe en el proyecto viejo: no hay archivos para copiar.")
            return
        raise
    print(f"\nArchivos en Storage ({bucket}): {len(archivos)}")
    if not CONFIRMAR:
        return

    try:
        _http("POST", f"{url_n}/storage/v1/bucket", key_n,
              json.dumps({"id": bucket, "name": bucket, "public": True}).encode(), "application/json")
    except urllib.error.HTTPError as e:
        if e.code not in (400, 409):
            raise

    errores = []
    for i, (ruta, tipo) in enumerate(archivos, 1):
        q = urllib.parse.quote(ruta)
        try:
            with _http("GET", f"{url_v}/storage/v1/object/{bucket}/{q}", key_v) as r:
                datos = r.read()
                tipo = tipo or r.headers.get("Content-Type") or "application/octet-stream"
            _http("POST", f"{url_n}/storage/v1/object/{bucket}/{q}", key_n, datos, tipo,
                  {"x-upsert": "true"}).close()
        except urllib.error.HTTPError as e:
            errores.append((ruta, e.code))
        if i % 25 == 0 or i == len(archivos):
            print(f"  {i}/{len(archivos)} archivos copiados")
    if errores:
        print(f"  ⚠ No se pudieron copiar {len(errores)} archivos: {errores[:10]}")
    else:
        print("  ✓ Todos los archivos copiados.")


def actualizar_links(nuevo, tablas, url_v, url_n):
    """Reemplaza https://<viejo>.supabase.co por https://<nuevo>.supabase.co en columnas de texto."""
    total = 0
    with nuevo.begin() as cn:
        for t in tablas:
            for c in t.columns:
                if isinstance(c.type, (String, Text)):
                    n = cn.execute(text(
                        f'update "{t.name}" set "{c.name}" = replace("{c.name}", :v, :n) '
                        f'where "{c.name}" like :patron'
                    ), {"v": url_v, "n": url_n, "patron": f"%{url_v}%"}).rowcount
                    if n:
                        print(f"  ✓ {t.name}.{c.name}: {n} links actualizados")
                        total += n
    print(f"  Links actualizados: {total}")


# ---------------------------------------------------------------- main

def main():
    viejo, nuevo = _motor(_env("DATABASE_URL")), _motor(_env("NEW_DATABASE_URL"))
    url_v, key_v = _base_supabase(_env("OLD_SUPABASE_URL")), _env("OLD_SUPABASE_SERVICE_KEY")
    url_n, key_n = _base_supabase(_env("NEW_SUPABASE_URL")), _env("NEW_SUPABASE_SERVICE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET") or "comprobantes"
    if url_v == url_n or _env("DATABASE_URL") == _env("NEW_DATABASE_URL"):
        sys.exit("El proyecto viejo y el nuevo son el mismo. Revisá el .env.")

    print(f"Viejo: {url_v}\nNuevo: {url_n}")
    print("MODO REAL: se van a copiar los datos." if CONFIRMAR
          else "MODO PRUEBA: no se escribe nada (agregá --confirmar para copiar).")

    tablas = copiar_base(viejo, nuevo)
    copiar_storage(url_v, key_v, url_n, key_n, bucket)
    if CONFIRMAR:
        print("\nActualizando links de comprobantes...")
        actualizar_links(nuevo, tablas, url_v, url_n)
        print("\n✅ Migración terminada.")


if __name__ == "__main__":
    main()
