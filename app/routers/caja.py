from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.caja import MovimientoCaja, TIPOS_MOVIMIENTO
from app.schemas.caja import CajaCreate, CajaUpdate, CajaResponse
from app.config_util import get_config, set_config

router = APIRouter(prefix="/api/caja", tags=["Caja"])

CLAVE_SALDO_INICIAL = "caja_saldo_inicial"


def _saldo_inicial(db: Session) -> Decimal:
    try:
        return Decimal(get_config(db, CLAVE_SALDO_INICIAL) or "0")
    except Exception:
        return Decimal("0")


class SaldoInicial(BaseModel):
    valor: Decimal


@router.get("/meta")
def meta():
    return {"tipos_movimiento": TIPOS_MOVIMIENTO}


@router.get("/saldo-inicial")
def obtener_saldo_inicial(db: Session = Depends(get_db)):
    return {"valor": float(_saldo_inicial(db))}


@router.put("/saldo-inicial")
def fijar_saldo_inicial(data: SaldoInicial, db: Session = Depends(get_db)):
    set_config(db, CLAVE_SALDO_INICIAL, str(data.valor))
    return {"ok": True, "valor": float(data.valor)}


@router.get("/", response_model=list[CajaResponse])
def listar(
    q: str | None = None,
    tipo: str | None = None,
    mes: int | None = None,
    anio: int | None = None,
    db: Session = Depends(get_db),
):
    # Se calcula el saldo acumulado sobre TODOS los movimientos en orden cronologico,
    # para que el saldo de cada fila refleje el arrastre real (aunque se filtre por mes).
    todos = db.query(MovimientoCaja).order_by(
        MovimientoCaja.fecha.asc(), MovimientoCaja.id.asc()
    ).all()
    saldo = _saldo_inicial(db)
    saldos: dict[int, Decimal] = {}
    for m in todos:
        if m.tipo == "ingreso":
            saldo += m.monto
        else:
            saldo -= m.monto
        saldos[m.id] = saldo

    # Aplicar filtros para lo que se muestra
    def coincide(m: MovimientoCaja) -> bool:
        if tipo and m.tipo != tipo:
            return False
        if anio and m.fecha.year != anio:
            return False
        if mes and m.fecha.month != mes:
            return False
        if q:
            t = q.strip().lower()
            campos = [m.concepto, m.tipo_movimiento, m.notas]
            if not any((c or "").lower().find(t) >= 0 for c in campos):
                return False
        return True

    visibles = [m for m in todos if coincide(m)]
    # Mostrar del mas reciente al mas antiguo
    visibles.sort(key=lambda m: (m.fecha, m.id), reverse=True)
    salida = []
    for m in visibles:
        r = CajaResponse.model_validate(m)
        r.saldo = saldos[m.id]
        salida.append(r)
    return salida


@router.get("/resumen")
def resumen(mes: int | None = None, anio: int | None = None, db: Session = Depends(get_db)):
    base = db.query(MovimientoCaja)
    if anio:
        base = base.filter(extract("year", MovimientoCaja.fecha) == anio)
    if mes:
        base = base.filter(extract("month", MovimientoCaja.fecha) == mes)

    def suma(tipo, query):
        return query.filter(MovimientoCaja.tipo == tipo).with_entities(
            func.coalesce(func.sum(MovimientoCaja.monto), 0)).scalar() or 0

    ing_per = Decimal(str(suma("ingreso", base)))
    egr_per = Decimal(str(suma("egreso", base)))
    cant = base.count()

    # Saldo actual = saldo inicial + todos los ingresos - todos los egresos (sin filtro)
    total = db.query(MovimientoCaja)
    ing_total = Decimal(str(suma("ingreso", total)))
    egr_total = Decimal(str(suma("egreso", total)))
    saldo_actual = _saldo_inicial(db) + ing_total - egr_total

    return {
        "ingresos_periodo": float(ing_per),
        "egresos_periodo": float(egr_per),
        "neto_periodo": float(ing_per - egr_per),
        "saldo_actual": float(saldo_actual),
        "saldo_inicial": float(_saldo_inicial(db)),
        "cantidad": cant,
    }


@router.post("/", response_model=CajaResponse, status_code=201)
def crear(data: CajaCreate, db: Session = Depends(get_db)):
    if data.tipo not in ("ingreso", "egreso"):
        raise HTTPException(400, "El tipo debe ser 'ingreso' o 'egreso'")
    m = MovimientoCaja(**data.model_dump())
    m.monto = abs(m.monto)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.put("/{mov_id}", response_model=CajaResponse)
def actualizar(mov_id: int, data: CajaUpdate, db: Session = Depends(get_db)):
    m = db.get(MovimientoCaja, mov_id)
    if not m:
        raise HTTPException(404, "Movimiento no encontrado")
    cambios = data.model_dump(exclude_unset=True)
    if "monto" in cambios and cambios["monto"] is not None:
        cambios["monto"] = abs(cambios["monto"])
    for campo, valor in cambios.items():
        setattr(m, campo, valor)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{mov_id}")
def eliminar(mov_id: int, db: Session = Depends(get_db)):
    m = db.get(MovimientoCaja, mov_id)
    if not m:
        raise HTTPException(404, "Movimiento no encontrado")
    db.delete(m)
    db.commit()
    return {"ok": True, "mensaje": "Movimiento de caja eliminado"}
