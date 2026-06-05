from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class AlumnoCreate(BaseModel):
    legajo: str
    dni: str
    nombre: str
    apellido: str
    curso: str


class AlumnoUpdate(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    curso: str | None = None
    activo: bool | None = None


class AlumnoResponse(BaseModel):
    id: int
    legajo: str
    dni: str
    nombre: str
    apellido: str
    curso: str
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlumnoConSaldo(AlumnoResponse):
    saldo: Decimal = Decimal("0.00")
