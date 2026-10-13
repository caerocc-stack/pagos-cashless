"""
Cupones de SIRO cargados desde el PDF que descarga la Asociación (un cupón por página).

El PDF se lee en el navegador (puede pesar decenas de MB, más que el límite de subida del servidor):
de cada página se toman el texto, el enlace de pago, la imagen del código de barras y el contenido
del QR. Acá llegan solo esos datos, se validan, se asocian al alumno y quedan visibles en el portal
hasta su último vencimiento.

Identificador del cupón (8 dígitos): "000" + legajo para los alumnos de 1° a 7°, o el DNI para
aeronavegantes y exámenes (misma regla que los pagos de SIRO).
"""
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import requiere_admin
from app.database import get_db
from app.models.alumno import Alumno
from app.models.portal import CuponEnviado
from app.routers.cuotas import _indices, _matchear, planes_de, extras_por_alumno, cursos_vigentes
from app.seguridad import auditar, qr_svg_data_uri
from app.tz import ahora_ar

router = APIRouter(prefix="/api/cupones-siro", tags=["Cupones SIRO"])

URL_PAGO = re.compile(r"^https://siropagos\.bancoroela\.com\.ar/Home/PagoOffLine/\d{10,30}/?$")
DATA_PNG = "data:image/png;base64,"
MAX_IMAGEN = 120_000  # caracteres del data URI


class Vencimiento(BaseModel):
    fecha: date
    importe: Decimal


class CuponPDF(BaseModel):
    pagina: int | None = None
    identificador: str = Field(max_length=20)
    nombre: str | None = Field(default=None, max_length=150)
    descripcion: str | None = Field(default=None, max_length=150)
    periodo: str | None = Field(default=None, max_length=40)
    vencimientos: list[Vencimiento] = Field(min_length=1, max_length=3)
    codigo_pago: str | None = Field(default=None, max_length=30)
    codigo_barras: str | None = Field(default=None, max_length=80)
    pago_url: str | None = Field(default=None, max_length=300)
    qr_texto: str | None = Field(default=None, max_length=1500)
    qr_imagen: str | None = None
    barras_imagen: str | None = None


class Lote(BaseModel):
    archivo: str | None = Field(default=None, max_length=150)
    lote: str | None = Field(default=None, max_length=40)
    cupones: list[CuponPDF] = Field(max_length=1000)


def _solo_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _imagen_valida(v: str | None) -> str | None:
    if not v:
        return None
    if not v.startswith(DATA_PNG) or len(v) > MAX_IMAGEN or not re.fullmatch(r"[A-Za-z0-9+/=]+", v[len(DATA_PNG):]):
        raise HTTPException(400, "Imagen de cupón inválida.")
    return v


def _validar(c: CuponPDF) -> None:
    if len(_solo_digitos(c.identificador)) < 7:
        raise HTTPException(400, f"Página {c.pagina}: identificador inválido.")
    for campo in ("codigo_pago", "codigo_barras"):
        v = getattr(c, campo)
        if v and not v.isdigit():
            raise HTTPException(400, f"Página {c.pagina}: {campo.replace('_', ' ')} inválido.")
    if c.pago_url and not URL_PAGO.match(c.pago_url):
        raise HTTPException(400, f"Página {c.pagina}: el enlace de pago no es de SIRO.")
    if any(v.importe <= 0 for v in c.vencimientos):
        raise HTTPException(400, f"Página {c.pagina}: importe inválido.")


def _palabras(s: str) -> set[str]:
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return {w for w in re.findall(r"[a-zñ]+", s) if len(w) > 2}


