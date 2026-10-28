import io
import re
import hashlib
from collections import Counter
from decimal import Decimal
from datetime import date, datetime

import xlrd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func, extract

from app.database import get_db
from app.models.pago_cuota import PagoCuota
from app.models.alumno import Alumno
from app.models.curso import Curso, AlumnoCurso
from app.models.caja import MovimientoCaja
from app.routers.cursos import curso_de_alumno
from app.schemas.pago_cuota import PagoCuotaResponse
from app.tz import ahora_ar
from app.cuenta_alumno import estado_cuenta, anio_de_pago, fecha_cobro, plan_simple, MES_INICIO, estado_con_anterior, libre_deuda_cursos

router = APIRouter(prefix="/api/cuotas", tags=["Cuotas"])


def _dig(x):
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return "".join(ch for ch in str(x) if ch.isdigit()) if x is not None else ""


def _indices(db: Session):
    """Construye indices del padron: por legajo (5 dig) y por DNI (ult 8)."""
    by_leg, by_dni = {}, {}
    for a in db.query(Alumno).all():
        leg = _dig(a.legajo)
        if leg and str(a.legajo).strip().isdigit():  # "D<dni>" = sin legajo: no se busca por legajo
            by_leg.setdefault(leg[-5:], a)
        d = _dig(a.dni)
        if len(d) >= 7:  # DNI real (los placeholders 'SL...' quedan afuera)
            by_dni.setdefault(d[-8:].zfill(8), a)
    return by_leg, by_dni


def _matchear(cliente, by_leg, by_dni):
    """Cliente SIRO = 1 dígito de concepto + 8 dígitos: el DNI, o "000" + legajo.
    Si los 8 dígitos no empiezan con 000 es un DNI: se busca primero por DNI para no confundirlo
    con un legajo que coincida con sus últimos 5 dígitos."""
    c = _dig(cliente)
    if not c:
        return None, None
    if len(c) >= 8 and not c[-8:].startswith("000"):
        a = by_dni.get(c[-8:].zfill(8))
        if a:
            return a, "dni"
    a = by_leg.get(c[-5:])
    if a:
        return a, "legajo"
    a = by_dni.get(c[-8:].zfill(8))
    if a:
        return a, "dni"
    return None, None


def reasignar_pendientes(db: Session) -> int:
    """Reasigna los pagos sin alumno a los que ahora existan en el padron. Devuelve cuantos asigno."""
    by_leg, by_dni = _indices(db)
    n = 0
    for p in db.query(PagoCuota).filter(PagoCuota.alumno_id.is_(None)).all():
        a, via = _matchear(p.cliente_siro, by_leg, by_dni)
        if a:
            p.alumno_id = a.id
            p.via = via
            n += 1
    if n:
        db.commit()
    return n


