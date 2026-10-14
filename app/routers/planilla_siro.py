"""
Planilla Excel para cargar los cupones de la cuota en SIRO (modelo "carga de cupones SIRO").

Columnas: Nro Cliente | 1º Vto | 1º Monto | 2º Vto | 2º Monto | 3º Vto | 3º Monto.
Solo se completan el número de cliente, el primer vencimiento y el primer monto.

Número de cliente, tal cual, sin agregarle dígitos:
- Aeronavegantes y exámenes: el DNI.
- Ciclo Básico, Aviónica y Mecánica: el legajo.
"""
import io
import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import requiere_admin
from app.cuenta_alumno import estado_cuenta
from app.database import get_db
from app.models.alumno import Alumno
from app.routers.cuotas import cursos_vigentes, extras_por_alumno, pagos_del_anio, planes_de
from app.seguridad import auditar
from app.tz import ahora_ar

router = APIRouter(prefix="/api/cupones-siro/planilla", tags=["Cupones SIRO"])

AREAS_CON_DNI = {"aeronavegantes", "examenes", "exámenes"}
ORDEN_AREAS = ["Ciclo Basico", "Avionica", "Mecanica", "Aeronavegantes", "Examenes"]
ENCABEZADOS = ["Nro Cliente", "1º Vto", "1º Monto", "2º Vto", "2º Monto", "3º Vto", "3º Monto"]


class CursoPlanilla(BaseModel):
    curso_id: int
    importe: Decimal | None = Field(default=None, gt=0, le=10_000_000)


class Pedido(BaseModel):
    vencimiento: date
    cursos: list[CursoPlanilla] = Field(min_length=1, max_length=50)
    anio: int | None = None
    excluir_pagados: bool = True


def usa_dni(area: str | None) -> bool:
    return (area or "").strip().lower() in AREAS_CON_DNI


def _exento(a: Alumno) -> bool:
    return (a.condicion or "").strip().lower() in ("becado", "exento") or bool(a.cuota_excluir)


def _anio(p: int | None) -> int:
    return p or ahora_ar().year


def _alumnos_con_planes(db: Session, anio: int):
    cursos = cursos_vigentes(db, anio)
    extras = extras_por_alumno(db, anio)
    for a in db.query(Alumno).filter(Alumno.activo == True).order_by(Alumno.apellido, Alumno.nombre).all():  # noqa: E712
        yield a, planes_de(a, cursos, extras.get(a.id, []))


@router.get("/cursos")
def cursos_para_planilla(anio: int | None = None, db: Session = Depends(get_db), _=Depends(requiere_admin)):
    """Cursos del año con su importe, qué número de cliente usan y cuántos alumnos reciben cupón."""
    anio = _anio(anio)
    conteo: dict[int, int] = {}
    for a, planes in _alumnos_con_planes(db, anio):
        if _exento(a):
            continue
        for pl in planes:
            if pl.get("curso_id"):
                conteo[pl["curso_id"]] = conteo.get(pl["curso_id"], 0) + 1
    orden = {x.lower(): i for i, x in enumerate(ORDEN_AREAS)}
    cursos = sorted(cursos_vigentes(db, anio), key=lambda c: (orden.get((c.area or "").lower(), 99), c.nombre))
    return [{"id": c.id, "nombre": c.nombre, "area": c.area, "importe": float(c.cuota or 0),
             "cliente": "DNI" if usa_dni(c.area) else "Legajo", "alumnos": conteo.get(c.id, 0)} for c in cursos]


