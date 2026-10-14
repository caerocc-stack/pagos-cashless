"""
Pedidos de materiales y servicios.

Formulario público /pedidos (sin cuenta) para profesores y personal del colegio: datos de quien pide,
sector de destino y la lista de productos (marca, modelo, color, tamaño, características, cantidad,
unidad y descripción). Protecciones: campo trampa contra robots, límite de envíos por IP y por día,
textos acotados y sin HTML.

La administración los gestiona desde el sistema (estado, notas internas, corrección de los ítems) y
exporta un PDF solo con los materiales para pedir presupuestos a proveedores (ese PDF se arma en el
navegador y no incluye los datos de quien hizo el pedido).
"""
import os
import re
from datetime import date
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app import consultas_util as cu
from app.auth import requiere_admin
from app.database import get_db
from app.models.pedido import ESTADOS, PedidoItem, PedidoMaterial
from app.seguridad import auditar, ip_cliente, registrar_fallo, segundos_bloqueo
from app.tz import ahora_ar

publico = APIRouter(prefix="/api/publico", tags=["Pedidos de materiales (público)"])
router = APIRouter(prefix="/api/pedidos", tags=["Pedidos de materiales"])

POR_IP_HORA, POR_DIA = 15, 200
APP_URL = (os.getenv("APP_URL") or "https://pagos-cashless.vercel.app").rstrip("/")
TIPOS = ("materiales", "servicio", "ambos")


def _texto(v, n: int) -> str | None:
    if v is None:
        return None
    v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f<>]", " ", str(v))
    v = re.sub(r"[ \t]+", " ", v).strip()
    return v[:n] or None


class ItemIn(BaseModel):
    producto: str = Field(min_length=1, max_length=160)
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=60)
    tamanio: str | None = Field(default=None, max_length=80)
    caracteristicas: str | None = Field(default=None, max_length=300)
    cantidad: Decimal = Field(gt=0, le=1_000_000)
    unidad: str = Field(default="Unidad", max_length=30)
    descripcion: str | None = Field(default=None, max_length=1000)

    @field_validator("producto", "marca", "modelo", "color", "tamanio", "caracteristicas", "unidad", "descripcion", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return _texto(v, 1000) if isinstance(v, str) else v


class PedidoIn(BaseModel):
    solicitante: str = Field(min_length=3, max_length=120)
    cargo: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=150)
    telefono: str | None = Field(default=None, max_length=40)
    sector: str = Field(min_length=2, max_length=120)
    tipo: str = "materiales"
    motivo: str | None = Field(default=None, max_length=1500)
    necesario_para: date | None = None
    urgente: bool = False
    items: list[ItemIn] = Field(min_length=1, max_length=80)
    web: str | None = None  # campo trampa

    @field_validator("solicitante", "cargo", "telefono", "sector", "motivo", mode="before")
    @classmethod
    def _limpiar(cls, v):
        return _texto(v, 1500) if isinstance(v, str) else v

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        v = (v or "").strip().lower()
        if not v:
            return None
        if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", v):
            raise ValueError("El correo no es válido")
        return v

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v):
        return v if v in TIPOS else "materiales"


def _cargar_items(p: PedidoMaterial, items: list[ItemIn]):
    p.items.clear()
    for i, it in enumerate(items):
        p.items.append(PedidoItem(orden=i, producto=it.producto, marca=it.marca, modelo=it.modelo, color=it.color,
                                  tamanio=it.tamanio, caracteristicas=it.caracteristicas, cantidad=it.cantidad,
                                  unidad=it.unidad or "Unidad", descripcion=it.descripcion))


def numero(p: PedidoMaterial) -> str:
    return f"{p.id:05d}"


def _item_dto(it: PedidoItem) -> dict:
    return {"producto": it.producto, "marca": it.marca, "modelo": it.modelo, "color": it.color, "tamanio": it.tamanio,
            "caracteristicas": it.caracteristicas, "cantidad": float(it.cantidad), "unidad": it.unidad,
            "descripcion": it.descripcion}


def _dto(p: PedidoMaterial, completo: bool = False) -> dict:
    d = {"id": p.id, "numero": numero(p), "creado": p.creado.isoformat() if p.creado else None,
         "tipo": p.tipo, "solicitante": p.solicitante, "cargo": p.cargo, "sector": p.sector,
         "necesario_para": p.necesario_para.isoformat() if p.necesario_para else None, "urgente": p.urgente,
         "estado": p.estado, "estado_texto": ESTADOS.get(p.estado, p.estado), "n_items": len(p.items),
         "resumen": ", ".join(it.producto for it in p.items[:3]) + ("…" if len(p.items) > 3 else "")}
    if completo:
        d.update(email=p.email, telefono=p.telefono, motivo=p.motivo, notas=p.notas,
                 actualizado=p.actualizado.isoformat() if p.actualizado else None,
                 items=[_item_dto(it) for it in p.items])
    return d


# ------------------------------------------------------------------ público