def _parsear_siro(contenido: bytes):
    try:
        wb = xlrd.open_workbook(file_contents=contenido)
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo. Tiene que ser el .xls del listado de cobranzas SIRO.")
    sh = wb.sheet_by_index(0)
    dm = wb.datemode

    fila_cab = None
    for r in range(min(6, sh.nrows)):
        textos = [str(sh.cell_value(r, c)).strip().lower() for c in range(sh.ncols)]
        if "cliente" in textos and "importe" in textos:
            fila_cab = r
            break
    if fila_cab is None:
        raise HTTPException(400, "El archivo no parece un listado de cobranzas SIRO (no encuentro las columnas).")

    cab = {str(sh.cell_value(fila_cab, c)).strip().lower(): c for c in range(sh.ncols)}
    c_cli = cab.get("cliente")
    c_imp = cab.get("importe")
    c_proc = next((c for t, c in cab.items() if "proceso" in t), None)
    c_pago = next((c for t, c in cab.items() if t == "fecha de pago"), None)
    c_canal = cab.get("canal")
    if None in (c_cli, c_imp, c_proc):
        raise HTTPException(400, "Faltan columnas (Cliente / Importe / Fecha de Proceso).")

    pagos = []
    repetidas: dict[str, int] = {}
    for r in range(fila_cab + 1, sh.nrows):
        cliente = str(sh.cell_value(r, c_cli)).strip()
        if not _dig(cliente):
            continue
        try:
            importe = Decimal(str(sh.cell_value(r, c_imp)))
        except Exception:
            continue
        if importe == 0:
            continue
        bruto_proc = sh.cell_value(r, c_proc)
        try:
            fecha = xlrd.xldate.xldate_as_datetime(float(bruto_proc), dm).date()
        except Exception:
            continue
        fecha_pago = None
        bruto_pago = sh.cell_value(r, c_pago) if c_pago is not None else None
        try:
            if bruto_pago:
                fecha_pago = xlrd.xldate.xldate_as_datetime(float(bruto_pago), dm).date()
        except Exception:
            pass
        canal = str(sh.cell_value(r, c_canal)).strip() if c_canal is not None else None
        try:  # la fecha de pago de SIRO trae hora, minuto y segundo: identifica a cada pago
            momento = xlrd.xldate.xldate_as_datetime(float(bruto_pago), dm) if bruto_pago else None
            momento = momento.replace(microsecond=0).isoformat() if momento else ""
        except Exception:
            momento = str(bruto_pago or "")
        clave = f"siro|{_dig(cliente).lstrip('0')}|{importe:.2f}|{fecha.isoformat()}|{momento}|{(canal or '').upper()}"
        repetidas[clave] = repetidas.get(clave, 0) + 1
        if repetidas[clave] > 1:  # dos renglones idénticos en el mismo listado: son dos pagos distintos
            clave += f"#{repetidas[clave]}"
        pagos.append({
            "cliente_siro": _dig(cliente), "importe": importe, "fecha": fecha,
            "fecha_pago": fecha_pago, "canal": canal or None,
            "mes": fecha.month, "anio": fecha.year,
            "hash": hashlib.sha1(clave.encode()).hexdigest()[:40],
            # huella con la que se guardaban antes (para reconocer los pagos ya cargados)
            "hash_anterior": hashlib.sha1(f"{cliente}|{importe}|{bruto_proc}|{bruto_pago}".encode()).hexdigest()[:40],
        })
    return pagos


FILA_PDF = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s+(-?)\s*\$\s*(-?)([\d.]+,\d{2})\s+(\d+)\s+"
                      r"(\d{1,2}/\d{1,2}/\d{4})\s+(?:\d{1,2}/\d{1,2}/\d{4}\s+)?(\S+)$")


def _parsear_siro_pdf(contenido: bytes):
    """El listado de cobranzas en PDF: los mismos pagos que el .xls, pero la fecha de pago viene sin hora."""
    import pdfplumber  # import diferido: solo se usa al importar PDFs

    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            lineas = [l.strip() for pg in pdf.pages for l in (pg.extract_text() or "").splitlines()]
    except Exception:
        raise HTTPException(400, "No se pudo abrir el PDF. Tiene que ser el listado de cobranzas descargado de SIRO.")
    cabecera = " ".join(lineas[:3])
    if "Listado Cobranzas" not in cabecera:
        if "Extracto de Cuenta" in cabecera:
            raise HTTPException(400, "Ese PDF es el extracto de cuenta del banco: se sube en Conciliación bancaria. "
                                     "Acá va el Listado de Cobranzas.")
        raise HTTPException(400, "El PDF no parece un listado de cobranzas SIRO.")

    def _f(t):
        return datetime.strptime(t, "%d/%m/%Y").date()

    pagos, leidos = [], 0
    repetidas: dict[str, int] = {}
    for l in lineas:
        m = FILA_PDF.match(l)
        if not m:
            continue
        leidos += 1
        proc, neg1, neg2, monto, cliente, pago, canal = m.groups()
        importe = Decimal(monto.replace(".", "").replace(",", "."))
        if neg1 or neg2:
            importe = -importe
        if importe == 0:
            continue
        fecha, fecha_pago = _f(proc), _f(pago)
        clave = f"siro-pdf|{cliente.lstrip('0')}|{importe:.2f}|{fecha.isoformat()}|{fecha_pago.isoformat()}|{canal.upper()}"
        repetidas[clave] = repetidas.get(clave, 0) + 1
        if repetidas[clave] > 1:
            clave += f"#{repetidas[clave]}"
        h = hashlib.sha1(clave.encode()).hexdigest()[:40]
        pagos.append({
            "cliente_siro": _dig(cliente), "importe": importe, "fecha": fecha,
            "fecha_pago": fecha_pago, "canal": canal,
            "mes": fecha.month, "anio": fecha.year, "hash": h, "hash_anterior": h,
        })
    cant = re.search(r"Cantidad de Cobranzas:\s*(\d+)", "\n".join(lineas))
    if cant and int(cant.group(1)) != leidos:
        raise HTTPException(400, f"No pude leer todos los pagos del PDF ({leidos} de {cant.group(1)}). "
                                 "Subí el .xls del mismo listado.")
    if not leidos:
        raise HTTPException(400, "No encontré pagos en el PDF.")
    return pagos


