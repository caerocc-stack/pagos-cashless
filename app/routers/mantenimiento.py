"""Mantenimiento (solo administradores): dejar en cero la parte financiera para empezar de nuevo.

No toca alumnos, tarjetas, saldos de tarjeta, cuotas ni usuarios.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import requiere_admin, verify_password
from app.models.usuario import Usuario
from app.models.gasto import Gasto
from app.models.banco import MovimientoBanco, ExtractoBancario
from app.models.caja import MovimientoCaja
from app.models.proveedor import Proveedor
from app.models.pago_cuota import PagoCuota
from app.models.configuracion import Configuracion
from app.seguridad import auditar

router = APIRouter(prefix="/api/mantenimiento", tags=["Mantenimiento"], dependencies=[Depends(requiere_admin)])


@router.get("/conteos")
def conteos(db: Session = Depends(get_db)):
    """Cuántos registros hay de cada cosa (para mostrar antes de borrar)."""
    return {
        "gastos": db.query(Gasto).count(),
        "conciliacion": db.query(MovimientoBanco).count(),
        "extractos": db.query(ExtractoBancario).count(),
        "caja": db.query(MovimientoCaja).count(),
        "proveedores": db.query(Proveedor).count(),
    }


class Limpieza(BaseModel):
    password: str
    confirmacion: str
    gastos: bool = False
    conciliacion: bool = False
    caja: bool = False
    proveedores: bool = False


@router.post("/limpiar-finanzas")
def limpiar_finanzas(data: Limpieza, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    if data.confirmacion.strip().upper() != "BORRAR":
        raise HTTPException(400, 'Para confirmar escribí la palabra BORRAR.')
    u = db.get(Usuario, admin["uid"])
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(400, "La contraseña es incorrecta.")
    if data.proveedores and not data.gastos:
        raise HTTPException(400, "Para borrar los proveedores también hay que borrar los gastos (las facturas los usan).")
    if not any([data.gastos, data.conciliacion, data.caja, data.proveedores]):
        raise HTTPException(400, "Elegí al menos una cosa para borrar.")

    borrado = {}
    # Orden pensado para respetar las relaciones entre tablas
    if data.conciliacion or data.gastos:
        if data.conciliacion:
            borrado["conciliacion"] = db.query(MovimientoBanco).delete()
            borrado["extractos"] = db.query(ExtractoBancario).delete()
            if not data.gastos:  # los gastos quedan, pero ya sin pago bancario vinculado
                db.query(Gasto).filter(Gasto.conciliado.is_(True), Gasto.caja_mov_id.is_(None)).update(
                    {"conciliado": False, "forma_pago": None, "fecha_pago": None}, synchronize_session=False)
        else:  # se borran gastos pero se conserva el banco: liberar los movimientos
            db.query(MovimientoBanco).update({"gasto_id": None, "conciliado": False, "conciliado_manual": False},
                                             synchronize_session=False)
            db.query(ExtractoBancario).update({"comisiones_gasto_id": None}, synchronize_session=False)
    if data.gastos:
        db.query(Gasto).update({"nc_de_id": None}, synchronize_session=False)
        borrado["gastos"] = db.query(Gasto).delete()
    if data.caja:
        db.query(PagoCuota).filter(PagoCuota.caja_mov_id.isnot(None)).update({"caja_mov_id": None}, synchronize_session=False)
        if not data.gastos:
            db.query(Gasto).filter(Gasto.caja_mov_id.isnot(None)).update(
                {"caja_mov_id": None, "forma_pago": None, "fecha_pago": None}, synchronize_session=False)
        borrado["caja"] = db.query(MovimientoCaja).delete()
        db.query(Configuracion).filter(Configuracion.clave == "caja_saldo_inicial").delete()
    if data.proveedores:
        borrado["proveedores"] = db.query(Proveedor).delete()

    auditar(db, "limpieza_finanzas", admin["sub"], ", ".join(f"{k}: {v}" for k, v in borrado.items()), request)
    db.commit()
    return {"ok": True, "borrado": borrado,
            "mensaje": "Listo. Se borró: " + ", ".join(f"{v} {k}" for k, v in borrado.items())}
