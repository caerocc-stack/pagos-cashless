"""Configuracion editable del sistema (clave/valor en la base)."""
from sqlalchemy.orm import Session
from app.models.configuracion import Configuracion
from app.tz import ahora_ar

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

DEFAULTS = {
    # --- Recarga de ApaiCard (monto libre) ---
    "recarga_asunto": "Cupón de recarga ApaiCard - {alumno}",
    "recarga_mensaje": (
        "Estimada familia de {alumno}:\n\n"
        "Adjuntamos el cupón para cargar saldo en la ApaiCard del alumno por un importe de {monto}.\n\n"
        "Una vez abonado, el saldo quedará disponible en la tarjeta del alumno para sus consumos.\n\n"
        "Curso: {curso} · Legajo: {legajo}\n\n"
        "¡Muchas gracias!\nAPAI - Asociación de Padres y Alumnos del I.N.A.C"
    ),
    # --- Cuota societaria mensual (monto fijo) ---
    "cuota_asunto": "Cuota APAI {mes} {anio} - {alumno}",
    "cuota_mensaje": (
        "Estimada familia de {alumno}:\n\n"
        "Adjuntamos el cupón de la cuota societaria de APAI correspondiente al mes de "
        "{mes} de {anio}, por un valor de {monto}.\n\n"
        "Agradecemos abonarla antes de su vencimiento.\n\n"
        "Alumno: {alumno} · Curso: {curso}\n\n"
        "¡Muchas gracias!\nAPAI - Asociación de Padres y Alumnos del I.N.A.C"
    ),
    "cuota_monto": "45000",
    # --- Datos fiscales de APAI (se muestran a los proveedores para que facturen) ---
    "apai_razon_social": "ASOCIACION DE PADRES Y ALUMNOS DEL INAC",
    "apai_cuit": "33-69006861-9",
    "apai_domicilio": "Av. Eva Perón 2200, Morón, Buenos Aires",
    "apai_condicion_iva": "IVA Sujeto Exento",
    # --- Módulos ---
    "tarjeta_activa": "0",   # la tarjeta APAI está suspendida temporalmente
}

CLAVES_SISTEMA = ["apai_razon_social", "apai_cuit", "apai_domicilio", "apai_condicion_iva", "tarjeta_activa"]

CLAVES_PLANTILLAS = [
    "recarga_asunto", "recarga_mensaje",
    "cuota_asunto", "cuota_mensaje", "cuota_monto",
]


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


def mes_actual() -> str:
    return MESES[ahora_ar().month - 1]


def aplicar_comodines(texto: str, alumno, monto_str: str) -> str:
    """Reemplaza los comodines del mensaje por los datos reales."""
    ahora = ahora_ar()
    return (
        texto
        .replace("{alumno}", f"{alumno.apellido}, {alumno.nombre}")
        .replace("{nombre}", alumno.nombre)
        .replace("{apellido}", alumno.apellido)
        .replace("{monto}", monto_str)
        .replace("{legajo}", str(alumno.legajo))
        .replace("{curso}", alumno.curso)
        .replace("{mes}", MESES[ahora.month - 1])
        .replace("{anio}", str(ahora.year))
    )


def tarjeta_activa(db: Session) -> bool:
    return get_config(db, "tarjeta_activa") == "1"


def datos_apai(db: Session) -> dict:
    return {"razon_social": get_config(db, "apai_razon_social"), "cuit": get_config(db, "apai_cuit"),
            "domicilio": get_config(db, "apai_domicilio"), "condicion_iva": get_config(db, "apai_condicion_iva")}
