from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from decimal import Decimal

from app.database import get_db
from app.models.alumno import Alumno
from app import siro, email_util, config_util

router = APIRouter(prefix="/api/cupones", tags=["Cupones SIRO"])


class EnvioRequest(BaseModel):
    tipo: str  # "recarga" | "cuota"
    alumno_id: int
    monto: Decimal | None = None


class CuotaMasivaRequest(BaseModel):
    curso: str | None = None
    monto: Decimal | None = None


class PreviewRequest(BaseModel):
    tipo: str  # "recarga" | "cuota"
    monto: Decimal | None = None


def _formato_monto(monto) -> str:
    return f"${monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _monto_de(db: Session, tipo: str, monto: Decimal | None) -> Decimal:
    if monto and monto > 0:
        return monto
    if tipo == "cuota":
        try:
            return Decimal(config_util.get_config(db, "cuota_monto"))
        except Exception:
            return Decimal("45000")
    raise HTTPException(400, "Indicá el monto a recargar")


def _cuerpo_email(db: Session, tipo: str, alumno, monto, url) -> str:
    monto_str = _formato_monto(monto)
    plantilla = config_util.get_config(db, f"{tipo}_mensaje")
    mensaje = config_util.aplicar_comodines(plantilla, alumno, monto_str).replace("\n", "<br>")
    boton = (
        f'<a href="{url}" style="background:#a01e22;color:#fff;text-decoration:none;'
        f'padding:12px 28px;border-radius:8px;font-weight:bold;display:inline-block">Pagar cupón</a>'
        if url else ''
    )
    titulo = "Cuota societaria" if tipo == "cuota" else "Recarga ApaiCard"
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;color:#15233b">
        <div style="background:#15233b;color:#fff;padding:16px 20px;border-radius:10px 10px 0 0">
            <h2 style="margin:0">APAI Pay</h2>
            <div style="color:#9bb6d6;font-size:13px">{titulo}</div>
        </div>
        <div style="border:1px solid #e2e8f0;border-top:none;padding:20px;border-radius:0 0 10px 10px">
            <p style="font-size:24px;font-weight:bold;color:#16a34a;text-align:center;margin:6px 0 18px">{monto_str}</p>
            <div style="line-height:1.5">{mensaje}</div>
            <p style="text-align:center;margin:24px 0">{boton}</p>
        </div>
    </div>
    """


def _asunto(db: Session, tipo: str, alumno, monto) -> str:
    return config_util.aplicar_comodines(
        config_util.get_config(db, f"{tipo}_asunto"), alumno, _formato_monto(monto)
    )


def _generar_y_enviar(db: Session, tipo: str, alumno, monto) -> dict:
    """Genera el cupón en SIRO y lo envía por email. Devuelve el resultado."""
    cupon = siro.generar_cupon(alumno, monto, concepto=("Cuota APAI" if tipo == "cuota" else "Recarga ApaiCard"))
    if not email_util.email_configurado():
        return {"email_enviado": False, "url": cupon.get("url"), "motivo": "email no configurado"}
    email_util.enviar_email(
        destino=alumno.email,
        asunto=_asunto(db, tipo, alumno, monto),
        cuerpo_html=_cuerpo_email(db, tipo, alumno, monto, cupon.get("url")),
    )
    return {"email_enviado": True, "url": cupon.get("url")}


@router.post("/enviar")
def enviar_cupon(data: EnvioRequest, db: Session = Depends(get_db)):
    if data.tipo not in ("recarga", "cuota"):
        raise HTTPException(400, "Tipo de cupón inválido")
    alumno = db.get(Alumno, data.alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")
    if not alumno.email:
        raise HTTPException(400, "El alumno no tiene email cargado.")
    if not siro.siro_configurado():
        raise HTTPException(400, "SIRO todavía no está configurado. Cargá las credenciales para activar el envío.")

    monto = _monto_de(db, data.tipo, data.monto)
    try:
        res = _generar_y_enviar(db, data.tipo, alumno, monto)
    except Exception as e:
        raise HTTPException(400, str(e))

    if res["email_enviado"]:
        return {"ok": True, "mensaje": f"Cupón enviado a {alumno.email}", "url": res.get("url")}
    return {"ok": True, "mensaje": "Cupón generado, pero el email no está configurado.", "url": res.get("url")}


@router.post("/cuota-masiva")
def cuota_masiva(data: CuotaMasivaRequest, db: Session = Depends(get_db)):
    if not siro.siro_configurado():
        raise HTTPException(400, "SIRO todavía no está configurado. Cargá las credenciales para activar el envío.")
    if not email_util.email_configurado():
        raise HTTPException(400, "El envío de email no está configurado todavía.")

    monto = _monto_de(db, "cuota", data.monto)
    query = db.query(Alumno).filter(Alumno.activo == True)
    if data.curso:
        query = query.filter(Alumno.curso == data.curso)
    alumnos = query.order_by(Alumno.apellido, Alumno.nombre).all()

    enviados = 0
    sin_email = 0
    errores = []
    for a in alumnos:
        if not a.email:
            sin_email += 1
            continue
        try:
            _generar_y_enviar(db, "cuota", a, monto)
            enviados += 1
        except Exception as e:
            errores.append(f"{a.apellido}, {a.nombre}: {e}")

    return {
        "ok": True,
        "mensaje": f"Cuota de {config_util.mes_actual()}: {enviados} enviados, {sin_email} sin email, {len(errores)} con error",
        "enviados": enviados,
        "sin_email": sin_email,
        "errores": errores[:30],
    }


@router.post("/preview")
def preview(data: PreviewRequest, db: Session = Depends(get_db), user=None):
    """Devuelve el email renderizado con datos de ejemplo (no envía nada)."""
    tipo = data.tipo if data.tipo in ("recarga", "cuota") else "recarga"
    alumno = db.query(Alumno).order_by(Alumno.apellido).first()
    if alumno is None:
        class _Demo:
            apellido = "PEREZ"; nombre = "Juan"; legajo = "25199"; curso = "1°A Ciclo Basico"
        alumno = _Demo()
    monto = _monto_de(db, tipo, data.monto) if (data.monto or tipo == "cuota") else Decimal("5000")
    return {
        "asunto": _asunto(db, tipo, alumno, monto),
        "html": _cuerpo_email(db, tipo, alumno, monto, "#"),
    }
