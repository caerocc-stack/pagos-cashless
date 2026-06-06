from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from decimal import Decimal
import openpyxl
import io

from app.database import get_db
from app.models.alumno import Alumno
from app.models.saldo import Saldo
from app.models.tarjeta import Tarjeta
from app.models.movimiento import Movimiento
from app.schemas.alumno import AlumnoCreate, AlumnoUpdate, AlumnoResponse, AlumnoConSaldo

router = APIRouter(prefix="/api/alumnos", tags=["Alumnos"])


def _alumno_con_saldo(a: Alumno) -> dict:
    return {
        "id": a.id,
        "legajo": a.legajo,
        "dni": a.dni,
        "nombre": a.nombre,
        "apellido": a.apellido,
        "curso": a.curso,
        "activo": a.activo,
        "created_at": a.created_at,
        "saldo": a.saldo.monto if a.saldo else Decimal("0.00"),
    }


@router.get("/", response_model=list[AlumnoConSaldo])
def listar_alumnos(activo: bool | None = None, curso: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Alumno)
    if activo is not None:
        query = query.filter(Alumno.activo == activo)
    if curso:
        query = query.filter(Alumno.curso == curso)
    alumnos = query.order_by(Alumno.apellido, Alumno.nombre).all()
    return [_alumno_con_saldo(a) for a in alumnos]


@router.get("/{alumno_id}", response_model=AlumnoConSaldo)
def obtener_alumno(alumno_id: int, db: Session = Depends(get_db)):
    alumno = db.get(Alumno, alumno_id)
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
    db.add(alumno)
    db.flush()

    saldo = Saldo(alumno_id=alumno.id)
    db.add(saldo)
    db.commit()
    db.refresh(alumno)
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


@router.delete("/{alumno_id}")
def eliminar_alumno(alumno_id: int, db: Session = Depends(get_db)):
    """Elimina un alumno y todos sus datos asociados (tarjetas, saldo, movimientos)."""
    alumno = db.get(Alumno, alumno_id)
    if not alumno:
        raise HTTPException(404, "Alumno no encontrado")

    # Borrar movimientos, tarjetas y saldo del alumno
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

    # Cargar todos los legajos y DNIs existentes de una sola vez (rapido)
    legajos_existentes = set(r[0] for r in db.query(Alumno.legajo).all())
    dnis_existentes = set(r[0] for r in db.query(Alumno.dni).all())

    creados = 0
    errores = []
    nuevos_alumnos = []

    for fila_num, fila in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        try:
            legajo = str(fila[col_map["legajo"]]).strip()
            dni = str(fila[col_map["dni"]]).strip()
            nombre = str(fila[col_map["nombre"]]).strip()
            apellido = str(fila[col_map["apellido"]]).strip()
            curso = str(fila[col_map["curso"]]).strip()

            if not all([legajo, dni, nombre, apellido, curso]):
                errores.append(f"Fila {fila_num}: datos incompletos")
                continue

            if legajo in legajos_existentes:
                errores.append(f"Fila {fila_num}: legajo {legajo} ya existe")
                continue
            if dni in dnis_existentes:
                errores.append(f"Fila {fila_num}: DNI {dni} ya existe")
                continue

            nuevos_alumnos.append(Alumno(
                legajo=legajo, dni=dni, nombre=nombre,
                apellido=apellido, curso=curso,
            ))
            legajos_existentes.add(legajo)
            dnis_existentes.add(dni)
            creados += 1
        except Exception as e:
            errores.append(f"Fila {fila_num}: {str(e)}")

    # Insertar todos de una vez
    if nuevos_alumnos:
        db.add_all(nuevos_alumnos)
        db.flush()
        # Crear saldos en bloque
        saldos = [Saldo(alumno_id=a.id) for a in nuevos_alumnos]
        db.add_all(saldos)
        db.commit()

    return {
        "creados": creados,
        "errores": errores,
        "total_procesadas": fila_num - 1 if 'fila_num' in dir() else 0,
    }
