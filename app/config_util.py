"""Configuracion editable del sistema (clave/valor en la base)."""
from sqlalchemy.orm import Session
from app.models.configuracion import Configuracion

DEFAULTS = {
    "cupon_asunto": "Cupón de recarga - APAI Pay - {alumno}",
    "cupon_mensaje": (
        "Estimada familia de {alumno}:\n\n"
        "Generamos un cupón para recargar saldo en la tarjeta del alumno por el importe de {monto}.\n\n"
        "Pueden abonarlo desde el botón de más abajo. Una vez acreditado el pago, el saldo "
        "quedará disponible en la tarjeta del alumno.\n\n"
        "Curso: {curso} · Legajo: {legajo}\n\n"
        "¡Muchas gracias!\nAPAI - Asociación de Padres y Alumnos del I.N.A.C"
    ),
}


def get_config(db: Session, clave: str) -> str:
    row = db.get(Configuracion, clave)
    if row and row.valor is not None:
        return row.valor
    return DEFAULTS.get(clave, "")


def set_config(db: Session, clave: str, valor: str):
    row = db.get(Configuracion, clave)
    if row:
        row.valor = valor
    else:
        db.add(Configuracion(clave=clave, valor=valor))
    db.commit()


def aplicar_comodines(texto: str, alumno, monto_str: str) -> str:
    """Reemplaza los comodines del mensaje por los datos reales."""
    return (
        texto
        .replace("{alumno}", f"{alumno.apellido}, {alumno.nombre}")
        .replace("{nombre}", alumno.nombre)
        .replace("{apellido}", alumno.apellido)
        .replace("{monto}", monto_str)
        .replace("{legajo}", str(alumno.legajo))
        .replace("{curso}", alumno.curso)
    )
