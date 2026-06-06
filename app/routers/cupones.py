from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from decimal import Decimal

from app.database import get_db
from app.models.alumno import Alumno
from app import siro, email_util

router = APIRouter(prefix="/api/cupones", tags=["Cupones SIRO"])


class CuponRequest(BaseModel):
    alumno_id: int
    monto: Decimal


def _cuerpo_email(alumno, monto, url) -> str:
    monto_str = f"${monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    boton = (
        f'<a href="{url}" style="background:#a01e22;color:#fff;text-decoration:none;'
        f'padding:12px 28px;border-radius:8px;font-weight:bold;display:inline-block">Pagar recarga</a>'
        if url else '<em>(enlace de pago no disponible)</em>'
    )
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;color:#15233b">
        <div style="background:#15233b;color:#fff;padding:16px 20px;border-radius:10px 10px 0 0">
            <h2 style="margin:0">APAI Pay</h2>
            <div style="color:#9bb6d6;font-size:13px">Asociación de Padres y Alumnos del I.N.A.C</div>
        </div>
        <div style="border:1px solid #e2e8f0;border-top:none;padding:20px;border-radius:0 0 10px 10px">
            <p>Estimada familia de <strong>{alumno.apellido}, {alumno.nombre}</strong>:</p>
            <p>Generamos un cupón para recargar saldo en la tarjeta del alumno por el siguiente importe:</p>
            <p style="font-size:24px;font-weight:bold;color:#16a34a;text-align:center;margin:18px 0">{monto_str}</p>
            <p style="text-align:center;margin:24px 0">{boton}</p>
            <p style="font-size:13px;color:#5b6b80">Una vez abonado, el saldo se acreditará en la tarjeta del alumno.
            Curso: {alumno.curso} · Legajo: {alumno.legajo}</p>
        </div>
    </div>
    """


@router.post("/recarga")
def enviar_cupon_recarga(data: CuponRequest, db: Session = Depends(get_db)):
    if data.monto <= 0:
        raise HTTPException(400, "El monto debe ser mayor a cero")

    alumno = db.get(Alumno, data.alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")
    if not alumno.email:
        raise HTTPException(400, "El alumno no tiene email cargado. Cargalo en su ficha o por importación.")

    if not siro.siro_configurado():
        raise HTTPException(
            400,
            "SIRO todavía no está configurado. Cargá las credenciales (SIRO_API_LOGIN, "
            "SIRO_API_KEY, SIRO_NRO_EMPRESA) para activar el envío de cupones.",
        )

    # 1) Generar el cupón en SIRO
    try:
        cupon = siro.generar_cupon(alumno, data.monto)
    except Exception as e:
        raise HTTPException(400, str(e))

    # 2) Enviar el cupón por email al padre
    if not email_util.email_configurado():
        return {
            "ok": True,
            "email_enviado": False,
            "mensaje": "Cupón generado, pero el envío de email no está configurado todavía.",
            "url": cupon.get("url"),
        }

    try:
        email_util.enviar_email(
            destino=alumno.email,
            asunto=f"Cupón de recarga - APAI Pay - {alumno.apellido}, {alumno.nombre}",
            cuerpo_html=_cuerpo_email(alumno, data.monto, cupon.get("url")),
        )
    except Exception as e:
        return {
            "ok": True,
            "email_enviado": False,
            "mensaje": f"Cupón generado, pero falló el envío de email: {e}",
            "url": cupon.get("url"),
        }

    return {
        "ok": True,
        "email_enviado": True,
        "mensaje": f"Cupón de recarga enviado a {alumno.email}",
        "url": cupon.get("url"),
    }