def armar_filas(db: Session, data: Pedido) -> dict:
    anio = _anio(data.anio)
    cursos = {c.id: c for c in cursos_vigentes(db, anio)}
    pedidos = {}
    for x in data.cursos:
        if x.curso_id not in cursos:
            raise HTTPException(400, f"El curso {x.curso_id} no existe o no está activo en {anio}")
        pedidos[x.curso_id] = Decimal(x.importe) if x.importe else Decimal(cursos[x.curso_id].cuota or 0)
    pagos = pagos_del_anio(db, anio) if data.excluir_pagados else {}

    filas: dict[str, dict] = {}
    omitidos = {"becados": 0, "pagados": 0}
    sin_numero = []
    for a, planes in _alumnos_con_planes(db, anio):
        elegidos = [pl for pl in planes if pl.get("curso_id") in pedidos]
        if not elegidos:
            continue
        if _exento(a):
            omitidos["becados"] += 1
            continue
        completos = set()
        if data.excluir_pagados:
            info = estado_cuenta(a, planes, pagos.get(a.id, []), anio, hoy=ahora_ar().date())
            completos = {c["clave"] for c in info.get("cursos", []) if c.get("completo")}
        for pl in elegidos:
            curso = cursos[pl["curso_id"]]
            etiqueta = pl.get("etiqueta") or (a.curso if pl.get("principal") else curso.nombre)
            if pl["clave"] in completos:
                omitidos["pagados"] += 1
                continue
            importe = pedidos[curso.id]
            if pl.get("principal") and a.cuota_personalizada:
                importe = Decimal(a.cuota_personalizada)
            dni = usa_dni(curso.area)
            numero = re.sub(r"\D", "", a.dni or "") if dni else (a.legajo or "").strip()
            if not numero.isdigit():
                sin_numero.append({"alumno": f"{a.apellido}, {a.nombre}", "curso": etiqueta,
                                   "motivo": "No tiene DNI cargado" if dni else f"No tiene legajo numérico (figura «{a.legajo}»)"})
                continue
            f = filas.get(numero)
            if f:  # mismo número de cliente en dos cursos elegidos: un solo cupón con la suma
                f["importe"] += importe
                f["cursos"].append(etiqueta)
            else:
                filas[numero] = {"cliente": numero, "tipo": "DNI" if dni else "Legajo", "alumno_id": a.id,
                                 "alumno": f"{a.apellido}, {a.nombre}", "cursos": [etiqueta],
                                 "importe": importe, "personalizado": importe != pedidos[curso.id]}
    lista = sorted(filas.values(), key=lambda f: (f["cursos"][0], f["alumno"]))
    return {"filas": lista, "omitidos": omitidos, "sin_numero": sin_numero, "anio": anio,
            "total": sum((f["importe"] for f in lista), Decimal(0))}


@router.post("/vista")
def vista(data: Pedido, db: Session = Depends(get_db), _=Depends(requiere_admin)):
    r = armar_filas(db, data)
    return {**r, "total": float(r["total"]),
            "filas": [{**f, "importe": float(f["importe"]), "cursos": " + ".join(f["cursos"])} for f in r["filas"]]}


def generar_excel(filas: list[dict], vencimiento: date) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    borde = Border(*(Side(style="thin", color="000000"),) * 4)
    gris = PatternFill("solid", fgColor="A6A6A6")
    for i, t in enumerate(ENCABEZADOS, 1):
        c = ws.cell(row=1, column=i, value=t)
        c.font, c.fill, c.border, c.alignment = Font(bold=True), gris, borde, Alignment(horizontal="center")
        c.number_format = "mm-dd-yy" if i == 2 else ("0.00" if i in (3, 5, 7) else "General")
    for r, f in enumerate(filas, 2):
        valores = [int(f["cliente"]), vencimiento, float(f["importe"]), None, None, None, None]
        for i, v in enumerate(valores, 1):
            c = ws.cell(row=r, column=i, value=v)
            c.border = borde
        ws.cell(row=r, column=2).number_format = "mm-dd-yy"
        ws.cell(row=r, column=3).number_format = "0.00"
    for letra, ancho in zip("ABCDEFG", (14, 12, 12, 10, 10, 10, 10)):
        ws.column_dimensions[letra].width = ancho
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.post("/excel")
def excel(data: Pedido, request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    r = armar_filas(db, data)
    if not r["filas"]:
        raise HTTPException(400, "No hay alumnos para generar cupones con esos cursos")
    nombres = sorted({c for f in r["filas"] for c in f["cursos"]})
    auditar(db, "planilla_siro", admin["sub"],
            f"{len(r['filas'])} cupones, vence {data.vencimiento:%d/%m/%Y}, total ${r['total']:,.2f}: {', '.join(nombres)[:300]}", request)
    db.commit()
    nombre = f"cupones_siro_{data.vencimiento:%Y-%m-%d}.xlsx"
    return StreamingResponse(io.BytesIO(generar_excel(r["filas"], data.vencimiento)),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
