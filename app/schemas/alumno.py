from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal


class AlumnoCreate(BaseModel):
    legajo: str
    dni: str
    nombre: str
    apellido: str
    curso: str
    area: str | None = None
    division: str | None = None
    email: str | None = None
    telefono: str | None = None
    fecha_nacimiento: date | None = None
    condicion: str | None = None
    modalidad: str | None = None
    cuota_excluir: bool = False
    cuota_personalizada: Decimal | None = None


class AlumnoUpdate(BaseModel):
    legajo: str | None = None
    dni: str | None = None
    nombre: str | None = None
    apellido: str | None = None
    curso: str | None = None
    area: str | None = None
    division: str | None = None
    email: str | None = None
    telefono: str | None = None
    fecha_nacimiento: date | None = None
    condicion: str | None = None
    modalidad: str | None = None
    cuota_excluir: bool | None = None
    cuota_personalizada: Decimal | None = None
    activo: bool | None = None


class AlumnoResponse(BaseModel):
    id: int
    legajo: str
    dni: str
    nombre: str
    apellido: str
    curso: str
    area: str | None = None
    division: str | None = None
    email: str | None = None
    telefono: str | None = None
    fecha_nacimiento: date | None = None
    condicion: str | None = None
    modalidad: str | None = None
    cuota_excluir: bool = False
    cuota_personalizada: Decimal | None = None
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlumnoConSaldo(AlumnoResponse):
    saldo: Decimal = Decimal("0.00")
    codigo_siro: str = ""
