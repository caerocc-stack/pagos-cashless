"""
Carga (o borra) una familia de prueba para ver el Portal de familias con datos ficticios.

    python scripts/familia_prueba.py correo@ejemplo.com          -> crea/actualiza
    python scripts/familia_prueba.py correo@ejemplo.com --borrar -> elimina todo lo creado

Crea 2 hermanos (apellido PRUEBA) con el correo indicado: Sofía (2°A, al día) y Tomás (5°B Mecánica,
debe agosto a octubre), con pagos de cuota desde marzo y movimientos de la tarjeta.
La primera clave del portal es el DNI de cualquiera de los dos (12345678 o 12345679).
Todo queda marcado: pagos con hash "DEMO-PRUEBA-..." y alumnos con legajo 99901 / 99902.
"""
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
load_dotenv(os.path.join(RAIZ, ".env"))

from app.database import SessionLocal  # noqa: E402
import app.esquema  # noqa: E402,F401  (registra todos los modelos y sus relaciones)
from app.models.alumno import Alumno  # noqa: E402
from app.models.pago_cuota import PagoCuota  # noqa: E402
from app.models.movimiento import Movimiento  # noqa: E402
from app.models.saldo import Saldo  # noqa: E402
from app.models.portal import CuentaPadre, CuponEnviado, Consulta, MensajeConsulta  # noqa: E402

HIJOS = [
    {"legajo": "99901", "dni": "12345678", "nombre": "Sofía", "apellido": "PRUEBA", "curso": "2°A", "division": "A",
     "area": "Ciclo Basico", "fecha_nacimiento": date(2012, 5, 14),
     # (fecha de proceso, importe, canal): matrícula + marzo juntos, después una cuota por mes -> al día
     "pagos": [(date(2026, 3, 9), 95000, "LK"), (date(2026, 4, 8), 45000, "PF"), (date(2026, 5, 11), 45000, "LK"),
               (date(2026, 6, 9), 45000, "TQR"), (date(2026, 7, 10), 45000, "LK"), (date(2026, 8, 10), 45000, "PF"),
               (date(2026, 9, 9), 45000, "LK"), (date(2026, 10, 8), 45000, "TQR")],
     "tarjeta": [(datetime(2026, 3, 16, 9, 12), "recarga", 10000, "Recarga en efectivo"),
                 (datetime(2026, 3, 18, 10, 40), "consumo", -1200, "Fotocopias apuntes Matemática"),
                 (datetime(2026, 4, 7, 12, 5), "consumo", -2500, "Buffet"),
                 (datetime(2026, 5, 20, 8, 55), "consumo", -900, "Fotocopias Lengua"),
                 (datetime(2026, 6, 3, 13, 20), "recarga", 5000, "Recarga con cupón"),
                 (datetime(2026, 6, 24, 11, 30), "consumo", -3000, "Buffet"),
                 (datetime(2026, 8, 12, 9, 45), "consumo", -1500, "Fotocopias Física"),
                 (datetime(2026, 9, 2, 10, 10), "transferencia_in", 2000, "Transferencia de PRUEBA, Tomás"),
                 (datetime(2026, 10, 6, 12, 40), "consumo", -2100, "Buffet")]},
    {"legajo": "99902", "dni": "12345679", "nombre": "Tomás", "apellido": "PRUEBA", "curso": "5°B Mecanica", "division": "B",
     "area": "Mecanica", "fecha_nacimiento": date(2009, 9, 2),
     # pagó hasta julio: debe agosto, septiembre y octubre
     "pagos": [(date(2026, 3, 12), 95000, "RP"), (date(2026, 4, 13), 45000, "PF"), (date(2026, 5, 12), 45000, "PF"),
               (date(2026, 6, 15), 45000, "LK"), (date(2026, 7, 13), 45000, "TQR")],
     "tarjeta": [(datetime(2026, 3, 20, 8, 30), "recarga", 6000, "Recarga en efectivo"),
                 (datetime(2026, 4, 15, 10, 15), "consumo", -1800, "Fotocopias taller"),
                 (datetime(2026, 7, 1, 12, 50), "consumo", -1550, "Buffet"),
                 (datetime(2026, 9, 2, 10, 10), "transferencia_out", -2000, "Transferencia a PRUEBA, Sofía")]},
]


