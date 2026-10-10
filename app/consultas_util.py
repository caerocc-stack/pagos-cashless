"""Tipos de consulta del portal, respuestas automáticas y avisos por correo."""
from html import escape

from sqlalchemy.orm import Session

from app.email_util import enviar_email, email_configurado
from app.models.usuario import Usuario

# Cada tipo: título, descripción corta y respuestas automáticas que se muestran ANTES de enviar
# (muchas consultas se resuelven solas sin intervención administrativa).
CATEGORIAS = {
    "informar_pago": {
        "titulo": "Informar un pago",
        "desc": "Pagaste la cuota o una recarga y querés avisar.",
        "comprobante": True,
        "ayuda": [
            "Los pagos con el cupón o el código SIRO (Pago Fácil, Rapipago, Pago Mis Cuentas, Link, QR o billeteras) "
            "se registran solos: no hace falta avisar.",
            "La acreditación demora entre 48 y 72 horas hábiles. Después de ese plazo el pago aparece en «Cuotas y pagos».",
            "Si pagaste por transferencia o en efectivo en la escuela, adjuntá el comprobante y lo registramos.",
        ],
    },
    "pago_no_registrado": {
        "titulo": "Pagué y no figura",
        "desc": "Hiciste un pago hace más de 3 días hábiles y no aparece.",
        "comprobante": True,
        "ayuda": [
            "Revisá que hayan pasado al menos 3 días hábiles desde el pago: antes de eso es normal que no aparezca.",
            "Verificá que hayas pagado con el código del alumno correcto (lo ves en «Cuotas y pagos»). "
            "Si tenés más de un hijo, cada uno tiene su propio código.",
            "Si se cumplió el plazo, adjuntá el comprobante: lo buscamos y lo asignamos al alumno.",
        ],
    },
    "reenvio_cupon": {
        "titulo": "Necesito el cupón de pago",
        "desc": "No te llegó el correo o lo perdiste.",
        "comprobante": False,
        "ayuda": [
            "Todos los cupones enviados están en la pestaña «Cupones»: podés abrirlos y pagarlos desde ahí.",
            "También podés pagar sin cupón con el código de pago del alumno por Pago Mis Cuentas o Link "
            "(buscá «APAI» o «Asociación de Padres INAC» y usá el código que figura en «Cuotas y pagos»).",
            "Revisá la carpeta de correo no deseado (spam): los cupones llegan desde el correo de APAI.",
        ],
    },
    "deuda": {
        "titulo": "Consulta sobre la deuda o las cuotas",
        "desc": "No entendés el saldo o creés que hay un error.",
        "comprobante": False,
        "ayuda": [
            "La deuda se calcula así: matrícula + cuotas vencidas hasta el mes anterior − pagos registrados "
            "(+ deuda del año anterior si la hubiera).",
            "Los pagos de los últimos 3 días hábiles pueden no estar todavía.",
            "Si sigue sin coincidir, envianos la consulta indicando qué pagos hiciste.",
        ],
    },
    "datos": {
        "titulo": "Corregir datos del alumno",
        "desc": "Curso, división, correo o teléfono incorrectos.",
        "comprobante": False,
        "ayuda": [
            "Indicá qué dato está mal y cuál es el correcto. Si cambiás el correo, los cupones y el acceso al portal "
            "pasarán al correo nuevo.",
        ],
    },
    "tarjeta": {
        "titulo": "Tarjeta APAI y saldo",
        "desc": "Recargas, consumos, pérdida de la tarjeta.",
        "comprobante": False,
        "ayuda": [
            "El saldo y cada consumo o recarga están en la pestaña «Tarjeta», con fecha y hora.",
            "Si la tarjeta se perdió, avisá cuanto antes: la damos de baja y el saldo pasa a la tarjeta nueva.",
            "Las recargas pagadas con cupón se acreditan en 48 a 72 horas hábiles.",
        ],
    },
    "otro": {
        "titulo": "Otra consulta",
        "desc": "Cualquier otro tema para la Asociación.",
        "comprobante": False,
        "ayuda": ["Escribinos tu consulta y te respondemos por este mismo medio. Te avisamos por correo cuando haya respuesta."],
    },
    # Solo para el personal (botón «Reportar un problema» dentro del sistema)
    "sistema": {
        "titulo": "Problema en el sistema",
        "desc": "Error o funcionamiento incorrecto de APAI Pay.",
        "comprobante": False,
        "ayuda": [],
    },
}

CATEGORIAS_PORTAL = [k for k in CATEGORIAS if k != "sistema"]


def titulo(cat: str) -> str:
    return CATEGORIAS.get(cat, {}).get("titulo", cat)


def _plantilla(titulo_mail: str, cuerpo: str, enlace: str | None, texto_boton: str) -> str:
    boton = (f'<p><a href="{enlace}" style="display:inline-block;background:#15233b;color:#fff;padding:12px 22px;'
             f'border-radius:8px;text-decoration:none;font-weight:bold">{texto_boton}</a></p>') if enlace else ""
    return f"""<div style="font-family:Arial,sans-serif;max-width:560px;color:#1e293b">
        <h2 style="color:#15233b;margin:0 0 4px">APAI</h2>
        <div style="color:#64748b;font-size:13px;margin-bottom:16px">{escape(titulo_mail)}</div>
        {cuerpo}{boton}
        <p style="color:#94a3b8;font-size:12px;margin-top:24px">Asociación de Padres y Alumnos del I.N.A.C.</p></div>"""


def enviar_seguro(destino: str | None, asunto: str, html: str):
    """Envía un correo sin romper el flujo si el envío falla o no está configurado."""
    if not destino or not email_configurado():
        return
    try:
        enviar_email(destino, asunto, html)
    except Exception as e:
        print("No se pudo enviar el correo:", e)


def avisar_admins(db: Session, asunto: str, cuerpo_html: str, enlace: str):
    for u in db.query(Usuario).filter(Usuario.rol == "admin", Usuario.activo.is_(True), Usuario.email.isnot(None)).all():
        enviar_seguro(u.email, f"APAI Pay · {asunto}", _plantilla("Mesa de ayuda", cuerpo_html, enlace, "Ver en el sistema"))


def avisar_padre(email: str, asunto: str, cuerpo_html: str, enlace: str):
    enviar_seguro(email, f"APAI · {asunto}", _plantilla("Portal de familias", cuerpo_html, enlace, "Ver en el portal"))
