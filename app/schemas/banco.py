from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal


class GastoMini(BaseModel):
    id: int
    fecha: date
    razon_social: str | None = None
    cuit: str | None = None
    importe: Decimal
    concepto: str | None = None
    numero: str | None = None

    model_config = {"from_attributes": True}


class BancoMovResponse(BaseModel):
    id: int
    fecha: date
    cuenta: str | None = None
    comprobante: str | None = None
    concepto: str | None = None
    descripcion: str | None = None
    cuit: str | None = None
    razon_social: str | None = None
    importe: Decimal
    gasto_id: int | None = None
    conciliado: bool
    conciliado_manual: bool
    origen: str | None = None
    created_at: datetime
    gasto: GastoMini | None = None

    model_config = {"from_attributes": True}
