"""
Envio de emails.

IMPORTANTE: Render (plan gratuito) bloquea los puertos SMTP salientes,
por eso el envio se hace por API HTTP (puerto 443, no bloqueado).

Proveedores soportados (se elige el que tenga sus variables cargadas):

  Mailjet (recomendado, 200/dia gratis, verifica por email):
    MAILJET_API_KEY, MAILJET_SECRET_KEY, MAILJET_FROM_EMAIL, MAILJET_FROM_NAME

  Brevo (300/dia gratis):
    BREVO_API_KEY, BREVO_FROM_EMAIL, BREVO_FROM_NAME

  SMTP (solo planes pagos de Render o local):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""
import os
import re
import json
import base64
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage


def _html_a_texto(html: str) -> str:
    """Genera una version de texto plano simple a partir del HTML."""
    texto = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    texto = re.sub(r"</p>", "\n\n", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() or "Mensaje de APAI Pay"


def email_configurado() -> bool:
    if os.getenv("MAILJET_API_KEY") and os.getenv("MAILJET_SECRET_KEY"):
        return True
    if os.getenv("BREVO_API_KEY"):
        return True
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def enviar_email(destino: str, asunto: str, cuerpo_html: str, cuerpo_texto: str | None = None):
    if os.getenv("MAILJET_API_KEY") and os.getenv("MAILJET_SECRET_KEY"):
        _enviar_mailjet(destino, asunto, cuerpo_html)
    elif os.getenv("BREVO_API_KEY"):
        _enviar_brevo(destino, asunto, cuerpo_html)
    elif os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"):
        _enviar_smtp(destino, asunto, cuerpo_html, cuerpo_texto)
    else:
        raise RuntimeError(
            "El envio de email no esta configurado. Cargá las variables de Mailjet "
            "(MAILJET_API_KEY, MAILJET_SECRET_KEY, MAILJET_FROM_EMAIL) en el entorno."
        )


def _enviar_mailjet(destino: str, asunto: str, cuerpo_html: str):
    api_key = os.getenv("MAILJET_API_KEY")
    secret = os.getenv("MAILJET_SECRET_KEY")
    from_email = os.getenv("MAILJET_FROM_EMAIL")
    from_name = os.getenv("MAILJET_FROM_NAME", "APAI Pay")
    if not from_email:
        raise RuntimeError("Falta MAILJET_FROM_EMAIL (el email remitente verificado en Mailjet).")

    cuerpo = {
        "Messages": [{
            "From": {"Email": from_email, "Name": from_name},
            "To": [{"Email": destino}],
            "Subject": asunto,
            "TextPart": _html_a_texto(cuerpo_html),
            "HTMLPart": cuerpo_html,
        }]
    }
    token = base64.b64encode(f"{api_key}:{secret}".encode()).decode()
    req = urllib.request.Request(
        "https://api.mailjet.com/v3.1/send",
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Mailjet respondio error {e.code}: {detalle}")
    except Exception as e:
        raise RuntimeError(f"No se pudo conectar con Mailjet: {e}")


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
        "textContent": _html_a_texto(cuerpo_html),
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={"api-key": api_key, "Content-Type": "application/json", "accept": "application/json"},
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
