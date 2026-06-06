from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user
from app import config_util

router = APIRouter(prefix="/api/config", tags=["Configuracion"])


class EmailConfig(BaseModel):
    asunto: str
    mensaje: str


@router.get("/email")
def obtener_email(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {
        "asunto": config_util.get_config(db, "cupon_asunto"),
        "mensaje": config_util.get_config(db, "cupon_mensaje"),
    }


@router.post("/email")
def guardar_email(data: EmailConfig, db: Session = Depends(get_db), user=Depends(get_current_user)):
    config_util.set_config(db, "cupon_asunto", data.asunto.strip())
    config_util.set_config(db, "cupon_mensaje", data.mensaje.strip())
    return {"ok": True, "mensaje": "Mensaje del email actualizado"}
