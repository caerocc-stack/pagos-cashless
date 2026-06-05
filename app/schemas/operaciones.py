from pydantic import BaseModel, field_validator
from datetime import datetime
from decimal import Decimal

RECARGA_MINIMA = Decimal("1000.00")
REINTEGRO_MAXIMO = Decimal("2500.00")


class CobroRequest(BaseModel):
    uid: str
    monto: Decimal
    descripcion: str | None = None
    operador: str

    @field_validator("monto")
    @classmethod
    def monto_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("El monto debe ser mayor a cero")
        return v


class RecargaRequest(BaseModel):
    alumno_id: int
    monto: Decimal
    operador: str
    descripcion: str | None = None

    @field_validator("monto")
    @classmethod
    def monto_minimo(cls, v: Decimal) -> Decimal:
        if v < RECARGA_MINIMA:
            raise ValueError(f"La recarga mínima es ${RECARGA_MINIMA}")
        return v


class TransferenciaRequest(BaseModel):
    uid_origen: str
    uid_destino: str
    monto: Decimal
    operador: str

    @field_validator("monto")
    @classmethod
    def monto_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("El monto debe ser mayor a cero")
        return v


class ReintegroRequest(BaseModel):
    alumno_id: int
    monto: Decimal
    operador: str

    @field_validator("monto")
    @classmethod
    def monto_valido(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("El monto debe ser mayor a cero")
        if v > REINTEGRO_MAXIMO:
            raise ValueError(f"El reintegro máximo es ${REINTEGRO_MAXIMO}")
        return v


class MovimientoResponse(BaseModel):
    id: int
    alumno_id: int
    tipo: str
    monto: Decimal
    descripcion: str | None
    referencia_id: int | None
    operador: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OperacionResponse(BaseModel):
    ok: bool
    mensaje: str
    saldo_actual: Decimal
