from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime, timedelta

from app.database import get_db
from app.models.alumno import Alumno
from app.models.tarjeta import Tarjeta
from app.models.saldo import Saldo
from app.models.movimiento import Movimiento
from app.tz import ahora_ar
from app.schemas.operaciones import (
    CobroRequest,
    RecargaRequest,
    TransferenciaRequest,
    ReintegroRequest,
    MovimientoResponse,
    OperacionResponse,
)

router = APIRouter(prefix="/api/operaciones", tags=["Operaciones"])


def _obtener_alumno_por_uid(uid: str, db: Session) -> tuple[Alumno, Tarjeta]:
    tarjeta = db.query(Tarjeta).filter(Tarjeta.uid == uid, Tarjeta.activa == True).first()
    if not tarjeta:
        raise HTTPException(404, "Tarjeta no encontrada o desactivada")
    alumno = tarjeta.alumno
    if not alumno.activo:
        raise HTTPException(403, "Alumno inactivo")
    return alumno, tarjeta


def _obtener_saldo(alumno_id: int, db: Session) -> Saldo:
    saldo = db.query(Saldo).filter(Saldo.alumno_id == alumno_id).with_for_update().first()
    if not saldo:
        saldo = Saldo(alumno_id=alumno_id)
        db.add(saldo)
        db.flush()
    return saldo


@router.post("/cobro", response_model=OperacionResponse)
def cobrar(data: CobroRequest, db: Session = Depends(get_db)):
    """Descuenta saldo por consumo (fotocopiadora, etc)."""
    alumno, _ = _obtener_alumno_por_uid(data.uid, db)
    saldo = _obtener_saldo(alumno.id, db)

    if saldo.monto < data.monto:
        raise HTTPException(
            400,
            f"Saldo insuficiente. Disponible: ${saldo.monto}, requerido: ${data.monto}",
        )

    saldo.monto -= data.monto
    db.add(Movimiento(
        alumno_id=alumno.id,
        tipo="consumo",
        monto=-data.monto,
        descripcion=data.descripcion or "Consumo",
        operador=data.operador,
    ))
    db.commit()

    return OperacionResponse(
        ok=True,
        mensaje=f"Cobro de ${data.monto} realizado a {alumno.apellido}, {alumno.nombre}",
        saldo_actual=saldo.monto,
    )


