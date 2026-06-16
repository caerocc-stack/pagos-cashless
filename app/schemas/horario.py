from pydantic import BaseModel
from datetime import datetime, date, time
from decimal import Decimal


class EmpleadoCreate(BaseModel):
    nombre: str
    puesto: str | None = None
    horas_diarias: Decimal = Decimal("8")
    activo: bool = True


class EmpleadoUpdate(BaseModel):
    nombre: str | None = None
    puesto: str | None = None
    horas_diarias: Decimal | None = None
    activo: bool | None = None


class EmpleadoResponse(BaseModel):
    id: int
    nombre: str
    puesto: str | None = None
    horas_diarias: Decimal
    activo: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class RegistroCreate(BaseModel):
    empleado_id: int
    fecha: date
    tipo: str = "Normal"
    entrada: time | None = None
    salida: time | None = None
    notas: str | None = None


class RegistroUpdate(BaseModel):
    fecha: date | None = None
    tipo: str | None = None
    entrada: time | None = None
    salida: time | None = None
    notas: str | None = None
