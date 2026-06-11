from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.proveedor import Proveedor
from app.schemas.proveedor import ProveedorCreate, ProveedorUpdate, ProveedorResponse

router = APIRouter(prefix="/api/proveedores", tags=["Proveedores"])


def _norm_cuit(cuit: str) -> str:
    return "".join(ch for ch in str(cuit) if ch.isdigit())


@router.get("/", response_model=list[ProveedorResponse])
def listar(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Proveedor)
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(
            Proveedor.razon_social.ilike(t),
            Proveedor.nombre_fantasia.ilike(t),
            Proveedor.cuit.ilike(t),
            Proveedor.rubro.ilike(t),
        ))
    return query.order_by(Proveedor.razon_social).all()


@router.get("/{prov_id}", response_model=ProveedorResponse)
def obtener(prov_id: int, db: Session = Depends(get_db)):
    p = db.get(Proveedor, prov_id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    return p


@router.post("/", response_model=ProveedorResponse, status_code=201)
def crear(data: ProveedorCreate, db: Session = Depends(get_db)):
    cuit = _norm_cuit(data.cuit)
    if not cuit:
        raise HTTPException(400, "CUIT inválido")
    if db.query(Proveedor).filter(Proveedor.cuit == cuit).first():
        raise HTTPException(409, f"Ya existe un proveedor con CUIT {cuit}")
    p = Proveedor(**{**data.model_dump(), "cuit": cuit})
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{prov_id}", response_model=ProveedorResponse)
def actualizar(prov_id: int, data: ProveedorUpdate, db: Session = Depends(get_db)):
    p = db.get(Proveedor, prov_id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    cambios = data.model_dump(exclude_unset=True)
    if "cuit" in cambios and cambios["cuit"]:
        nuevo = _norm_cuit(cambios["cuit"])
        if nuevo != p.cuit and db.query(Proveedor).filter(Proveedor.cuit == nuevo).first():
            raise HTTPException(409, f"Ya existe un proveedor con CUIT {nuevo}")
        cambios["cuit"] = nuevo
    for campo, valor in cambios.items():
        setattr(p, campo, valor)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{prov_id}")
def eliminar(prov_id: int, db: Session = Depends(get_db)):
    p = db.get(Proveedor, prov_id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    db.delete(p)
    db.commit()
    return {"ok": True, "mensaje": f"Proveedor {p.razon_social} eliminado"}
