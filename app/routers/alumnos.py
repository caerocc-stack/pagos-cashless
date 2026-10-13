from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from decimal import Decimal
import openpyxl
import io

from app.database import get_db
from app.models.alumno import Alumno
from app.models.saldo import Saldo
from app.models.tarjeta import Tarjeta
from app.models.movimiento import Movimiento
from app.schemas.alumno import AlumnoCreate, AlumnoUpdate, AlumnoResponse, AlumnoConSaldo
from app.models.curso import Curso, AlumnoCurso
from app.models.pago_cuota import PagoCuota
from app.models.portal import CuponEnviado, Consulta
from app.routers.cursos import curso_de_alumno
from app.tz import ahora_ar
from pydantic import BaseModel

router = APIRouter(prefix="/api/alumnos", tags=["Alumnos"])


def derivar_area(curso: str) -> str | None:
    """Deduce el area a partir del nombre del curso."""
    c = (curso or "").lower()
    if "avionica" in c or "aviónica" in c:
        return "Avionica"
    if "mecanica" in c or "mecánica" in c:
        return "Mecanica"
    if "ciclo" in c or "basico" in c or "básico" in c:
        return "Ciclo Basico"
    return None


# ---------------------------------------------------------------- cursos del alumno (más de uno por año)

def _cursos_activos(db: Session, anio: int) -> list[Curso]:
    cursos = db.query(Curso).filter(Curso.anio == anio, Curso.activo.is_(True)).all()
    return cursos or db.query(Curso).filter(Curso.activo.is_(True)).all()


def agregar_curso(db: Session, alumno: Alumno, curso: Curso, anio: int, mes_inicio: int) -> AlumnoCurso | None:
    """Suma un curso al alumno. Si es el primero que se agrega a mano, primero deja registrado su curso
    del padrón como principal (así se siguen cobrando sus cuotas)."""
    filas = db.query(AlumnoCurso).filter(AlumnoCurso.alumno_id == alumno.id, AlumnoCurso.anio == anio).all()
    if not filas:
        actual = curso_de_alumno(alumno, _cursos_activos(db, anio))
        if actual:
            principal = AlumnoCurso(alumno_id=alumno.id, curso_id=actual.id, anio=anio, mes_inicio=3, principal=True)
            db.add(principal)
            filas.append(principal)
    if any(f.curso_id == curso.id for f in filas):
        return None
    nuevo = AlumnoCurso(alumno_id=alumno.id, curso_id=curso.id, anio=anio, mes_inicio=mes_inicio,
                        principal=not filas)
    db.add(nuevo)
    db.flush()
    return nuevo


class CursoAlumnoIn(BaseModel):
    curso_id: int
    mes_inicio: int = 3
    anio: int | None = None


@router.get("/{alumno_id}/cursos")
def cursos_del_alumno(alumno_id: int, anio: int | None = None, db: Session = Depends(get_db)):
    from app.routers.cuotas import planes_alumno
    a = db.get(Alumno, alumno_id)
    if not a:
        raise HTTPException(404, "Alumno no encontrado")
    anio = anio or ahora_ar().year
    return [{"id": p.get("alumno_curso_id"), "curso_id": p.get("curso_id"), "nombre": p["nombre"],
             "mes_inicio": p["mes_inicio"], "principal": p["principal"], "cuota": float(p["curso"].cuota),
             "n_cuotas": p["curso"].n_cuotas, "matricula": float(p["curso"].matricula or 0)}
            for p in planes_alumno(db, a, anio)]


@router.post("/{alumno_id}/cursos")
def sumar_curso(alumno_id: int, data: CursoAlumnoIn, db: Session = Depends(get_db)):
    a = db.get(Alumno, alumno_id)
    c = db.get(Curso, data.curso_id)
    if not a or not c:
        raise HTTPException(404, "Alumno o curso no encontrado")
    if not 1 <= data.mes_inicio <= 12:
        raise HTTPException(400, "Mes de inicio inválido")
    if not agregar_curso(db, a, c, data.anio or ahora_ar().year, data.mes_inicio):
        raise HTTPException(400, "El alumno ya tiene ese curso")
    db.commit()
    return {"ok": True, "mensaje": f"Curso {c.nombre} agregado"}


@router.delete("/{alumno_id}/cursos/{fila_id}")
def quitar_curso(alumno_id: int, fila_id: int, db: Session = Depends(get_db)):
    f = db.get(AlumnoCurso, fila_id)
    if not f or f.alumno_id != alumno_id:
        raise HTTPException(404, "Curso no encontrado")
    db.query(PagoCuota).filter(PagoCuota.alumno_id == alumno_id, PagoCuota.curso_id == f.curso_id).update({"curso_id": None})
    db.delete(f)
    db.flush()
    resto = db.query(AlumnoCurso).filter(AlumnoCurso.alumno_id == alumno_id, AlumnoCurso.anio == f.anio).all()
    if len(resto) == 1:  # vuelve a ser un alumno de un solo curso
        db.delete(resto[0])
    elif resto and not any(x.principal for x in resto):
        resto[0].principal = True
    db.commit()
    return {"ok": True, "mensaje": "Curso quitado"}


