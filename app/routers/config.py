from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user, requiere_admin
from app.seguridad import auditar
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


class SistemaConfig(BaseModel):
    apai_razon_social: str
    apai_cuit: str
    apai_domicilio: str
    apai_condicion_iva: str
    tarjeta_activa: bool


@router.get("/sistema")
def obtener_sistema(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Datos fiscales de APAI y módulos activos (lo usa toda la interfaz)."""
    return {"apai": config_util.datos_apai(db), "tarjeta_activa": config_util.tarjeta_activa(db)}


@router.post("/sistema")
def guardar_sistema(data: SistemaConfig, request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    antes = config_util.tarjeta_activa(db)
    for clave in ("apai_razon_social", "apai_cuit", "apai_domicilio", "apai_condicion_iva"):
        config_util.set_config(db, clave, str(getattr(data, clave)).strip()[:200])
    config_util.set_config(db, "tarjeta_activa", "1" if data.tarjeta_activa else "0")
    if antes != data.tarjeta_activa:
        auditar(db, "tarjeta_" + ("reactivada" if data.tarjeta_activa else "suspendida"), admin["sub"], None, request)
        db.commit()
    return {"ok": True, "mensaje": "Configuración guardada"}
