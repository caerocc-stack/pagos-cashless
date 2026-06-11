from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal


class CajaCreate(BaseModel):
    fecha: date
    concepto: str
    tipo_movimiento: str | None = None
    tipo: str  # 'ingreso' o 'egreso'
    monto: Decimal
    notas: str | None = None


class CajaUpdate(BaseModel):
    fecha: date | None = None
    concepto: str | None = None
    tipo_movimiento: str | None = None
    tipo: str | None = None
    monto: Decimal | None = None
    notas: str | None = None


class CajaResponse(BaseModel):
    id: int
    fecha: date
    concepto: str
    tipo_movimiento: str | None = None
    tipo: str
    monto: Decimal
    notas: str | None = None
    saldo: Decimal | None = None  # saldo acumulado (lo calcula el router)
    created_at: datetime

    model_config = {"from_attributes": True}
