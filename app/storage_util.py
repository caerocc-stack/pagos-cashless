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


def _cfg():
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY") or ""
    bucket = os.getenv("SUPABASE_BUCKET") or "comprobantes"
    return url, key, bucket


def storage_configurado() -> bool:
    url, key, _ = _cfg()
    return bool(url and key)


def _request(metodo: str, url: str, key: str, datos: bytes | None, content_type: str | None):
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=datos, headers=headers, method=metodo)
    return urllib.request.urlopen(req, timeout=30)


def _asegurar_bucket(url: str, key: str, bucket: str):
    """Crea el bucket público si no existe (idempotente; ignora 'ya existe')."""
    try:
        cuerpo = json.dumps({"name": bucket, "id": bucket, "public": True}).encode()
        _request("POST", f"{url}/storage/v1/bucket", key, cuerpo, "application/json")
    except urllib.error.HTTPError as e:
        # 400/409 = ya existe -> está bien
        if e.code not in (400, 409):
            raise


def subir_comprobante(contenido: bytes, filename: str, content_type: str | None = None) -> str:
    """Sube el archivo y devuelve la URL pública. Lanza ValueError si no está configurado."""
    url, key, bucket = _cfg()
    if not (url and key):
        raise ValueError(
            "Supabase Storage no está configurado. Cargá SUPABASE_URL y "
            "SUPABASE_SERVICE_KEY en las variables de entorno."
        )

    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in EXT_PERMITIDAS:
        raise ValueError(f"Tipo de archivo no permitido (.{ext}). Usá una foto o PDF.")
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    anio = ahora_ar().year
    ruta = f"{anio}/{uuid.uuid4().hex}.{ext}"

    _asegurar_bucket(url, key, bucket)
    try:
        _request("POST", f"{url}/storage/v1/object/{bucket}/{ruta}", key, contenido, content_type)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")[:200]
        raise ValueError(f"No se pudo subir el archivo a Storage ({e.code}): {detalle}")

    return f"{url}/storage/v1/object/public/{bucket}/{ruta}"
