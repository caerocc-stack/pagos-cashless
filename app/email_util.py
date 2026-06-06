"""
Envio de emails.

IMPORTANTE: Render (plan gratuito) bloquea los puertos SMTP salientes,
por eso el envio se hace por la API HTTP de Brevo (puerto 443, no bloqueado).
Brevo: gratis 300 emails/dia, no requiere dominio propio (solo verificar el remitente).

Variables de entorno (Brevo - recomendado):
  BREVO_API_KEY     -> API key de Brevo
  BREVO_FROM_EMAIL  -> email remitente verificado en Brevo
  BREVO_FROM_NAME   -> nombre a mostrar (ej. APAI Pay)

Alternativa SMTP (solo sirve en planes pagos de Render o en local):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""
import os
import json
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage


def email_configurado() -> bool:
    if os.getenv("BREVO_API_KEY"):
        return True
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def enviar_email(destino: str, asunto: str, cuerpo_html: str, cuerpo_texto: str | None = None):
    if os.getenv("BREVO_API_KEY"):
        _enviar_brevo(destino, asunto, cuerpo_html)
    elif os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"):
        _enviar_smtp(destino, asunto, cuerpo_html, cuerpo_texto)
    else:
        raise RuntimeError(
            "El envio de email no esta configurado. Cargá BREVO_API_KEY y BREVO_FROM_EMAIL "
            "(recomendado) en las variables de entorno."
        )


def _enviar_brevo(destino: str, asunto: str, cuerpo_html: str):
    api_key = os.getenv("BREVO_API_KEY")
    from_email = os.getenv("BREVO_FROM_EMAIL") or os.getenv("SMTP_USER")
    from_name = os.getenv("BREVO_FROM_NAME", "APAI Pay")
    if not from_email:
        raise RuntimeError("Falta BREVO_FROM_EMAIL (el email remitente verificado en Brevo).")

    cuerpo = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": destino}],
        "subject": asunto,
        "htmlContent": cuerpo_html,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Brevo respondio error {e.code}: {detalle}")
    except Exception as e:
        raise RuntimeError(f"No se pudo conectar con Brevo: {e}")


def _enviar_smtp(destino: str, asunto: str, cuerpo_html: str, cuerpo_texto: str | None = None):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    remitente = os.getenv("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = destino
    msg.set_content(cuerpo_texto or "Para ver este mensaje active el formato HTML en su correo.")
    msg.add_alternative(cuerpo_html, subtype="html")

    with smtplib.SMTP(host, port, timeout=20) as servidor:
        servidor.starttls()
        servidor.login(user, password)
        servidor.send_message(msg)