@router.post("/recarga", response_model=OperacionResponse)
def recargar(data: RecargaRequest, db: Session = Depends(get_db)):
    """Acredita saldo por transferencia bancaria recibida."""
    alumno = db.get(Alumno, data.alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")

    saldo = _obtener_saldo(alumno.id, db)
    saldo.monto += data.monto
    db.add(Movimiento(
        alumno_id=alumno.id,
        tipo="recarga",
        monto=data.monto,
        descripcion=data.descripcion or "Recarga por transferencia",
        operador=data.operador,
    ))
    db.commit()

    return OperacionResponse(
        ok=True,
        mensaje=f"Recarga de ${data.monto} acreditada a {alumno.apellido}, {alumno.nombre}",
        saldo_actual=saldo.monto,
    )


@router.post("/transferencia", response_model=OperacionResponse)
def transferir(data: TransferenciaRequest, db: Session = Depends(get_db)):
    """Transfiere saldo de un alumno a otro."""
    alumno_origen, _ = _obtener_alumno_por_uid(data.uid_origen, db)
    alumno_destino, _ = _obtener_alumno_por_uid(data.uid_destino, db)

    if alumno_origen.id == alumno_destino.id:
        raise HTTPException(400, "No se puede transferir al mismo alumno")

    saldo_origen = _obtener_saldo(alumno_origen.id, db)
    saldo_destino = _obtener_saldo(alumno_destino.id, db)

    if saldo_origen.monto < data.monto:
        raise HTTPException(
            400,
            f"Saldo insuficiente. Disponible: ${saldo_origen.monto}",
        )

    saldo_origen.monto -= data.monto
    saldo_destino.monto += data.monto

    desc = f"Transferencia a {alumno_destino.apellido}, {alumno_destino.nombre}"
    db.add(Movimiento(
        alumno_id=alumno_origen.id,
        tipo="transferencia_out",
        monto=-data.monto,
        descripcion=desc,
        referencia_id=alumno_destino.id,
        operador=data.operador,
    ))
    desc = f"Transferencia de {alumno_origen.apellido}, {alumno_origen.nombre}"
    db.add(Movimiento(
        alumno_id=alumno_destino.id,
        tipo="transferencia_in",
        monto=data.monto,
        descripcion=desc,
        referencia_id=alumno_origen.id,
        operador=data.operador,
    ))
    db.commit()

    return OperacionResponse(
        ok=True,
        mensaje=f"Transferencia de ${data.monto} realizada",
        saldo_actual=saldo_origen.monto,
    )


@router.post("/reintegro", response_model=OperacionResponse)
def reintegrar(data: ReintegroRequest, db: Session = Depends(get_db)):
    """Devuelve saldo en efectivo (máximo $2.500)."""
    alumno = db.get(Alumno, data.alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")

    saldo = _obtener_saldo(alumno.id, db)
    if saldo.monto < data.monto:
        raise HTTPException(
            400,
            f"Saldo insuficiente. Disponible: ${saldo.monto}",
        )

    saldo.monto -= data.monto
    db.add(Movimiento(
        alumno_id=alumno.id,
        tipo="reintegro",
        monto=-data.monto,
        descripcion="Reintegro en efectivo",
        operador=data.operador,
    ))
    db.commit()

    return OperacionResponse(
        ok=True,
        mensaje=f"Reintegro de ${data.monto} procesado para {alumno.apellido}, {alumno.nombre}",
        saldo_actual=saldo.monto,
    )


def _mov_con_alumno(m: Movimiento, a: Alumno) -> dict:
    return {
        "id": m.id,
        "alumno_id": m.alumno_id,
        "tipo": m.tipo,
        "monto": float(m.monto),
        "descripcion": m.descripcion,
        "operador": m.operador,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "apellido": a.apellido,
        "nombre": a.nombre,
        "curso": a.curso,
        "legajo": a.legajo,
    }


@router.get("/recientes")
def movimientos_recientes(limite: int = 10, db: Session = Depends(get_db)):
    """Ultimos N movimientos de todo el sistema (con datos del alumno)."""
    filas = (
        db.query(Movimiento, Alumno)
        .join(Alumno, Movimiento.alumno_id == Alumno.id)
        .order_by(Movimiento.created_at.desc())
        .limit(limite)
        .all()
    )
    return [_mov_con_alumno(m, a) for m, a in filas]


@router.get("/diario")
def movimientos_dia(fecha: str | None = None, db: Session = Depends(get_db)):
    """Todos los movimientos de un dia (por defecto hoy), con datos del alumno."""
    if fecha:
        base = datetime.strptime(fecha, "%Y-%m-%d")
    else:
        base = ahora_ar()
    inicio = base.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = inicio + timedelta(days=1)
    filas = (
        db.query(Movimiento, Alumno)
        .join(Alumno, Movimiento.alumno_id == Alumno.id)
        .filter(Movimiento.created_at >= inicio, Movimiento.created_at < fin)
        .order_by(Movimiento.created_at.desc())
        .all()
    )
    return [_mov_con_alumno(m, a) for m, a in filas]


@router.get("/historial/{alumno_id}", response_model=list[MovimientoResponse])
def historial(alumno_id: int, limite: int = 50, db: Session = Depends(get_db)):
    """Devuelve los últimos movimientos de un alumno."""
    alumno = db.get(Alumno, alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")
    return (
        db.query(Movimiento)
        .filter(Movimiento.alumno_id == alumno_id)
        .order_by(Movimiento.created_at.desc())
        .limit(limite)
        .all()
    )


@router.delete("/historial/{alumno_id}")
def limpiar_historial(alumno_id: int, db: Session = Depends(get_db)):
    """Elimina todos los movimientos de un alumno."""
    alumno = db.get(Alumno, alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")
    cantidad = db.query(Movimiento).filter(Movimiento.alumno_id == alumno_id).delete()
    db.commit()
    return {
        "ok": True,
        "mensaje": f"{cantidad} movimientos eliminados de {alumno.apellido}, {alumno.nombre}",
    }
