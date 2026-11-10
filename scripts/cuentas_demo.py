"""
Cuentas de demostración para mostrar ALAS (sistema del personal, portal de familias y portal de alumnos)
sin que se pueda modificar ni descargar nada.

    DEMO_PASSWORD=... python scripts/cuentas_demo.py          -> crea o actualiza todo
    python scripts/cuentas_demo.py --borrar                   -> borra todo lo creado

Crea, todo con el correo ficticio de app/demo.py (DEMO_EMAIL) y la misma clave (DEMO_PASSWORD):
- Usuario del personal "demo", rol Demostración: ve el sistema como la administración, sin guardar ni descargar.
- Alumna ficticia Lucía DEMO (2°B, legajo 99905, DNI 12121212): pagó de marzo a septiembre, debe octubre.
- Su cuenta del portal de familias (ingreso con el correo) y la del portal de alumnos (ingreso con el DNI).
- Una consulta respondida y dos envíos a imprimir ya resueltos, para que los portales no se vean vacíos.

La clave no se guarda en el repositorio: se pasa por la variable de entorno DEMO_PASSWORD.
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
from app.auth import hash_password  # noqa: E402
from app.demo import DEMO_EMAIL  # noqa: E402
from app.seguridad import error_password  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.models.alumno import Alumno  # noqa: E402
from app.models.pago_cuota import PagoCuota  # noqa: E402
from app.models.portal import CuentaPadre, Consulta, MensajeConsulta  # noqa: E402
from app.models.impresion import CuentaAlumno, PedidoImpresion  # noqa: E402

USUARIO = "demo"
ALUMNA = {"legajo": "99905", "dni": "12121212", "nombre": "Lucía", "apellido": "DEMO", "curso": "2°B", "division": "B",
          "area": "Ciclo Basico", "fecha_nacimiento": date(2012, 4, 17)}
# (fecha de proceso, importe, canal): matrícula + marzo juntos, después una cuota por mes hasta septiembre
PAGOS = [(date(2026, 3, 9), 95000, "PF"), (date(2026, 4, 8), 45000, "LK"), (date(2026, 5, 11), 45000, "TQR"),
         (date(2026, 6, 9), 45000, "LK"), (date(2026, 7, 10), 45000, "PF"), (date(2026, 8, 10), 45000, "TQR"),
         (date(2026, 9, 9), 45000, "LK")]
HASH = "DEMO-ALAS-99905-"


def borrar(db):
    a = db.query(Alumno).filter(Alumno.legajo == ALUMNA["legajo"]).first()
    if a:
        db.query(PagoCuota).filter(PagoCuota.alumno_id == a.id).delete(synchronize_session=False)
        db.query(PedidoImpresion).filter(PedidoImpresion.alumno_id == a.id).delete(synchronize_session=False)
        db.query(CuentaAlumno).filter(CuentaAlumno.alumno_id == a.id).delete(synchronize_session=False)
    cuenta = db.query(CuentaPadre).filter(CuentaPadre.email == DEMO_EMAIL).first()
    filtro = Consulta.alumno_id == (a.id if a else -1)
    if cuenta:
        filtro = filtro | (Consulta.cuenta_id == cuenta.id)
    for x in db.query(Consulta).filter(filtro).all():
        db.delete(x)  # borra también sus mensajes
    db.flush()
    if a:
        db.delete(a)
    if cuenta:
        db.delete(cuenta)
    db.query(Usuario).filter(Usuario.username == USUARIO).delete(synchronize_session=False)
    db.commit()
    print("Borradas las cuentas de demostración y la alumna ficticia.")


def crear(db, clave: str):
    clave_hash = hash_password(clave)

    u = db.query(Usuario).filter(Usuario.username == USUARIO).first() or Usuario(username=USUARIO)
    u.email, u.nombre, u.rol, u.activo = DEMO_EMAIL, "Demostración", "demo", True
    u.password_hash, u.debe_cambiar_password = clave_hash, False
    u.intentos_fallidos, u.bloqueado_hasta = 0, None
    u.totp_activo, u.totp_secreto, u.codigos_respaldo = False, None, None
    u.version_sesion = (u.version_sesion or 0) + 1
    db.add(u)

    a = db.query(Alumno).filter(Alumno.legajo == ALUMNA["legajo"]).first()
    if not a:
        a = Alumno(legajo=ALUMNA["legajo"], dni=ALUMNA["dni"])
        db.add(a)
    for k, v in ALUMNA.items():
        setattr(a, k, v)
    a.email, a.telefono = DEMO_EMAIL, "11 5555-0000"
    a.condicion, a.modalidad, a.activo = "Regular", "Mensual", True
    db.flush()

    db.query(PagoCuota).filter(PagoCuota.alumno_id == a.id).delete(synchronize_session=False)
    for fecha, importe, canal in PAGOS:
        db.add(PagoCuota(alumno_id=a.id, cliente_siro=a.codigo_siro, via="legajo", importe=Decimal(importe),
                         fecha=fecha, fecha_pago=fecha - timedelta(days=1), canal=canal, mes=fecha.month, anio=fecha.year,
                         origen="Datos de demostración", hash=f"{HASH}{fecha:%m%d}"))

    padre = db.query(CuentaPadre).filter(CuentaPadre.email == DEMO_EMAIL).first() or CuentaPadre(email=DEMO_EMAIL)
    padre.password_hash, padre.debe_cambiar_password, padre.activo = clave_hash, False, True
    padre.intentos_fallidos, padre.bloqueado_hasta = 0, None
    padre.version_sesion = (padre.version_sesion or 0) + 1
    db.add(padre)

    cal = db.query(CuentaAlumno).filter(CuentaAlumno.alumno_id == a.id).first() or CuentaAlumno(alumno_id=a.id)
    cal.password_hash, cal.debe_cambiar_password = clave_hash, False
    cal.intentos_fallidos, cal.bloqueado_hasta = 0, None
    cal.version_sesion = (cal.version_sesion or 0) + 1
    db.add(cal)
    db.flush()

    # Una consulta ya respondida (no aparece como pendiente para la oficina)
    for x in db.query(Consulta).filter((Consulta.cuenta_id == padre.id) | (Consulta.alumno_id == a.id)).all():
        db.delete(x)
    db.flush()
    enviada = datetime(2026, 10, 14, 19, 32)
    q = Consulta(origen="portal", cuenta_id=padre.id, alumno_id=a.id, categoria="pago_no_registrado",
                 asunto="Pago de septiembre", estado="respondida", leida_admin=True, leida_autor=True,
                 created_at=enviada, actualizada=enviada + timedelta(hours=16))
    q.mensajes = [
        MensajeConsulta(autor="padre", autor_nombre=DEMO_EMAIL, created_at=enviada,
                        texto="Hola, pagué la cuota de septiembre el 8/9 por Link y quería confirmar que esté registrada."),
        MensajeConsulta(autor="admin", autor_nombre="Asociación de Padres", created_at=enviada + timedelta(hours=16),
                        texto="Hola, sí: el pago de septiembre está registrado el 09/09. Lucía tiene pendiente solo la cuota de octubre."),
    ]
    db.add(q)

    # Dos envíos a imprimir ya resueltos (sin archivo: no quedan en la cola de la oficina)
    db.query(PedidoImpresion).filter(PedidoImpresion.alumno_id == a.id).delete(synchronize_session=False)
    for nombre, hoja, estado, cuando, motivo in [
        ("A4 - TP Física.pdf", "A4", "impreso", datetime(2026, 11, 4, 10, 5), None),
        ("A3 - Lámina de dibujo técnico.pdf", "A3", "descartado", datetime(2026, 11, 6, 9, 40),
         "Lo retiraste impreso en otra fotocopiadora."),
    ]:
        db.add(PedidoImpresion(alumno_id=a.id, archivo_nombre=nombre, archivo_ruta=f"demo/{a.legajo}/{hoja}.pdf",
                               tamanio=850_000, copias=1, hoja=hoja, estado=estado, motivo=motivo,
                               created_at=cuando - timedelta(hours=2), resuelto_at=cuando,
                               resuelto_por="Personal de APAI", archivo_borrado=True))
    db.commit()
    print(f"Listo. Correo de las cuentas: {DEMO_EMAIL} · usuario del personal: {USUARIO} · "
          f"DNI de la alumna: {ALUMNA['dni']} · {len(PAGOS)} pagos (debe octubre).")


if __name__ == "__main__":
    sesion = SessionLocal()
    try:
        if "--borrar" in sys.argv:
            borrar(sesion)
        else:
            clave = os.getenv("DEMO_PASSWORD") or ""
            if (motivo := error_password(clave)):
                sys.exit(f"DEMO_PASSWORD no sirve: {motivo}")
            crear(sesion, clave)
    finally:
        sesion.close()
