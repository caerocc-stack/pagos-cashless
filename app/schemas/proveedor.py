from pydantic import BaseModel
from datetime import datetime


class ProveedorCreate(BaseModel):
    cuit: str
    razon_social: str
    nombre_fantasia: str | None = None
    rubro: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    cbu: str | None = None
    notas: str | None = None


class ProveedorUpdate(BaseModel):
    cuit: str | None = None
    razon_social: str | None = None
    nombre_fantasia: str | None = None
    rubro: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    cbu: str | None = None
    notas: str | None = None
    activo: bool | None = None


class ProveedorResponse(BaseModel):
    id: int
    cuit: str
    razon_social: str
    nombre_fantasia: str | None = None
    rubro: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    cbu: str | None = None
    notas: str | None = None
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}
