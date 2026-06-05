from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class TarjetaEmitir(BaseModel):
    uid: str
    alumno_id: int


class TarjetaResponse(BaseModel):
    id: int
    uid: str
    alumno_id: int
    activa: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TarjetaLectura(BaseModel):
    uid: str


class TarjetaInfoResponse(BaseModel):
    alumno_id: int
    legajo: str
    nombre: str
    apellido: str
    curso: str
    saldo: Decimal
    tarjeta_id: int