def _alumno_con_saldo(a: Alumno) -> dict:
    return {
        "id": a.id,
        "legajo": a.legajo,
        "dni": a.dni,
        "nombre": a.nombre,
        "apellido": a.apellido,
        "curso": a.curso,
        "area": a.area or derivar_area(a.curso),
        "division": a.division,
        "email": a.email,
        "telefono": a.telefono,
        "fecha_nacimiento": a.fecha_nacimiento,
        "condicion": a.condicion,
        "modalidad": a.modalidad,
        "deuda_anio_anterior": a.deuda_anio_anterior,
        "cuota_excluir": a.cuota_excluir,
        "cuota_personalizada": a.cuota_personalizada,
        "matricula_paga": bool(a.matricula_paga),
        "activo": a.activo,
        "created_at": a.created_at,
        "saldo": a.saldo.monto if a.saldo else Decimal("0.00"),
        "codigo_siro": a.codigo_siro,
    }


@router.get("/", response_model=list[AlumnoConSaldo])
def listar_alumnos(activo: bool | None = None, curso: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Alumno).options(joinedload(Alumno.saldo))
    if activo is not None:
        query = query.filter(Alumno.activo == activo)
    if curso:
        query = query.filter(Alumno.curso == curso)
    alumnos = query.order_by(Alumno.apellido, Alumno.nombre).all()
    return [_alumno_con_saldo(a) for a in alumnos]


@router.get("/{alumno_id}", response_model=AlumnoConSaldo)
def obtener_alumno(alumno_id: int, db: Session = Depends(get_db)):
    alumno = db.query(Alumno).options(joinedload(Alumno.saldo)).filter(Alumno.id == alumno_id).first()
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")
    return _alumno_con_saldo(alumno)


@router.post("/", response_model=AlumnoResponse, status_code=201)
def crear_alumno(data: AlumnoCreate, db: Session = Depends(get_db)):
    if db.query(Alumno).filter(Alumno.legajo == data.legajo).first():
        raise HTTPException(409, f"Ya existe un alumno con legajo {data.legajo}")
    if db.query(Alumno).filter(Alumno.dni == data.dni).first():
        raise HTTPException(409, f"Ya existe un alumno con DNI {data.dni}")

    alumno = Alumno(**data.model_dump())
    if not alumno.area:
        alumno.area = derivar_area(alumno.curso)
    db.add(alumno)
    db.flush()

    saldo = Saldo(alumno_id=alumno.id)
    db.add(saldo)
    db.commit()
    db.refresh(alumno)
    # Reasignar pagos de cuota que estaban sin dueño y ahora matchean con este alumno
    try:
        from app.routers.cuotas import reasignar_pendientes
        reasignar_pendientes(db)
    except Exception as e:
        print("Aviso reasignar cuotas:", e)
    return alumno