def _analizar(db: Session, cupones: list[CuponPDF]) -> list[dict]:
    by_leg, by_dni = _indices(db)
    hoy = ahora_ar().date()
    cursos = cursos_vigentes(db, hoy.year)
    extras = extras_por_alumno(db, hoy.year)
    barras = [c.codigo_barras for c in cupones if c.codigo_barras]
    ya = {b for (b,) in db.query(CuponEnviado.codigo_barras).filter(CuponEnviado.codigo_barras.in_(barras)).all()} if barras else set()
    salida = []
    for c in cupones:
        _validar(c)
        a, via = _matchear(_solo_digitos(c.identificador), by_leg, by_dni)
        avisos = []
        if a and c.nombre and not (_palabras(c.nombre) & _palabras(f"{a.apellido} {a.nombre}")):
            avisos.append("el nombre del cupón no coincide con el del padrón")
        importe = c.vencimientos[0].importe
        if a:
            planes = planes_de(a, cursos, extras.get(a.id, []))
            if planes:
                validos = set()
                for pl in planes:
                    validos |= {Decimal(str(pl["curso"].cuota or 0)), Decimal(str(pl["curso"].matricula or 0))}
                if a.cuota_personalizada:
                    validos.add(Decimal(str(a.cuota_personalizada)))
                if importe not in validos:
                    nombres = ", ".join(f"{pl['nombre']} ${pl['curso'].cuota:,.0f}".replace(",", ".") for pl in planes)
                    avisos.append(f"importe distinto al de sus cursos ({nombres}): ¿le falta agregar un curso?")
        vence = max(v.fecha for v in c.vencimientos)
        salida.append({
            "pagina": c.pagina, "identificador": c.identificador, "nombre_cupon": c.nombre,
            "concepto": " ".join(x for x in (c.descripcion, c.periodo) if x), "importe": float(importe),
            "vence": vence.isoformat(), "vencido": vence < hoy, "repetido": bool(c.codigo_barras and c.codigo_barras in ya),
            "qr": bool(c.qr_texto or c.qr_imagen), "barras": bool(c.barras_imagen),
            "alumno": {"id": a.id, "nombre": f"{a.apellido}, {a.nombre}", "curso": a.curso, "legajo": a.legajo, "via": via} if a else None,
            "avisos": avisos,
        })
    return salida


@router.post("/previsualizar")
def previsualizar(data: Lote, db: Session = Depends(get_db), _=Depends(requiere_admin)):
    filas = _analizar(db, data.cupones)
    return {"filas": filas, "total": len(filas),
            "con_alumno": sum(1 for f in filas if f["alumno"]), "sin_alumno": sum(1 for f in filas if not f["alumno"]),
            "repetidos": sum(1 for f in filas if f["repetido"]), "vencidos": sum(1 for f in filas if f["vencido"]),
            "con_avisos": sum(1 for f in filas if f["avisos"])}


