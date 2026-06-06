from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user
from app import config_util

router = APIRouter(prefix="/api/config", tags=["Configuracion"])


class PlantillasConfig(BaseModel):
    recarga_asunto: str
    recarga_mensaje: str
    cuota_asunto: str
    cuota_mensaje: str
    cuota_monto: str


@router.get("/plantillas")
def obtener_plantillas(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {k: config_util.get_config(db, k) for k in config_util.CLAVES_PLANTILLAS}


@router.post("/plantillas")
def guardar_plantillas(data: PlantillasConfig, db: Session = Depends(get_db), user=Depends(get_current_user)):
    for clave, valor in data.model_dump().items():
        config_util.set_config(db, clave, str(valor).strip())
    return {"ok": True, "mensaje": "Plantillas actualizadas"}