@router.put("/{alumno_id}", response_model=AlumnoResponse)
def actualizar_alumno(alumno_id: int, data: AlumnoUpdate, db: Session = Depends(get_db)):
    alumno = db.get(Alumno, alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(alumno, campo, valor)
    db.commit()
    db.refresh(alumno)
    return alumno


@router.delete("/eliminar-todos")
def eliminar_todos(db: Session = Depends(get_db)):
    """Elimina TODO el padron: alumnos, tarjetas, saldos y movimientos. Accion irreversible."""
    db.query(Movimiento).delete()
    db.query(Tarjeta).delete()
    db.query(Saldo).delete()
    cantidad = db.query(Alumno).delete()
    db.commit()
    return {"ok": True, "mensaje": f"Se eliminaron {cantidad} alumnos y todos sus datos asociados"}


@router.delete("/{alumno_id}")
def eliminar_alumno(alumno_id: int, db: Session = Depends(get_db)):
    """Elimina un alumno y todos sus datos asociados (tarjetas, saldo, movimientos)."""
    alumno = db.get(Alumno, alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")

    # Borrar movimientos, tarjetas, saldo, cursos y cupones; los pagos quedan "sin asignar"
    db.query(AlumnoCurso).filter(AlumnoCurso.alumno_id == alumno_id).delete()
    db.query(CuponEnviado).filter(CuponEnviado.alumno_id == alumno_id).delete()
    db.query(PagoCuota).filter(PagoCuota.alumno_id == alumno_id).update({"alumno_id": None, "via": None, "curso_id": None})
    db.query(Consulta).filter(Consulta.alumno_id == alumno_id).update({"alumno_id": None})
    db.query(Movimiento).filter(Movimiento.alumno_id == alumno_id).delete()
    db.query(Tarjeta).filter(Tarjeta.alumno_id == alumno_id).delete()
    db.query(Saldo).filter(Saldo.alumno_id == alumno_id).delete()
    db.delete(alumno)
    db.commit()

    return {"ok": True, "mensaje": f"Alumno {alumno.apellido}, {alumno.nombre} eliminado"}


@router.post("/importar")
def importar_excel(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Importa alumnos desde un archivo Excel.
    Columnas esperadas: legajo, dni, nombre, apellido, curso
    """
    contenido = archivo.file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    ws = wb.active

    encabezados = [str(cell.value).strip().lower() for cell in ws[1]]
    campos_requeridos = {"legajo", "dni", "nombre", "apellido", "curso"}
    faltantes = campos_requeridos - set(encabezados)
    if faltantes:
        raise HTTPException(400, f"Faltan columnas en el Excel: {', '.join(faltantes)}")

    col_map = {nombre: idx for idx, nombre in enumerate(encabezados)}
    # Columnas opcionales
    col_mail = col_map.get("mail", col_map.get("email"))
    col_area = col_map.get("area", col_map.get("área"))

    def _valor(fila, idx):
        if idx is None:
            return ""
        v = fila[idx]
        return "" if v is None else str(v).strip()

    # Cargar alumnos existentes (por legajo y por dni) para detectar duplicados y actualizar email
    existentes_por_legajo = {a.legajo: a for a in db.query(Alumno).all()}
    por_dni = {a.dni: a for a in existentes_por_legajo.values()}
    dnis_existentes = set(por_dni)
    anio = ahora_ar().year
    cursos_cfg = _cursos_activos(db, anio)
    cursos_sumados = 0

    def sumar_si_es_otro_curso(alumno, curso_txt, area_txt):
        """El mismo alumno aparece en otro curso (aeronavegantes, exámenes): se le suma ese curso."""
        nonlocal cursos_sumados
        if not alumno.id or (curso_txt or "").strip().upper() == (alumno.curso or "").strip().upper():
            return False
        otro = curso_de_alumno(Alumno(curso=curso_txt, area=area_txt), cursos_cfg)
        actual = curso_de_alumno(alumno, cursos_cfg)
        if not otro or (actual and otro.id == actual.id):
            return False
        if agregar_curso(db, alumno, otro, anio, max(3, ahora_ar().month)):
            cursos_sumados += 1
            return True
        return False

    creados = 0
    actualizados = 0
    errores = []
    nuevos_alumnos = []

    for fila_num, fila in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        try:
            legajo = _valor(fila, col_map["legajo"])
            dni = _valor(fila, col_map["dni"])
            nombre = _valor(fila, col_map["nombre"])
            apellido = _valor(fila, col_map["apellido"])
            curso = _valor(fila, col_map["curso"])
            email = _valor(fila, col_mail) or None
            area = _valor(fila, col_area) or derivar_area(curso)

            if not all([legajo, dni, nombre, apellido, curso]):
                errores.append(f"Fila {fila_num}: datos incompletos")
                continue

            # Si el alumno ya existe: actualizar email y area si el archivo los trae
            if legajo in existentes_por_legajo:
                ex = existentes_por_legajo[legajo]
                cambio = sumar_si_es_otro_curso(ex, curso, area)
                if email:
                    ex.email = email
                    cambio = True
                if area and not ex.area:
                    ex.area = area
                    cambio = True
                if cambio:
                    actualizados += 1
                continue
            if dni in dnis_existentes:
                ex = por_dni.get(dni)
                if ex is not None and sumar_si_es_otro_curso(ex, curso, area):
                    continue
                errores.append(f"Fila {fila_num}: DNI {dni} ya existe con otro legajo")
                continue

            nuevo = Alumno(
                legajo=legajo, dni=dni, nombre=nombre,
                apellido=apellido, curso=curso, email=email, area=area,
            )
            nuevos_alumnos.append(nuevo)
            existentes_por_legajo[legajo] = nuevo
            por_dni[dni] = nuevo
            dnis_existentes.add(dni)
            creados += 1
        except Exception as e:
            errores.append(f"Fila {fila_num}: {str(e)}")

    # Insertar nuevos de una vez
    if nuevos_alumnos:
        db.add_all(nuevos_alumnos)
        db.flush()
        saldos = [Saldo(alumno_id=a.id) for a in nuevos_alumnos]
        db.add_all(saldos)

    db.commit()

    return {
        "creados": creados,
        "actualizados": actualizados,
        "cursos_sumados": cursos_sumados,
        "errores": errores,
        "total_procesadas": fila_num - 1 if 'fila_num' in dir() else 0,
    }