@router.post("/importar")
def importar(data: Lote, request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    """Guarda (o actualiza) los cupones con alumno. Se puede llamar en tandas con el mismo `lote`."""
    lote = data.lote or uuid.uuid4().hex[:12]
    filas = _analizar(db, data.cupones)
    nuevos = actualizados = omitidos = 0
    for c, f in zip(data.cupones, filas):
        if not f["alumno"] or f["vencido"]:
            omitidos += 1
            continue
        x = None
        if c.codigo_barras:
            x = db.query(CuponEnviado).filter(CuponEnviado.alumno_id == f["alumno"]["id"],
                                              CuponEnviado.codigo_barras == c.codigo_barras).first()
        if x:
            actualizados += 1
        else:
            x = CuponEnviado(alumno_id=f["alumno"]["id"], tipo="cuota", email_enviado=False)
            db.add(x)
            nuevos += 1
        v = sorted(c.vencimientos, key=lambda v: v.fecha)
        x.origen, x.lote, x.archivo = "siro_pdf", lote, (data.archivo or "")[:150]
        x.identificador, x.nombre_cupon, x.periodo = _solo_digitos(c.identificador), c.nombre, c.periodo
        x.concepto = f["concepto"][:200] or "Cupón de pago"
        x.monto, x.vencimiento = v[0].importe, v[0].fecha
        x.vencimiento2, x.monto2 = (v[1].fecha, v[1].importe) if len(v) > 1 else (None, None)
        x.vencimiento3, x.monto3 = (v[2].fecha, v[2].importe) if len(v) > 2 else (None, None)
        x.vence_ultimo = v[-1].fecha
        x.codigo_pago, x.codigo_barras, x.pago_url = c.codigo_pago, c.codigo_barras, c.pago_url
        x.qr_texto = c.qr_texto
        x.qr_imagen = None if c.qr_texto else _imagen_valida(c.qr_imagen)
        x.barras_imagen = _imagen_valida(c.barras_imagen)
        x.url = c.pago_url
    # Limpieza: los cupones de SIRO vencidos hace más de 4 meses ya no sirven
    db.query(CuponEnviado).filter(CuponEnviado.origen == "siro_pdf",
                                  CuponEnviado.vence_ultimo < ahora_ar().date() - timedelta(days=120)).delete(synchronize_session=False)
    auditar(db, "cupones_siro", admin["sub"], f"{data.archivo or ''}: {nuevos} nuevos, {actualizados} actualizados", request)
    db.commit()
    return {"ok": True, "lote": lote, "nuevos": nuevos, "actualizados": actualizados, "omitidos": omitidos}


@router.get("/lotes")
def lotes(db: Session = Depends(get_db)):
    hoy = ahora_ar().date()
    filas = (db.query(CuponEnviado.lote, func.max(CuponEnviado.archivo), func.min(CuponEnviado.created_at),
                      func.count(CuponEnviado.id), func.max(CuponEnviado.vence_ultimo), func.max(CuponEnviado.concepto),
                      func.sum(CuponEnviado.monto))
             .filter(CuponEnviado.origen == "siro_pdf").group_by(CuponEnviado.lote)
             .order_by(func.min(CuponEnviado.created_at).desc()).limit(60).all())
    return [{"lote": l, "archivo": arch, "cargado": cre.strftime("%Y-%m-%dT%H:%M:%S") if cre else None, "cupones": n,
             "vence": v.isoformat() if v else None, "vigente": bool(v and v >= hoy), "concepto": conc,
             "total": float(tot or 0)} for l, arch, cre, n, v, conc, tot in filas]


@router.delete("/lotes/{lote}")
def borrar_lote(lote: str, request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    n = db.query(CuponEnviado).filter(CuponEnviado.origen == "siro_pdf", CuponEnviado.lote == lote).delete(synchronize_session=False)
    auditar(db, "cupones_siro_borrados", admin["sub"], f"lote {lote}: {n} cupones", request)
    db.commit()
    return {"ok": True, "borrados": n}


def cupon_dto(x: CuponEnviado, con_imagenes: bool = True) -> dict:
    venc = [{"fecha": f.isoformat(), "importe": float(m)} for f, m in
            ((x.vencimiento, x.monto), (x.vencimiento2, x.monto2), (x.vencimiento3, x.monto3)) if f and m is not None]
    d = {"id": x.id, "origen": x.origen or "sistema", "tipo": x.tipo, "concepto": x.concepto, "periodo": x.periodo,
         "monto": float(x.monto), "fecha": x.created_at.strftime("%Y-%m-%dT%H:%M:%S") if x.created_at else None,
         "vencimientos": venc, "vence": x.vence_ultimo.isoformat() if x.vence_ultimo else None,
         "codigo_pago": x.codigo_pago, "codigo_barras": x.codigo_barras,
         "pago_url": x.pago_url if x.pago_url and URL_PAGO.match(x.pago_url) else None,
         "url": x.url if (x.url or "").startswith("https://") else None}
    if con_imagenes:
        d["qr"] = qr_svg_data_uri(x.qr_texto) if x.qr_texto else x.qr_imagen
        d["barras_imagen"] = x.barras_imagen
    return d


def cupones_vigentes(db: Session, alumno_id: int, con_imagenes: bool = True) -> list[dict]:
    """Cupones que todavía se pueden pagar. Los de SIRO dejan de mostrarse después de su último vencimiento;
    los generados por el sistema (sin vencimiento cargado) se muestran 40 días."""
    hoy = ahora_ar().date()
    lista = (db.query(CuponEnviado).filter(CuponEnviado.alumno_id == alumno_id)
             .order_by(CuponEnviado.vence_ultimo.desc().nullslast(), CuponEnviado.created_at.desc()).limit(30).all())
    vigentes = [x for x in lista if (x.vence_ultimo and x.vence_ultimo >= hoy)
                or (not x.vence_ultimo and x.created_at and x.created_at.date() >= hoy - timedelta(days=40))]
    return [cupon_dto(x, con_imagenes) for x in vigentes]


def ultimo_codigo_pago(db: Session, alumno_id: int) -> str | None:
    x = (db.query(CuponEnviado.codigo_pago).filter(CuponEnviado.alumno_id == alumno_id, CuponEnviado.codigo_pago.isnot(None))
         .order_by(CuponEnviado.created_at.desc()).first())
    return x[0] if x else None


@router.get("/alumno/{alumno_id}")
def de_alumno(alumno_id: int, db: Session = Depends(get_db)):
    if not db.get(Alumno, alumno_id):
        raise HTTPException(404, "Alumno no encontrado")
    return cupones_vigentes(db, alumno_id)