@publico.post("/pedidos")
def recibir_pedido(data: PedidoIn, request: Request, db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    if data.web:  # campo trampa: solo lo completan los robots
        raise HTTPException(400, "No se pudo procesar el envío.")
    if segundos_bloqueo(db, f"pedidos-ip:{ip}", POR_IP_HORA, 60) or segundos_bloqueo(db, "pedidos-dia", POR_DIA, 1440):
        raise HTTPException(429, "Se recibieron demasiados pedidos seguidos. Probá de nuevo en un rato.")
    if data.necesario_para and data.necesario_para < ahora_ar().date():
        raise HTTPException(400, "La fecha para cuándo se necesita ya pasó.")
    registrar_fallo(db, f"pedidos-ip:{ip}")
    registrar_fallo(db, "pedidos-dia")
    p = PedidoMaterial(tipo=data.tipo, solicitante=data.solicitante, cargo=data.cargo, email=data.email,
                       telefono=data.telefono, sector=data.sector, motivo=data.motivo,
                       necesario_para=data.necesario_para, urgente=data.urgente, ip=ip)
    _cargar_items(p, data.items)
    db.add(p)
    db.commit()

    lista = "".join(f"<li>{escape(f'{it.cantidad:g}')} {escape(it.unidad)} · {escape(it.producto)}</li>" for it in p.items[:15])
    cuerpo = (f"<p><b>{escape(p.solicitante)}</b>{' (' + escape(p.cargo) + ')' if p.cargo else ''} pidió "
              f"{'<b>con urgencia</b> ' if p.urgente else ''}para <b>{escape(p.sector)}</b>:</p><ul>{lista}</ul>")
    cu.avisar_admins(db, f"Pedido de materiales N° {numero(p)}", cuerpo, f"{APP_URL}/#pedidos")
    if p.email:
        cu.enviar_seguro(p.email, f"APAI · Recibimos tu pedido N° {numero(p)}", cu._plantilla(
            "Pedido de materiales",
            f"<p>Hola {escape(p.solicitante.split(' ')[0])}, recibimos tu pedido <b>N° {numero(p)}</b> para "
            f"<b>{escape(p.sector)}</b> con {len(p.items)} ítem{'s' if len(p.items) != 1 else ''}.</p>"
            f"<ul>{lista}</ul><p>La administración de APAI lo va a revisar y te avisamos cualquier novedad.</p>",
            None, ""))
    return {"ok": True, "numero": numero(p), "items": len(p.items)}


# ------------------------------------------------------------------ administración

@router.get("/")
def listar(estado: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PedidoMaterial).options(selectinload(PedidoMaterial.items))
    if estado == "abiertos":
        q = q.filter(PedidoMaterial.estado.notin_(("entregado", "rechazado")))
    elif estado:
        q = q.filter(PedidoMaterial.estado == estado)
    return [_dto(p) for p in q.order_by(PedidoMaterial.id.desc()).limit(500).all()]


@router.get("/contador")
def contador(db: Session = Depends(get_db)):
    filas = dict(db.query(PedidoMaterial.estado, func.count(PedidoMaterial.id)).group_by(PedidoMaterial.estado).all())
    return {"nuevos": filas.get("nuevo", 0), "por_estado": filas,
            "abiertos": sum(v for k, v in filas.items() if k not in ("entregado", "rechazado"))}


@router.get("/estados")
def estados():
    return ESTADOS


def _pedido(db: Session, pid: int) -> PedidoMaterial:
    p = db.get(PedidoMaterial, pid)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    return p


@router.get("/{pid}")
def ver(pid: int, db: Session = Depends(get_db)):
    return _dto(_pedido(db, pid), completo=True)


class PedidoEdit(BaseModel):
    estado: str | None = None
    notas: str | None = Field(default=None, max_length=3000)
    sector: str | None = Field(default=None, max_length=120)
    urgente: bool | None = None
    items: list[ItemIn] | None = Field(default=None, max_length=80)


@router.put("/{pid}")
def editar(pid: int, data: PedidoEdit, request: Request, db: Session = Depends(get_db), usuario=Depends(requiere_admin)):
    p = _pedido(db, pid)
    cambios = []
    if data.estado is not None:
        if data.estado not in ESTADOS:
            raise HTTPException(400, "Estado inválido")
        if data.estado != p.estado:
            cambios.append(f"estado {ESTADOS.get(p.estado)} → {ESTADOS[data.estado]}")
            p.estado = data.estado
    if data.notas is not None:
        p.notas = _texto(data.notas.replace("\n", " "), 3000)
        p.notas = p.notas.replace(" ", "\n") if p.notas else None
    if data.sector is not None and _texto(data.sector, 120):
        p.sector = _texto(data.sector, 120)
    if data.urgente is not None:
        p.urgente = data.urgente
    if data.items is not None:
        if not data.items:
            raise HTTPException(400, "El pedido tiene que tener al menos un ítem")
        _cargar_items(p, data.items)
        cambios.append("ítems corregidos")
    p.actualizado = ahora_ar()
    if cambios:
        auditar(db, "pedido_materiales", usuario["sub"], f"Pedido N° {numero(p)}: {', '.join(cambios)}", request)
    db.commit()
    return _dto(p, completo=True)


@router.delete("/{pid}")
def borrar(pid: int, request: Request, db: Session = Depends(get_db), usuario=Depends(requiere_admin)):
    p = _pedido(db, pid)
    auditar(db, "pedido_borrado", usuario["sub"], f"Pedido N° {numero(p)} de {p.solicitante} ({p.sector})", request)
    db.delete(p)
    db.commit()
    return {"ok": True}
