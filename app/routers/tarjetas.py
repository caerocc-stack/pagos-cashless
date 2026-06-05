from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import get_db
from app.models.alumno import Alumno
from app.models.tarjeta import Tarjeta
from app.models.saldo import Saldo
from app.schemas.tarjeta import TarjetaEmitir, TarjetaResponse, TarjetaLectura, TarjetaInfoResponse

router = APIRouter(prefix="/api/tarjetas", tags=["Tarjetas"])


@router.post("/leer", response_model=TarjetaInfoResponse)
def leer_tarjeta(data: TarjetaLectura, db: Session = Depends(get_db)):
    """Lee una tarjeta y devuelve info del alumno + saldo."""
    tarjeta = db.query(Tarjeta).filter(Tarjeta.uid == data.uid).first()
    if not tarjeta:
        raise HTTPException(404, "Tarjeta no registrada en el sistema")
    if not tarjeta.activa:
        raise HTTPException(403, "Tarjeta desactivada — contactar a APAI")

    alumno = tarjeta.alumno
    if not alumno.activo:
        raise HTTPException(403, "Alumno inactivo en el sistema")

    saldo = alumno.saldo
    return TarjetaInfoResponse(
        alumno_id=alumno.id,
        legajo=alumno.legajo,
        nombre=alumno.nombre,
        apellido=alumno.apellido,
        curso=alumno.curso,
        saldo=saldo.monto if saldo else Decimal("0.00"),
        tarjeta_id=tarjeta.id,
    )


@router.post("/emitir", response_model=TarjetaResponse, status_code=201)
def emitir_tarjeta(data: TarjetaEmitir, db: Session = Depends(get_db)):
    """Asocia una tarjeta nueva a un alumno."""
    alumno = db.get(Alumno, data.alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")

    if db.query(Tarjeta).filter(Tarjeta.uid == data.uid).first():
        raise HTTPException(409, "Esta tarjeta ya está registrada")

    tarjeta = Tarjeta(uid=data.uid, alumno_id=data.alumno_id)
    db.add(tarjeta)
    db.commit()
    db.refresh(tarjeta)
    return tarjeta


@router.put("/{tarjeta_id}/desactivar", response_model=TarjetaResponse)
def desactivar_tarjeta(tarjeta_id: int, db: Session = Depends(get_db)):
    """Desactiva una tarjeta (pérdida/robo)."""
    tarjeta = db.get(Tarjeta, tarjeta_id)
    if not tarjeta:
        raise HTTPException(404, "Tarjeta no encontrada")
    tarjeta.activa = False
    db.commit()
    db.refresh(tarjeta)
    return tarjeta


@router.get("/alumno/{alumno_id}", response_model=list[TarjetaResponse])
def tarjetas_de_alumno(alumno_id: int, db: Session = Depends(get_db)):
    """Lista todas las tarjetas de un alumno."""
    return db.query(Tarjeta).filter(Tarjeta.alumno_id == alumno_id).all()