def _clave_dia(cliente, importe, fecha, fecha_pago, canal):
    """Un pago sin la hora: cliente, importe, fecha de proceso, fecha de pago y canal."""
    return (_dig(cliente).lstrip("0"), f"{Decimal(str(importe)):.2f}", fecha, fecha_pago, (canal or "").upper())


@router.post("/importar")
async def importar(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """Carga el listado de cobranzas de SIRO (.xls o .pdf) sin duplicar: los listados se pueden superponer
    (del 1 al 13 y después del 1 al 31) y solo entran los pagos que todavía no estaban. Cada pago se reconoce por
    cliente, importe, fecha de proceso, fecha y hora de pago y canal. El PDF no trae la hora: sus pagos se
    reconocen sin ella, y el .xls que llegue después reconoce los que vinieron de un PDF."""
    contenido = await archivo.read()
    es_pdf = contenido[:5] == b"%PDF-"
    pagos = _parsear_siro_pdf(contenido) if es_pdf else _parsear_siro(contenido)
    by_leg, by_dni = _indices(db)
    cargados = set()
    huellas = [h for p in pagos for h in (p["hash"], p["hash_anterior"])]
    for k in range(0, len(huellas), 500):
        cargados |= {h for (h,) in db.query(PagoCuota.hash).filter(PagoCuota.hash.in_(huellas[k:k + 500])).all()}
    previos = Counter()  # pagos ya cargados contados sin la hora (el PDF contra todo; el .xls contra lo que vino de PDF)
    if pagos:
        q = db.query(PagoCuota).filter(PagoCuota.cliente_siro.isnot(None),
                                       PagoCuota.fecha.between(min(p["fecha"] for p in pagos),
                                                               max(p["fecha"] for p in pagos)))
        if not es_pdf:
            q = q.filter(PagoCuota.origen.ilike("%.pdf"))
        previos = Counter(_clave_dia(x.cliente_siro, x.importe, x.fecha, x.fecha_pago, x.canal) for x in q)

    nuevos = duplicados = asignados = 0
    usadas = set()  # huellas anteriores ya reconocidas: cada pago viejo cubre un solo renglón
    for p in pagos:
        anterior = p.pop("hash_anterior")
        dia = _clave_dia(p["cliente_siro"], p["importe"], p["fecha"], p["fecha_pago"], p["canal"])
        if not es_pdf and (p["hash"] in cargados or (anterior in cargados and anterior not in usadas)):
            usadas.add(anterior)
            duplicados += 1
            continue
        if previos[dia] > 0 or (es_pdf and p["hash"] in cargados):
            previos[dia] = max(previos[dia] - 1, 0)
            duplicados += 1
            continue
        a, via = _matchear(p["cliente_siro"], by_leg, by_dni)
        db.add(PagoCuota(origen=archivo.filename, alumno_id=(a.id if a else None), via=via, **p))
        cargados.add(p["hash"])
        nuevos += 1
        if a:
            asignados += 1
    db.commit()
    return {
        "ok": True, "leidos": len(pagos), "nuevos": nuevos, "duplicados": duplicados,
        "asignados": asignados, "sin_asignar": nuevos - asignados,
    }


@router.post("/reasignar")
def reasignar(db: Session = Depends(get_db)):
    n = reasignar_pendientes(db)
    pend = db.query(func.count(PagoCuota.id)).filter(PagoCuota.alumno_id.is_(None)).scalar()
    return {"ok": True, "asignados": n, "sin_asignar": pend}


@router.get("/resumen")
def resumen(mes: int | None = None, anio: int | None = None, db: Session = Depends(get_db)):
    q = db.query(PagoCuota)
    if anio:
        q = q.filter(PagoCuota.anio == anio)
    if mes:
        q = q.filter(PagoCuota.mes == mes)
    total = q.count()
    asign = q.filter(PagoCuota.alumno_id.isnot(None)).count()
    monto = q.with_entities(func.coalesce(func.sum(PagoCuota.importe), 0)).scalar() or 0
    monto_sin = q.filter(PagoCuota.alumno_id.is_(None)).with_entities(
        func.coalesce(func.sum(PagoCuota.importe), 0)).scalar() or 0
    return {
        "total": total, "asignados": asign, "sin_asignar": total - asign,
        "monto_total": float(monto), "monto_sin_asignar": float(monto_sin),
    }


@router.get("/", response_model=list[PagoCuotaResponse])
def listar(estado: str | None = None, q: str | None = None,
           mes: int | None = None, anio: int | None = None,
           db: Session = Depends(get_db)):
    query = db.query(PagoCuota).options(joinedload(PagoCuota.alumno))
    if estado == "asignado":
        query = query.filter(PagoCuota.alumno_id.isnot(None))
    elif estado == "sin_asignar":
        query = query.filter(PagoCuota.alumno_id.is_(None))
    if anio:
        query = query.filter(PagoCuota.anio == anio)
    if mes:
        query = query.filter(PagoCuota.mes == mes)
    if q:
        t = f"%{q.strip()}%"
        query = query.filter(or_(PagoCuota.cliente_siro.ilike(t)))
    return query.order_by(PagoCuota.fecha.desc(), PagoCuota.id.desc()).limit(1000).all()


class ImputarEfectivo(BaseModel):
    alumno_id: int
    caja_mov_id: int | None = None
    importe: Decimal | None = None
    fecha: date | None = None


@router.post("/efectivo")
def imputar_efectivo(data: ImputarEfectivo, db: Session = Depends(get_db)):
    """Imputa un pago de cuota en efectivo a un alumno (opcionalmente desde un movimiento de caja)."""
    a = db.get(Alumno, data.alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    importe = data.importe
    fecha = data.fecha
    if data.caja_mov_id:
        # Evitar imputar dos veces el mismo movimiento de caja
        ya = db.query(PagoCuota).filter(PagoCuota.caja_mov_id == data.caja_mov_id).first()
        if ya:
            raise HTTPException(409, "Ese movimiento de caja ya está imputado a una cuota")
        mov = db.get(MovimientoCaja, data.caja_mov_id)
        if not mov:
            raise HTTPException(404, "Movimiento de caja no encontrado")
        importe = importe or Decimal(str(mov.monto))
        fecha = fecha or mov.fecha
    if not importe or not fecha:
        raise HTTPException(400, "Faltan importe y/o fecha del pago")
    importe = abs(Decimal(str(importe)))
    h = hashlib.sha1(f"efectivo|{data.caja_mov_id}|{a.id}|{importe}|{fecha}".encode()).hexdigest()[:40]
    pago = PagoCuota(
        alumno_id=a.id, via="efectivo", canal="Efectivo", caja_mov_id=data.caja_mov_id,
        cliente_siro=None, importe=importe, fecha=fecha, fecha_pago=fecha,
        mes=fecha.month, anio=fecha.year, origen="caja/efectivo", hash=h,
    )
    db.add(pago)
    db.commit()
    return {"ok": True, "mensaje": f"Pago en efectivo imputado a {a.apellido}, {a.nombre}"}


@router.post("/{pago_id}/asignar/{alumno_id}")
def asignar_manual(pago_id: int, alumno_id: int, db: Session = Depends(get_db)):
    p = db.get(PagoCuota, pago_id)
    a = db.get(Alumno, alumno_id)
    if not p or not a:
        raise HTTPException(404, "Pago o alumno no encontrado")
    p.alumno_id = a.id
    p.via = "manual"
    db.commit()
    return {"ok": True, "mensaje": f"Pago asignado a {a.apellido}, {a.nombre}"}


@router.delete("/{pago_id}")
def eliminar(pago_id: int, db: Session = Depends(get_db)):
    p = db.get(PagoCuota, pago_id)
    if not p:
        raise HTTPException(404, "Pago no encontrado")
    db.delete(p)
    db.commit()
    return {"ok": True, "mensaje": "Pago eliminado"}


# =========================================================
# --- ESTADO DE CUENTA Y ESTADISTICAS ---
# =========================================================
def _nivel(curso: str) -> str:
    m = re.match(r"\s*(\d+)", str(curso or ""))
    return f"{m.group(1)}°" if m else "Otros"


def _base_alumno(alumno) -> dict:
    return {"id": alumno.id, "legajo": alumno.legajo, "apellido": alumno.apellido, "nombre": alumno.nombre,
            "curso": alumno.curso, "area": alumno.area, "division": alumno.division, "nivel": _nivel(alumno.curso),
            "modalidad": alumno.modalidad, "condicion": alumno.condicion}


def _estado_de(alumno, planes, pagos, anio: int, mes_corte: int | None = None, detalle: bool = False) -> dict:
    """Estado de cuenta cuota por cuota (ver app/cuenta_alumno.py). Sin `detalle` devuelve solo el resumen."""
    info = estado_cuenta(alumno, planes, pagos, anio, hoy=ahora_ar().date(), mes_corte=mes_corte)
    if not detalle:
        for k in ("items", "pagos", "proximo"):
            info.pop(k, None)
        for c in info.get("cursos", []):
            c.pop("items", None)
    info["cursos_nombres"] = [c["nombre"] for c in info.get("cursos", [])]
    return {**_base_alumno(alumno), **info}


def planes_de(alumno, cursos: list[Curso], extras: list[AlumnoCurso]) -> list[dict]:
    """Cursos del alumno en el año: los cargados explícitamente (si cursa más de uno) o el de su padrón."""
    if extras:
        por_id = {c.id: c for c in cursos}
        planes = [{"clave": f"ac{x.id}", "curso": por_id[x.curso_id], "nombre": por_id[x.curso_id].nombre,
                   "mes_inicio": x.mes_inicio or por_id[x.curso_id].mes_inicio or MES_INICIO, "principal": bool(x.principal), "curso_id": x.curso_id,
                   "etiqueta": x.etiqueta,
                   "alumno_curso_id": x.id}
                  for x in sorted(extras, key=lambda x: (not x.principal, x.mes_inicio or MES_INICIO, x.id)) if x.curso_id in por_id]
        if planes:
            return planes
    return plan_simple(curso_de_alumno(alumno, cursos))


def cursos_vigentes(db: Session, anio: int) -> list[Curso]:
    cursos = db.query(Curso).filter(Curso.anio == anio, Curso.activo == True).all()  # noqa: E712
    cursos = cursos or db.query(Curso).filter(Curso.activo == True).all()  # noqa: E712
    # cursos por examen: sus instancias, para saber a qué examen fue cada pago (ver cuenta_alumno.instancia_de)
    por_examen = {c.id: c for c in cursos if c.por_examen}
    if por_examen:
        from app.models.curso import InstanciaExamen
        for c in por_examen.values():
            c._instancias = []
        for i in db.query(InstanciaExamen).filter(InstanciaExamen.curso_id.in_(list(por_examen))).all():
            por_examen[i.curso_id]._instancias.append(i)
    return cursos


def extras_por_alumno(db: Session, anio: int, alumno_id: int | None = None) -> dict[int, list[AlumnoCurso]]:
    q = db.query(AlumnoCurso).filter(AlumnoCurso.anio == anio)
    if alumno_id:
        q = q.filter(AlumnoCurso.alumno_id == alumno_id)
    salida: dict[int, list[AlumnoCurso]] = {}
    for x in q.all():
        salida.setdefault(x.alumno_id, []).append(x)
    return salida


def planes_alumno(db: Session, a: Alumno, anio: int) -> list[dict]:
    return planes_de(a, cursos_vigentes(db, anio), extras_por_alumno(db, anio, a.id).get(a.id, []))


def pagos_del_anio(db: Session, anio: int, alumno_id: int | None = None) -> dict[int, list]:
    """Pagos imputables al año (por fecha de pago: un pago del 30/12 acreditado en enero es del año anterior)."""
    q = db.query(PagoCuota).filter(PagoCuota.alumno_id.isnot(None),
                                   PagoCuota.fecha >= date(anio - 1, 12, 1), PagoCuota.fecha <= date(anio + 1, 1, 31))
    if alumno_id:
        q = q.filter(PagoCuota.alumno_id == alumno_id)
    por_alumno: dict[int, list] = {}
    for p in q.all():
        if anio_de_pago(p) == anio:
            por_alumno.setdefault(p.alumno_id, []).append(p)
    return por_alumno


def _mes_cobro(p, anio: int) -> int:
    """Mes en que entró el pago (fecha de proceso). Lo pagado en diciembre y procesado en enero del año
    siguiente queda en diciembre del año al que pertenece."""
    f = fecha_cobro(p)
    return 12 if f.year > anio else f.month


def _corte_texto(mes_corte: int | None) -> int:
    """Último mes con la cuota ya vencida (las cuotas vencen el último día de cada mes)."""
    return mes_corte if mes_corte else max(0, ahora_ar().month - 1)


def _calcular(db: Session, anio: int, mes_corte: int | None):
    cursos = cursos_vigentes(db, anio)
    pagos = pagos_del_anio(db, anio)
    extras = extras_por_alumno(db, anio)
    return [_estado_de(a, planes_de(a, cursos, extras.get(a.id, [])), pagos.get(a.id, []), anio, mes_corte)
            for a in db.query(Alumno).filter(Alumno.activo == True).all()]  # noqa: E712


@router.get("/estado")
def estado(anio: int | None = None, mes: int | None = None,
           area: str | None = None, curso: str | None = None,
           estado: str | None = None, q: str | None = None,
           db: Session = Depends(get_db)):
    """Estado de cuenta de todos los alumnos (para consulta y morosos)."""
    anio = anio or ahora_ar().year
    filas = _calcular(db, anio, mes)
    if area:
        filas = [f for f in filas if (f["area"] or "") == area]
    if curso:
        filas = [f for f in filas if (f["curso"] or "") == curso]
    if estado:
        filas = [f for f in filas if f["estado"] == estado]
    if q:
        t = q.strip().lower()
        filas = [f for f in filas if t in f"{f['apellido']} {f['nombre']} {f['legajo']}".lower()]
    filas.sort(key=lambda f: (-f["deuda_total"], f["apellido"]))
    return {"anio": anio, "mes_corte": _corte_texto(mes), "alumnos": filas}


def detalle_alumno(db: Session, a: Alumno, anio: int | None = None) -> dict:
    """Estado de cuenta completo de un alumno: cuotas, imputación de cada pago y próximo vencimiento."""
    anio = anio or ahora_ar().year
    planes = planes_alumno(db, a, anio)
    info = _estado_de(a, planes, pagos_del_anio(db, anio, a.id).get(a.id, []), anio, detalle=True)
    curso = planes[0]["curso"] if planes else None
    info["curso_param"] = {"nombre": curso.nombre, "cuota": float(curso.cuota), "n_cuotas": curso.n_cuotas,
                           "matricula": float(curso.matricula or 0)} if curso else None
    return info


@router.get("/estado/{alumno_id}")
def estado_alumno(alumno_id: int, anio: int | None = None, db: Session = Depends(get_db)):
    a = db.get(Alumno, alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    return detalle_alumno(db, a, anio)


@router.get("/libre-deuda/{alumno_id}")
def libre_deuda(alumno_id: int, anio: int | None = None, db: Session = Depends(get_db)):
    """Cursos de aeronavegantes y exámenes del alumno y si se puede extender el libre deuda de cada uno."""
    a = db.get(Alumno, alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    info = detalle_alumno(db, a, anio)
    return {"alumno_id": a.id, "apellido": a.apellido, "nombre": a.nombre, "dni": a.dni, "legajo": a.legajo,
            "anio": info["anio"], "cursos": libre_deuda_cursos(info)}


@router.get("/estadisticas")
def estadisticas(anio: int | None = None, mes: int | None = None, area: str | None = None, nivel: str | None = None,
                 db: Session = Depends(get_db)):
    """Comparativa de cursos (como la hoja COMPARATIVA CURSOS de la planilla), siempre A LA FECHA:
    lo esperado son las cuotas ya vencidas (al día de hoy, o al cierre del `mes` elegido), así el
    cumplimiento compara lo pagado con lo que ya se tenía que pagar. En diciembre equivale al anual."""
    anio = anio or ahora_ar().year
    if mes is not None and not 1 <= mes <= 12:
        raise HTTPException(400, "Mes inválido")
    hoy = ahora_ar().date()
    cursos_cfg = cursos_vigentes(db, anio)
    por_id_curso = {c.id: c for c in db.query(Curso).all()}
    pagos = pagos_del_anio(db, anio)
    extras = extras_por_alumno(db, anio)
    ORDEN_AREAS = ["Ciclo Basico", "Avionica", "Mecanica", "Aeronavegantes", "Examenes"]
    ESCUELA = {"Ciclo Basico", "Avionica", "Mecanica"}

    filas = []
    for a in db.query(Alumno).filter(Alumno.activo == True).all():  # noqa: E712
        planes = planes_de(a, cursos_cfg, extras.get(a.id, []))
        ps = pagos.get(a.id, [])
        if mes:  # la foto al cierre del mes elegido solo considera lo pagado hasta ese mes
            ps = [p for p in ps if _mes_cobro(p, anio) <= mes]
        info = estado_cuenta(a, planes, ps, anio, hoy=hoy, mes_corte=mes)
        # lo cobrado de cada curso sale del mismo reparto que el estado de cuenta del alumno (si cursa dos
        # cursos, cada pago va al suyo); lo del mes elegido = lo cobrado hasta el mes menos lo cobrado hasta el anterior
        previo = {}
        if mes:
            antes = estado_cuenta(a, planes, [p for p in ps if _mes_cobro(p, anio) < mes], anio, hoy=hoy, mes_corte=mes)
            previo = {x["clave"]: x.get("cobrado", 0.0) for x in antes["cursos"]}
        becado = info["estado"] in ("Becado", "Exento") or (a.condicion or "").lower() in ("becado", "exento")
        for i, c in enumerate(info["cursos"]):
            # Todo "a la fecha": lo esperado son las cuotas ya vencidas (al corte), no el total del año
            cobrado = c.get("cobrado", 0.0)
            cobrado_mes = cobrado - previo.get(c["clave"], 0.0) if mes else 0.0
            esperado = 0.0 if becado else c.get("esperado", 0.0)
            deuda_vencida = 0.0 if becado else c.get("deuda", 0.0)
            etq = c.get("etiqueta") or a.curso or "—"
            ar = c.get("area") or a.area or "Sin área"  # el área del curso (ORR A es de Aeronavegantes aunque el alumno figure en Exámenes)
            m = re.match(r"\s*(\d+)\s*°", etq)
            niv = f"{m.group(1)}°" if m else "—"
            estado = "Becado" if becado else c["estado"]
            if not becado and i == 0:
                estado = estado_con_anterior(estado, info.get("debe_anio_anterior"), anio)
            filas.append({"curso": etq, "area": ar, "nivel": niv,
                          "grupo": f"Todos los {niv} — {ar}" if ar in ESCUELA and niv != "—" else f"{etq} — {ar}",
                          "estado": estado, "cobrado": cobrado, "cobrado_mes": cobrado_mes, "esperado": esperado, "deuda_vencida": deuda_vencida,
                          "debe_anterior": bool(info.get("debe_anio_anterior")) and i == 0,
                          "deuda_anterior": info.get("deuda_anterior", 0.0) if i == 0 else 0.0})

    areas_disponibles = sorted({f["area"] for f in filas}, key=lambda x: (ORDEN_AREAS.index(x) if x in ORDEN_AREAS else 99, x))
    niveles_disponibles = sorted({f["nivel"] for f in filas if f["nivel"] != "—"})
    if area:
        filas = [f for f in filas if f["area"] == area]
    if nivel:
        filas = [f for f in filas if f["nivel"] == nivel or f["curso"] == nivel]

    def agrupar(clave_fn, orden_fn) -> list[dict]:
        g: dict = {}
        for f in filas:
            k = clave_fn(f)
            d = g.setdefault(k, {"clave": k[0] if isinstance(k, tuple) else k, "area": f["area"], "nivel": f["nivel"],
                                 "alumnos": 0, "becados": 0, "al_dia": 0, "pagado": 0, "al_dia_debe_anterior": 0,
                                 "moroso": 0, "sin_pagos": 0, "cobrado": 0.0, "cobrado_mes": 0.0, "esperado": 0.0, "deuda_vencida": 0.0,
                                 "con_deuda_anterior": 0, "deuda_anterior": 0.0})
            d["alumnos"] += 1
            e = f["estado"]
            clave_estado = {"Becado": "becados", "Exento": "becados", "Al día": "al_dia", "Pagado": "pagado",
                            "Moroso": "moroso", "Sin pagos": "sin_pagos"}.get(e, "al_dia_debe_anterior" if e.startswith("Al día ·") else None)
            if clave_estado:
                d[clave_estado] += 1
            d["cobrado"] += f["cobrado"]
            d["cobrado_mes"] += f["cobrado_mes"]
            d["esperado"] += f["esperado"]
            d["deuda_vencida"] += f["deuda_vencida"]
            if f["debe_anterior"]:
                d["con_deuda_anterior"] += 1
                d["deuda_anterior"] += f["deuda_anterior"]
        for d in g.values():
            # Deuda a la fecha = cuotas vencidas sin pagar; cumplimiento = parte de lo vencido que ya se pagó
            d["deuda"] = d["deuda_vencida"]
            d["cumplimiento"] = round((d["esperado"] - d["deuda"]) / d["esperado"] * 100, 1) if d["esperado"] else 100.0
        return sorted(g.values(), key=orden_fn)

    orden_area = lambda d: (ORDEN_AREAS.index(d["area"]) if d["area"] in ORDEN_AREAS else 99, d["clave"])
    por_curso = agrupar(lambda f: (f["curso"], f["area"]), orden_area)
    por_grupo = agrupar(lambda f: f["grupo"], orden_area)
    tot = agrupar(lambda f: "Total", lambda d: 0)
    total = tot[0] if tot else {"alumnos": 0, "cobrado": 0.0, "cobrado_mes": 0.0, "esperado": 0.0, "deuda": 0.0, "cumplimiento": 0.0,
                                "deuda_vencida": 0.0, "con_deuda_anterior": 0, "deuda_anterior": 0.0, "becados": 0,
                                "al_dia": 0, "pagado": 0, "al_dia_debe_anterior": 0, "moroso": 0, "sin_pagos": 0}

    # Cobranza por mes y área (fecha de proceso; el área es la del curso al que corresponde el pago)
    from app.routers.sectores import curso_de_pago
    alumnos = {x.id: x for x in db.query(Alumno).filter(Alumno.id.in_(list(pagos) or [0])).all()}
    matriz: dict = {m: {} for m in range(1, 13)}
    for aid, ps in pagos.items():
        a = alumnos.get(aid)
        planes = planes_de(a, cursos_cfg, extras.get(aid, [])) if a else []
        for p in ps:
            mes_p = _mes_cobro(p, anio)
            cid = p.curso_id if p.curso_id in por_id_curso else curso_de_pago(planes, p)
            ar = (por_id_curso[cid].area if cid in por_id_curso else None) or (a.area if a else None) or "Sin área"
            matriz[mes_p][ar] = matriz[mes_p].get(ar, 0.0) + float(p.importe)
    areas_m = sorted({ar for v in matriz.values() for ar in v}, key=lambda x: (ORDEN_AREAS.index(x) if x in ORDEN_AREAS else 99, x))
    mensual = [{"mes": m, "valores": {ar: matriz[m].get(ar, 0.0) for ar in areas_m}, "total": sum(matriz[m].values())} for m in range(1, 13)]
    tot_areas = {ar: sum(x["valores"][ar] for x in mensual) for ar in areas_m}

    return {
        "anio": anio, "mes": mes, "mes_corte": mes or _corte_texto(None),
        "filtros": {"areas": areas_disponibles, "niveles": niveles_disponibles},
        "indicadores": total,
        "por_curso": por_curso,
        "por_grupo": por_grupo,
        "mensual": {"areas": areas_m, "meses": mensual, "totales": tot_areas, "total": sum(tot_areas.values())},
    }


class Imputacion(BaseModel):
    curso_id: int | None = None


@router.post("/pagos/{pago_id}/imputar")
def imputar_pago(pago_id: int, data: Imputacion, db: Session = Depends(get_db)):
    """Imputa a mano un pago a uno de los cursos del alumno (o lo deja en automático con curso_id null)."""
    p = db.get(PagoCuota, pago_id)
    if not p or not p.alumno_id:
        raise HTTPException(404, "Pago no encontrado")
    if data.curso_id is not None and not db.query(AlumnoCurso).filter(
            AlumnoCurso.alumno_id == p.alumno_id, AlumnoCurso.curso_id == data.curso_id).first():
        raise HTTPException(400, "Ese curso no está asignado al alumno")
    p.curso_id = data.curso_id
    db.commit()
    return {"ok": True, "mensaje": "Imputación actualizada"}
