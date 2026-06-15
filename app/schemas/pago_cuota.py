from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal


class AlumnoMini(BaseModel):
    id: int
    legajo: str
    apellido: str
    nombre: str
    curso: str | None = None
    area: str | None = None

    model_config = {"from_attributes": True}


class PagoCuotaResponse(BaseModel):
    id: int
    alumno_id: int | None = None
    cliente_siro: str | None = None
    via: str | None = None
    importe: Decimal
    fecha: date
    fecha_pago: date | None = None
    canal: str | None = None
    mes: int
    anio: int
    origen: str | None = None
    created_at: datetime
    alumno: AlumnoMini | None = None

    model_config = {"from_attributes": True}
