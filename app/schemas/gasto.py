from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal


class GastoCreate(BaseModel):
    fecha: date
    tipo_comprobante: str | None = None
    punto_venta: str | None = None
    numero: str | None = None
    proveedor_id: int | None = None
    razon_social: str | None = None
    cuit: str | None = None
    importe: Decimal
    concepto: str | None = None
    rubro: str | None = None
    categoria: str | None = None
    destino: str | None = None
    forma_pago: str | None = None
    fecha_pago: date | None = None
    adjunto_url: str | None = None
    nc_de_id: int | None = None
    notas: str | None = None


class GastoUpdate(BaseModel):
    fecha: date | None = None
    tipo_comprobante: str | None = None
    punto_venta: str | None = None
    numero: str | None = None
    proveedor_id: int | None = None
    razon_social: str | None = None
    cuit: str | None = None
    importe: Decimal | None = None
    concepto: str | None = None
    rubro: str | None = None
    categoria: str | None = None
    destino: str | None = None
    forma_pago: str | None = None
    fecha_pago: date | None = None
    adjunto_url: str | None = None
    nc_de_id: int | None = None
    conciliado: bool | None = None
    notas: str | None = None


class GastoResponse(BaseModel):
    id: int
    fecha: date
    tipo_comprobante: str | None = None
    punto_venta: str | None = None
    numero: str | None = None
    proveedor_id: int | None = None
    razon_social: str | None = None
    cuit: str | None = None
    importe: Decimal
    concepto: str | None = None
    rubro: str | None = None
    categoria: str | None = None
    destino: str | None = None
    forma_pago: str | None = None
    fecha_pago: date | None = None
    caja_mov_id: int | None = None
    adjunto_url: str | None = None
    nc_de_id: int | None = None
    conciliado: bool
    notas: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