def borrar(db, email):
    alumnos = db.query(Alumno).filter(Alumno.legajo.in_([h["legajo"] for h in HIJOS])).all()
    ids = [a.id for a in alumnos]
    if ids:
        db.query(PagoCuota).filter(PagoCuota.alumno_id.in_(ids)).delete(synchronize_session=False)
        db.query(Movimiento).filter(Movimiento.alumno_id.in_(ids)).delete(synchronize_session=False)
        db.query(Saldo).filter(Saldo.alumno_id.in_(ids)).delete(synchronize_session=False)
        db.query(CuponEnviado).filter(CuponEnviado.alumno_id.in_(ids)).delete(synchronize_session=False)
    cuenta = db.query(CuentaPadre).filter(CuentaPadre.email == email).first()
    consultas = db.query(Consulta).filter((Consulta.alumno_id.in_(ids)) | (Consulta.cuenta_id == (cuenta.id if cuenta else -1))).all()
    for x in consultas:
        db.query(MensajeConsulta).filter(MensajeConsulta.consulta_id == x.id).delete(synchronize_session=False)
        db.delete(x)
    db.flush()
    for a in alumnos:
        db.delete(a)
    if cuenta:
        db.delete(cuenta)
    db.commit()
    print(f"Borrados: {len(alumnos)} alumnos, {len(consultas)} consultas, cuenta del portal: {'sí' if cuenta else 'no había'}")


def crear(db, email):
    for h in HIJOS:
        a = db.query(Alumno).filter(Alumno.legajo == h["legajo"]).first()
        if not a:
            a = Alumno(legajo=h["legajo"], dni=h["dni"])
            db.add(a)
        a.nombre, a.apellido, a.curso, a.division, a.area = h["nombre"], h["apellido"], h["curso"], h["division"], h["area"]
        a.email, a.telefono, a.fecha_nacimiento = email, "11 5555-0000", h["fecha_nacimiento"]
        a.condicion, a.modalidad, a.activo = "Regular", "Mensual", True
        db.flush()
        # Pagos y movimientos se regeneran desde cero
        db.query(PagoCuota).filter(PagoCuota.alumno_id == a.id).delete(synchronize_session=False)
        db.query(Movimiento).filter(Movimiento.alumno_id == a.id).delete(synchronize_session=False)
        for fecha, importe, canal in h["pagos"]:
            db.add(PagoCuota(alumno_id=a.id, cliente_siro=a.codigo_siro, via="legajo", importe=Decimal(importe),
                             fecha=fecha, fecha_pago=fecha - timedelta(days=1), canal=canal, mes=fecha.month, anio=fecha.year,
                             origen="Datos de prueba (portal)", hash=f"DEMO-PRUEBA-{h['legajo']}-{fecha:%m%d}"))
        saldo = Decimal("0")
        for cuando, tipo, monto, desc in h["tarjeta"]:
            saldo += Decimal(monto)
            db.add(Movimiento(alumno_id=a.id, tipo=tipo, monto=Decimal(monto), descripcion=desc, operador="Datos de prueba",
                              created_at=cuando))
        s = db.get(Saldo, a.id)
        if not s:
            s = Saldo(alumno_id=a.id)
            db.add(s)
        s.monto = saldo
        print(f"{a.apellido}, {a.nombre} ({a.curso}) · legajo {a.legajo} · {len(h['pagos'])} pagos "
              f"${sum(p[1] for p in h['pagos']):,} · saldo tarjeta ${saldo:,}")
    db.commit()


if __name__ == "__main__":
    if len(sys.argv) < 2 or "@" not in sys.argv[1]:
        sys.exit(__doc__)
    correo = sys.argv[1].strip().lower()
    sesion = SessionLocal()
    try:
        borrar(sesion, correo) if "--borrar" in sys.argv else crear(sesion, correo)
    finally:
        sesion.close()
