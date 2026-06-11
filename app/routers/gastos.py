from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.gasto import Gasto, CATEGORIAS, FORMAS_PAGO, TIPOS_COMPROBANTE
from app.models.proveedor import Proveedor
from app.schemas.gasto import GastoCreate, GastoUpdate, GastoResponse

router = APIRouter(prefix="/api/gastos", tags=["Gastos"])


def _completar_proveedor(data: dict, db: Session):
    """Si se eligio un proveedor, copia su razon social y CUIT al gasto."""
    if data.get("proveedor_id"):
        p = db.get(Proveedor, data["proveedor_id"])
        if not p:
            raise HTTPException(404, "Proveedor no encontrado")
        data.setdefault("razon_social", None)
        data.setdefault("cuit", None)
        if not data.get("razon_social"):
            data["razon_social"] = p.razon_social
        if not data.get("cuit"):
            data["cuit"] = p.cuit
    return data


@router.get("/meta")
def meta():
    """Listas fijas para los desplegables del formulario."""
    return {
        "categorias": CATEGORIAS,
        "formas_pago": FORMAS_PAGO,
        "tipos_comprobante": TIPOS_COMPROBANTE,
    }


@router.get("/", response_model=list[GastoResponse])
def listar(
    q: str | None = None,
    categoria: str | None = None,
    forma_pago: str | None = None,
    mes: int | None = None,
    anio: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Gasto)
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(
            Gasto.razon_social.ilike(t),
            Gasto.cuit.ilike(t),
            Gasto.concepto.ilike(t),
            Gasto.rubro.ilike(t),
            Gasto.destino.ilike(t),
            Gasto.numero.ilike(t),
        ))
    if categoria:
        query = query.filter(Gasto.categoria == categoria)
    if forma_pago:
        query = query.filter(Gasto.forma_pago == forma_pago)
    if anio:
        query = query.filter(extract("year", Gasto.fecha) == anio)
    if mes:
        query = query.filter(extract("month", Gasto.fecha) == mes)
    return query.order_by(Gasto.fecha.desc(), Gasto.id.desc()).all()


@router.get("/resumen")
def resumen(mes: int | None = None, anio: int | None = None, db: Session = Depends(get_db)):
    """Total general y subtotales por categoria (respeta los filtros de mes/anio)."""
    query = db.query(Gasto)
    if anio:
        query = query.filter(extract("year", Gasto.fecha) == anio)
    if mes:
        query = query.filter(extract("month", Gasto.fecha) == mes)
    total = query.with_entities(func.coalesce(func.sum(Gasto.importe), 0)).scalar() or 0
    por_cat = (
        query.with_entities(Gasto.categoria, func.coalesce(func.sum(Gasto.importe), 0), func.count(Gasto.id))
        .group_by(Gasto.categoria).all()
    )
    cantidad = query.count()
    return {
        "total": float(total),
        "cantidad": cantidad,
        "por_categoria": [
            {"categoria": c or "Sin categoría", "total": float(t), "cantidad": n}
            for c, t, n in por_cat
        ],
    }


@router.get("/{gasto_id}", response_model=GastoResponse)
def obtener(gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    return g


@router.post("/", response_model=GastoResponse, status_code=201)
def crear(data: GastoCreate, db: Session = Depends(get_db)):
    d = _completar_proveedor(data.model_dump(), db)
    g = Gasto(**d)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@router.put("/{gasto_id}", response_model=GastoResponse)
def actualizar(gasto_id: int, data: GastoUpdate, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    cambios = _completar_proveedor(data.model_dump(exclude_unset=True), db)
    for campo, valor in cambios.items():
        setattr(g, campo, valor)
    db.commit()
    db.refresh(g)
    return g


@router.delete("/{gasto_id}")
def eliminar(gasto_id: int, db: Session = Depends(get_db)):
    g = db.get(Gasto, gasto_id)
    if not g:
        raise HTTPException(404, "Gasto no encontrado")
    db.delete(g)
    db.commit()
    return {"ok": True, "mensaje": "Gasto eliminado"}
