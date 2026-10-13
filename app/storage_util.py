"""
Subida de comprobantes (fotos/PDF de facturas) a Supabase Storage.

Render bloquea SMTP pero NO el puerto 443, así que se usa la API REST de
Storage por HTTPS (igual que email_util con Mailjet).

Variables de entorno necesarias (cargar en Vercel):
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


def _preparar(filename: str):
    """Valida la configuración y la extensión; devuelve (url, key, bucket, ruta)."""
    url, key, bucket = _cfg()
    if not (url and key):
        raise ValueError(
            "Supabase Storage no está configurado. Cargá SUPABASE_URL y "
            "SUPABASE_SERVICE_KEY en las variables de entorno del servidor y volvé a desplegar."
        )
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in EXT_PERMITIDAS:
        raise ValueError(f"Tipo de archivo no permitido (.{ext}). Usá una foto o PDF.")
    ruta = f"{ahora_ar().year}/{uuid.uuid4().hex}.{ext}"
    return url, key, bucket, ruta


def _con_bucket(url: str, key: str, bucket: str, accion):
    """Ejecuta accion(); si el bucket no existe lo crea y reintenta una vez."""
    try:
        return accion()
    except urllib.error.HTTPError as e:
        cuerpo = _leer_cuerpo(e)
        # Supabase responde "Bucket not found" a veces como 404 y a veces dentro de un 400.
        if not _es_bucket_inexistente(e.code, cuerpo):
            raise ValueError(_traducir(e.code, cuerpo))
        try:
            _asegurar_bucket(url, key, bucket)
        except urllib.error.HTTPError as e_bucket:
            cb = _leer_cuerpo(e_bucket)
            # 400/409 o "already exists" = el bucket ya estaba, seguimos
            if e_bucket.code not in (400, 409) and "exist" not in cb.lower():
                raise ValueError(_traducir(e_bucket.code, cb))
        try:
            return accion()
        except urllib.error.HTTPError as e2:
            raise ValueError(_traducir(e2.code, _leer_cuerpo(e2)))
    except urllib.error.URLError as e:
        raise ValueError(f"No se pudo conectar con Supabase: {e.reason}. Revisá SUPABASE_URL.")


def subir_comprobante(contenido: bytes, filename: str, content_type: str | None = None) -> str:
    """Sube el archivo y devuelve la URL pública. Lanza ValueError con un mensaje claro si falla."""
    url, key, bucket, ruta = _preparar(filename)
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    destino = f"{url}/storage/v1/object/{bucket}/{ruta}"
    _con_bucket(url, key, bucket,
                lambda: _request("POST", destino, key, contenido, content_type, extra={"x-upsert": "true"}))
    return f"{url}/storage/v1/object/public/{bucket}/{ruta}"


def crear_subida_firmada(filename: str) -> dict:
    """Genera una URL firmada para que el navegador suba el archivo directo a Storage
    (sin pasar por el servidor: Vercel limita el cuerpo de los pedidos a 4,5 MB).
    Devuelve {"upload_url", "public_url"}. La firma vence a las 2 horas."""
    url, key, bucket, ruta = _preparar(filename)

    def _firmar():
        with _request("POST", f"{url}/storage/v1/object/upload/sign/{bucket}/{ruta}",
                      key, b"{}", "application/json") as resp:
            return json.loads(resp.read())

    firma = _con_bucket(url, key, bucket, _firmar)
    return {
        "upload_url": f"{url}/storage/v1{firma['url']}",
        "public_url": f"{url}/storage/v1/object/public/{bucket}/{ruta}",
    }


# ---------------------------------------------------------------- depósito PRIVADO (facturas de proveedores)
BUCKET_PRIVADO = "facturas-proveedores"


def _asegurar_bucket_privado(url: str, key: str):
    cuerpo = json.dumps({"name": BUCKET_PRIVADO, "id": BUCKET_PRIVADO, "public": False}).encode()
    try:
        _request("POST", f"{url}/storage/v1/bucket", key, cuerpo, "application/json")
    except urllib.error.HTTPError as e:
        cb = _leer_cuerpo(e)
        if e.code not in (400, 409) and "exist" not in cb.lower():
            raise ValueError(_traducir(e.code, cb))


def subir_privado(contenido: bytes, extension: str = "pdf", content_type: str = "application/pdf") -> str:
    """Sube a un depósito privado (sin URL pública). Devuelve la ruta interna."""
    url, key, _ = _cfg()
    if not (url and key):
        raise ValueError("Supabase Storage no está configurado.")
    ruta = f"{ahora_ar():%Y/%m}/{uuid.uuid4().hex}.{extension}"
    destino = f"{url}/storage/v1/object/{BUCKET_PRIVADO}/{ruta}"

    def subir():
        return _request("POST", destino, key, contenido, content_type)
    try:
        subir()
    except urllib.error.HTTPError as e:
        cuerpo = _leer_cuerpo(e)
        if not _es_bucket_inexistente(e.code, cuerpo):
            raise ValueError(_traducir(e.code, cuerpo))
        _asegurar_bucket_privado(url, key)
        try:
            subir()
        except urllib.error.HTTPError as e2:
            raise ValueError(_traducir(e2.code, _leer_cuerpo(e2)))
    return ruta


def url_privada_firmada(ruta: str, segundos: int = 300) -> str:
    """Enlace temporal para ver un archivo del depósito privado."""
    url, key, _ = _cfg()
    with _request("POST", f"{url}/storage/v1/object/sign/{BUCKET_PRIVADO}/{ruta}", key,
                  json.dumps({"expiresIn": segundos}).encode(), "application/json") as resp:
        firma = json.loads(resp.read())
    return f"{url}/storage/v1{firma.get('signedURL') or firma.get('signedUrl')}"
