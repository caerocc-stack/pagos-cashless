"""
Integracion con la API de SIRO Pagos (Banco Roela).

Credenciales (variables de entorno):
  SIRO_API_LOGIN   -> usuario de la API que entrega SIRO
  SIRO_API_KEY     -> clave de la API que entrega SIRO
  SIRO_NRO_EMPRESA -> numero de empresa/comercio (los digitos que anteceden al codigo de cliente)
  SIRO_BASE_URL    -> URL base de la API (sandbox o produccion)

NOTA: el endpoint y el formato exacto del cuerpo se terminan de ajustar y probar
contra el entorno de PRUEBA (sandbox) de SIRO una vez que se obtengan las credenciales.
"""
import os
import json
import urllib.request
import urllib.error


def siro_configurado() -> bool:
    return bool(os.getenv("SIRO_API_LOGIN") and os.getenv("SIRO_API_KEY") and os.getenv("SIRO_NRO_EMPRESA"))


def codigo_cliente_empresa(alumno) -> str:
    """
    Arma el numero de cliente de 19 digitos que identifica el cobro en SIRO:
    9 digitos de empresa + 10 digitos del codigo del alumno (legajo con ceros).
    """
    empresa = "".join(c for c in os.getenv("SIRO_NRO_EMPRESA", "") if c.isdigit())
    return (empresa.zfill(9) + alumno.codigo_siro)[-19:]


def generar_cupon(alumno, monto, concepto: str = "Recarga de saldo APAI Pay") -> dict:
    """
    Crea una intencion de pago en SIRO y devuelve la URL del cupon para el padre.
    Devuelve: {"url": ..., "nro_cliente": ..., "hash": ..., "id_resultado": ...}
    """
    if not siro_configurado():
        raise RuntimeError(
            "SIRO todavia no esta configurado. Cargá SIRO_API_LOGIN, SIRO_API_KEY y "
            "SIRO_NRO_EMPRESA en las variables de entorno para activar el envio de cupones."
        )

    base_url = os.getenv("SIRO_BASE_URL", "https://apisiro.bancoroela.com.ar").rstrip("/")
    api_login = os.getenv("SIRO_API_LOGIN")
    api_key = os.getenv("SIRO_API_KEY")
    nro_cliente = codigo_cliente_empresa(alumno)

    cuerpo = {
        "nro_cliente_empresa": nro_cliente,
        "importe": float(monto),
        "concepto": concepto,
        "comprobante": alumno.codigo_siro,
    }

    req = urllib.request.Request(
        f"{base_url}/api/Pago",
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
            "ApiLogin": api_login,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"SIRO respondio error {e.code}: {detalle}")
    except Exception as e:
        raise RuntimeError(f"No se pudo conectar con SIRO: {e}")

    return {
        "url": data.get("url") or data.get("URL") or data.get("link"),
        "hash": data.get("hash") or data.get("Hash"),
        "id_resultado": data.get("id_resultado") or data.get("IdResultado"),
        "nro_cliente": nro_cliente,
        "raw": data,
    }
