from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class CursoBase(BaseModel):
    nombre: str
    area: str | None = None
    patron: str | None = None
    divisiones: str | None = None
    cuota: Decimal = Decimal("0")
    n_cuotas: int = 10
    matricula: Decimal = Decimal("0")
    cuota_anio_anterior: Decimal = Decimal("0")
    cobra_cuotas_viejas: bool = False
    anio: int = 2026
    activo: bool = True


class CursoCreate(CursoBase):
    pass


class CursoUpdate(BaseModel):
    nombre: str | None = None
    area: str | None = None
    patron: str | None = None
    divisiones: str | None = None
    cuota: Decimal | None = None
    n_cuotas: int | None = None
    matricula: Decimal | None = None
    cuota_anio_anterior: Decimal | None = None
    cobra_cuotas_viejas: bool | None = None
    anio: int | None = None
    activo: bool | None = None


class CursoResponse(CursoBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
