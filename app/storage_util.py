"""
Subida de comprobantes (fotos/PDF de facturas) a Supabase Storage.

Render bloquea SMTP pero NO el puerto 443, así que se usa la API REST de
Storage por HTTPS (igual que email_util con Mailjet).

Variables de entorno necesarias (cargar en Render):
  SUPABASE_URL          ej: https://abcdxyz.supabase.co
  SUPABASE_SERVICE_KEY  la clave 'service_role' (Project Settings > API). SECRETA.
  SUPABASE_BUCKET       opcional, por defecto 'comprobantes'
"""
import os
import json
import uuid
import mimetypes
import urllib.request
import urllib.error

from app.tz import ahora_ar

EXT_PERMITIDAS = {"jpg", "jpeg", "png", "webp", "gif", "pdf", "heic"}


def _normalizar_url(u: str) -> str:
    """Deja solo https://<proyecto>.supabase.co, sacando rutas de API pegadas por error
    (ej. .../rest/v1, .../storage/v1) y barras finales."""
    u = (u or "").strip().rstrip("/")
    for suf in ("/rest/v1", "/storage/v1", "/auth/v1", "/rest", "/storage", "/auth"):
        if u.endswith(suf):
            u = u[: -len(suf)].rstrip("/")
    return u


def _cfg():
    url = _normalizar_url(os.getenv("SUPABASE_URL") or "")
    key = os.getenv("SUPABASE_SERVICE_KEY") or ""
    bucket = os.getenv("SUPABASE_BUCKET") or "comprobantes"
    return url, key, bucket


def storage_configurado() -> bool:
    url, key, _ = _cfg()
    return bool(url and key)


def _request(metodo: str, url: str, key: str, datos: bytes | None, content_type: str | None, extra: dict | None = None):
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    if extra:
        headers.update(extra)
    req = urllib.request.Request(url, data=datos, headers=headers, method=metodo)
    return urllib.request.urlopen(req, timeout=30)


def _asegurar_bucket(url: str, key: str, bucket: str):
    """Crea el bucket público. Devuelve True si lo creó o ya existía."""
    cuerpo = json.dumps({"name": bucket, "id": bucket, "public": True}).encode()
    _request("POST", f"{url}/storage/v1/bucket", key, cuerpo, "application/json")


def _leer_cuerpo(e: urllib.error.HTTPError) -> str:
    try:
        return e.read().decode("utf-8", "ignore")[:300]
    except Exception:
        return ""


def _traducir(code: int, detalle: str) -> str:
    if code in (401, 403):
        return ("La clave de Supabase es inválida o no tiene permisos. "
                "Verificá que sea la clave 'service_role' (Project Settings > API), no la 'anon'. "
                f"[{code}] {detalle}")
    if code == 404:
        return f"No se encontró el proyecto/bucket en Supabase. Revisá SUPABASE_URL. [{code}] {detalle}"
    return f"No se pudo subir el archivo a Storage [{code}] {detalle}"


def _es_bucket_inexistente(code: int, cuerpo: str) -> bool:
    return code == 404 or "bucket not found" in (cuerpo or "").lower()


def subir_comprobante(contenido: bytes, filename: str, content_type: str | None = None) -> str:
    """Sube el archivo y devuelve la URL pública. Lanza ValueError con un mensaje claro si falla."""
    url, key, bucket = _cfg()
    if not (url and key):
        raise ValueError(
            "Supabase Storage no está configurado. Cargá SUPABASE_URL y "
            "SUPABASE_SERVICE_KEY en las variables de entorno de Render y volvé a desplegar."
        )

    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in EXT_PERMITIDAS:
        raise ValueError(f"Tipo de archivo no permitido (.{ext}). Usá una foto o PDF.")
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    anio = ahora_ar().year
    ruta = f"{anio}/{uuid.uuid4().hex}.{ext}"
    destino = f"{url}/storage/v1/object/{bucket}/{ruta}"

    def _intentar():
        _request("POST", destino, key, contenido, content_type, extra={"x-upsert": "true"})

    try:
        _intentar()
    except urllib.error.HTTPError as e:
        cuerpo = _leer_cuerpo(e)
        # Supabase responde "Bucket not found" a veces como 404 y a veces dentro de un 400.
        if _es_bucket_inexistente(e.code, cuerpo):
            try:
                _asegurar_bucket(url, key, bucket)
            except urllib.error.HTTPError as e_bucket:
                cb = _leer_cuerpo(e_bucket)
                # 400/409 o "already exists" = el bucket ya estaba, seguimos
                if e_bucket.code not in (400, 409) and "exist" not in cb.lower():
                    raise ValueError(_traducir(e_bucket.code, cb))
            try:
                _intentar()
            except urllib.error.HTTPError as e2:
                raise ValueError(_traducir(e2.code, _leer_cuerpo(e2)))
        else:
            raise ValueError(_traducir(e.code, cuerpo))
    except urllib.error.URLError as e:
        raise ValueError(f"No se pudo conectar con Supabase: {e.reason}. Revisá SUPABASE_URL.")

    return f"{url}/storage/v1/object/public/{bucket}/{ruta}"
