"""
Compras hechas por un encargado (administración, profesores): el banco no le paga al proveedor sino a la
persona que compró, como reintegro de lo que puso o como adelanto para comprar. La factura igual está a
nombre de APAI.

Una transferencia a un encargado ("rendición") se vincula con una o varias facturas de cualquier proveedor
(Gasto.banco_mov_id). La factura queda pagada por transferencia, con la fecha del extracto y "pagada vía
<encargado>". La transferencia queda conciliada cuando lo rendido iguala lo transferido (±$1) o cuando se
la da por rendida con una nota (vuelto devuelto, diferencia a favor del encargado, etc.).
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.factura_pdf import digitos
from app.models.banco import EncargadoCompra, MovimientoBanco
from app.models.gasto import Gasto

TOLERANCIA = Decimal("1.00")


def facturas_de(db: Session, mov: MovimientoBanco) -> list[Gasto]:
    return db.query(Gasto).filter(Gasto.banco_mov_id == mov.id).order_by(Gasto.fecha, Gasto.id).all()


def rendido(db: Session, mov: MovimientoBanco) -> Decimal:
    return sum((Decimal(str(g.importe)) for g in facturas_de(db, mov)), Decimal(0))


def encargado_de(db: Session, mov: MovimientoBanco) -> EncargadoCompra | None:
    """El encargado elegido para esta transferencia o, si no, el que tiene el CUIT del destinatario."""
    if mov.encargado_id:
        return db.get(EncargadoCompra, mov.encargado_id)
    c = digitos(mov.cuit)
    if c:
        return db.query(EncargadoCompra).filter(EncargadoCompra.cuit == c, EncargadoCompra.activo.is_(True)).first()
    return None


def actualizar_estado(db: Session, mov: MovimientoBanco):
    """Conciliada si lo rendido cubre la transferencia o si se dio por rendida."""
    if mov.gasto_id:  # vinculada directo a una factura del proveedor: no es una rendición
        return
    saldo = abs(Decimal(str(mov.importe))) - rendido(db, mov)
    hay = bool(facturas_de(db, mov))
    mov.conciliado = bool(mov.rendicion_cerrada) or (hay and abs(saldo) <= TOLERANCIA)
    mov.conciliado_manual = mov.conciliado


def vincular(db: Session, mov: MovimientoBanco, g: Gasto, encargado: EncargadoCompra):
    g.banco_mov_id = mov.id
    g.conciliado = True
    g.forma_pago = "Transferencia"
    g.fecha_pago = mov.fecha  # cuando salió la plata del banco
    g.pagado_por = encargado.nombre
    mov.encargado_id = encargado.id


def desvincular(db: Session, g: Gasto):
    """La factura vuelve a quedar sin pagar y la transferencia recalcula lo que falta rendir."""
    mov = db.get(MovimientoBanco, g.banco_mov_id) if g.banco_mov_id else None
    g.banco_mov_id = None
    g.conciliado = False
    g.forma_pago = g.fecha_pago = g.pagado_por = None
    db.flush()
    if mov:
        actualizar_estado(db, mov)


def resumen(db: Session, mov: MovimientoBanco) -> dict:
    enc = encargado_de(db, mov)
    total = abs(Decimal(str(mov.importe)))
    r = rendido(db, mov)
    return {"encargado": {"id": enc.id, "nombre": enc.nombre} if enc else None,
            "transferido": float(total), "rendido": float(r), "saldo": float(total - r),
            "facturas": len(facturas_de(db, mov)), "cerrada": bool(mov.rendicion_cerrada), "nota": mov.rendicion_nota}
