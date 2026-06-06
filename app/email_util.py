"""
Envio de emails por SMTP. Lee las credenciales de variables de entorno.
Para usar Gmail: crear una "contrasena de aplicacion" y cargar:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=casilla@gmail.com
  SMTP_PASS=clave_de_aplicacion
  SMTP_FROM=APAI Pay <casilla@gmail.com>
"""
import os
import smtplib
from email.message import EmailMessage


def email_configurado() -> bool:
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def enviar_email(destino: str, asunto: str, cuerpo_html: str, cuerpo_texto: str | None = None):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    remitente = os.getenv("SMTP_FROM", user)

    if not user or not password:
        raise RuntimeError("El envio de email no esta configurado (faltan SMTP_USER y SMTP_PASS).")

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
