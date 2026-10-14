"""
Lectura flexible de listados de alumnos para el padrón.

Acepta el formato propio (legajo, dni, nombre, apellido, curso…) y también los listados que llegan
de otras áreas de la escuela, con otros encabezados y el nombre completo en una sola columna, p. ej.:

    Nro Cliente | Descripción               | Correo electrónica
    19147981    | García Parra  Luis Carlos | lucho767300@gmail.com

Se busca la fila de encabezados, se reconoce cada columna por su nombre (y el número de cliente por
su contenido: 7 a 9 dígitos es DNI, menos es legajo), se separa apellido y nombre y se normaliza todo
al formato del padrón: APELLIDO en mayúsculas, Nombre con mayúscula inicial, correo en minúsculas.
Si el listado no trae el curso, se usa el que se elige al importar.
"""
import csv
import io
import re
import unicodedata

import openpyxl

PARTICULAS = {"de", "del", "la", "las", "los", "di", "da", "dos", "van", "von", "mc", "san", "santa", "le"}

# Nombres de pila frecuentes; se suman los que ya figuran en el padrón.
NOMBRES_BASE = set("""
abigail adolfo adrian adriana agustin agustina aida ailen aimara alan alba alberto alejandra alejandro alexis alfredo
alicia alma alvaro amanda amelia ana andrea andres angel angela angeles angelina anibal antonella antonio ariana ariel
arturo augusto aurora axel barbara bautista beatriz benjamin bernardo bianca braian brenda brian brisa bruno camila
camilo candela carina carla carlos carmen carolina catalina cecilia celeste cesar cintia cipriano clara claudia
claudio constanza cristian cristina dahiana daiana damian daniel daniela dante dario david debora deborah delfina
diana diego dolores edgardo eduardo elena elias elian eliana elisa elizabeth ema emanuel emilia emiliano emilio
emma enrique enzo ernesto esteban estefania estela eugenia eugenio ezequiel facundo fabian fabiana fabricio fabrizio
federico felipe fernanda fernando florencia franco francisco gabriel gabriela gael galo gaston genaro gerardo
german gimena gisela gonzalo graciela guadalupe guillermo gustavo hector hernan horacio hugo ignacio ines irina iris
isabel isaac ismael ivan jazmin javier jeremias jesica jesus joaquin jonathan jorge jose josefina juan juana julia
julian juliana julieta karen karina kevin laura lautaro leandro leila leonardo leonel liliana lionel lisandro
lorena lorenzo lourdes lucas lucia luciana luciano lucio luis luisa luisana lujan maia maira malena manuel manuela
marcela marcelo marcos maria mariana mariano maricel marina mario marta martin martina mateo matias mauricio maximiliano
maximo melina melisa mia micaela miguel milagros mirta moises monica nadia nahuel natalia nazareno nelson nestor nicolas
noelia norberto norma octavio omar oscar pablo pamela paola patricia paula pedro pilar priscila rafael ramiro ramon
raul rebeca renata ricardo roberto rocio rodolfo rodrigo rolando romina ruben ruth sabrina salvador samuel sandra
santiago santino sara sebastian sergio silvana silvia sofia soledad sonia susana tamara tatiana teresa thiago tiago
tiziano tobias tomas ulises valentin valentina valeria vanesa veronica vicente victor victoria virginia walter ximena
yamila yanina yesica zoe
""".split())

ENCABEZADOS = {
    "legajo": ("legajo", "nro legajo", "n legajo", "legajo alumno"),
    "dni": ("dni", "documento", "nro documento", "n documento", "nro doc", "doc", "dni alumno", "numero de documento"),
    "cliente": ("nro cliente", "n cliente", "numero de cliente", "cliente", "codigo cliente", "cod cliente"),
    "apellido": ("apellido", "apellidos"),
    "nombre": ("nombre", "nombres"),
    "completo": ("apellido y nombre", "apellidos y nombres", "apellido nombre", "apellido, nombre", "descripcion",
                 "alumno", "nombre completo", "alumno/a", "estudiante"),
    "completo_nombre_primero": ("nombre y apellido", "nombres y apellidos", "nombre apellido"),
    "curso": ("curso", "curso/division", "curso y division", "division"),
    "area": ("area", "especialidad", "orientacion"),
    "email": ("email", "e-mail", "mail", "correo", "correo electronico", "correo electronica", "correo e", "e mail"),
    "telefono": ("telefono", "tel", "tel movil", "celular", "movil", "whatsapp"),
}


def sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _clave(s) -> str:
    s = sin_acentos(str(s or "")).lower().strip()
    s = re.sub(r"[°º.:#_]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tipo_columna(encabezado) -> str | None:
    k = _clave(encabezado)
    if not k:
        return None
    for tipo, nombres in ENCABEZADOS.items():
        if k in nombres:
            return tipo
    for tipo, nombres in ENCABEZADOS.items():  # coincidencia parcial ("Correo electrónico del alumno")
        if any(len(n) > 3 and k.startswith(n) for n in nombres):
            return tipo
    return None


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def solo_digitos(v) -> str:
    return re.sub(r"\D", "", texto(v))


def limpiar_emails(v) -> str | None:
    """Corrige errores de tipeo comunes (gmail,com · espacios · mayúsculas) y deja los correos separados por '; '."""
    t = texto(v).lower().replace("mailto:", "")
    t = re.sub(r"@([a-z0-9-]+),(com|ar|net|org)\b", r"@\1.\2", t)
    t = re.sub(r"\.con\b", ".com", t)
    if "@" not in t:
        t = re.sub(r"^([a-z0-9._%+-]+?)(gmail|hotmail|yahoo|outlook|live|icloud)\.com", r"\1@\2.com", t.strip())
    correos = [c.strip(" .,;") for c in re.split(r"[;\s/]+|,(?=\s*[a-z0-9._%+-]+@)", t) if "@" in c]
    validos = [c for c in correos if re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", c)]
    return "; ".join(dict.fromkeys(validos))[:150] or None


def _titulo(s: str) -> str:
    return " ".join(p[:1].upper() + p[1:].lower() for p in s.split(" ") if p)


def _es_nombre(tok: str, nombres: set[str]) -> bool:
    return sin_acentos(tok).lower() in nombres


def separar_nombre(completo: str, nombres: set[str], nombre_primero: bool = False) -> tuple[str, str]:
    """'García Parra  Luis Carlos' -> ('GARCÍA PARRA', 'Luis Carlos'). También 'APELLIDO, Nombre',
    'APELLIDO Nombre' (apellido en mayúsculas) y, con nombre_primero, 'Luis Carlos García'."""
    s = re.sub(r"\s+", " ", re.sub(r"\s+becad[oa]\s*$", "", completo.strip(), flags=re.I)).strip()
    if not s:
        return "", ""
    if "," in s:
        ape, nom = (x.strip() for x in s.split(",", 1))
        if nombre_primero:
            ape, nom = nom, ape
        return ape.upper(), _titulo(nom)
    t = s.split(" ")
    if len(t) == 1:
        return t[0].upper(), ""
    # Convención del padrón: el apellido en mayúsculas y el nombre no
    mayus = [p.isupper() and any(c.isalpha() for c in p) and len(p) > 1 for p in t]
    if any(mayus) and not all(mayus):
        if nombre_primero:
            i = mayus.index(True)
            return " ".join(t[i:]).upper(), _titulo(" ".join(t[:i]))
        i = mayus.index(False)
        if i > 0:
            return " ".join(t[:i]).upper(), _titulo(" ".join(t[i:]))
    if nombre_primero:
        # nombres de pila al principio; el resto, apellido (al menos una palabra)
        i = 0
        while i < len(t) - 1 and _es_nombre(t[i], nombres):
            i += 1
        i = max(i, 1)
        while i > 1 and t[i - 1].lower() in PARTICULAS:
            i -= 1
        return " ".join(t[i:]).upper(), _titulo(" ".join(t[:i]))
    # Apellido primero: los nombres de pila son las últimas palabras conocidas como nombre
    i = len(t)
    while i > 1 and _es_nombre(t[i - 1], nombres):
        i -= 1
    if i == len(t):  # la última palabra no es un nombre conocido: el primer nombre conocido marca el corte
        i = next((k for k in range(1, len(t)) if _es_nombre(t[k], nombres)), 1)
    while i < len(t) - 1 and t[i - 1].lower() in PARTICULAS:  # "DE LA FUENTE Ana": la partícula va con el apellido
        i += 1
    return " ".join(t[:i]).upper(), _titulo(" ".join(t[i:]))


def _leer_filas(contenido: bytes, nombre_archivo: str) -> list[list]:
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith(".csv"):
        txt = contenido.decode("utf-8-sig", errors="replace")
        dialecto = csv.Sniffer().sniff(txt[:4000], delimiters=",;\t") if txt.strip() else csv.excel
        return [list(r) for r in csv.reader(io.StringIO(txt), dialecto)]
    if nombre.endswith(".xls"):
        import xlrd
        hoja = xlrd.open_workbook(file_contents=contenido).sheet_by_index(0)
        return [hoja.row_values(i) for i in range(hoja.nrows)]
    wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    hojas = [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets[:20]]
    # con varias hojas, la que tiene el listado de alumnos (más columnas reconocidas; si empatan, más filas)
    return max(hojas, key=lambda h: (_puntaje(h), len(h)))


def _puntaje(filas: list[list]) -> int:
    _, col = _buscar_encabezados(filas)
    tiene_id = bool({"dni", "cliente", "legajo"} & set(col))
    tiene_nombre = bool({"apellido", "nombre", "completo", "completo_nombre_primero"} & set(col))
    return len(col) + (10 if tiene_id and tiene_nombre else 0)


def _buscar_encabezados(filas: list[list]) -> tuple[int, dict[str, int]]:
    """La fila (de las primeras 15) con más columnas reconocidas."""
    mejor, mapa_mejor = -1, {}
    for i, fila in enumerate(filas[:15]):
        mapa = {}
        for j, v in enumerate(fila):
            tipo = _tipo_columna(v)
            if tipo and tipo not in mapa:
                mapa[tipo] = j
        if len(mapa) > len(mapa_mejor):
            mejor, mapa_mejor = i, mapa
    return mejor, mapa_mejor


def leer_padron(contenido: bytes, nombre_archivo: str, curso: str | None = None,
                nombres_conocidos: set[str] | None = None) -> dict:
    """Devuelve las filas ya en el formato del padrón (legajo, dni, apellido, nombre, curso, area, email,
    telefono) y qué columnas se reconocieron."""
    try:
        filas = _leer_filas(contenido, nombre_archivo)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo ({e.__class__.__name__}). Subí un Excel (.xlsx o .xls) o un CSV.")
    nombres = NOMBRES_BASE | (nombres_conocidos or set())
    cab, col = _buscar_encabezados(filas)
    if cab < 0 or not ({"dni", "cliente"} & set(col)) or not ({"apellido", "nombre", "completo", "completo_nombre_primero"} & set(col)):
        raise ValueError("No encontré las columnas del listado: hace falta al menos el DNI (o número de cliente) "
                         "y el nombre del alumno.")

    def val(f, tipo):
        j = col.get(tipo)
        return f[j] if j is not None and j < len(f) else None

    # "Nro Cliente": 7 a 9 dígitos es DNI; menos, legajo
    cliente_es_dni = False
    if "cliente" in col:
        largos = [len(solo_digitos(val(f, "cliente"))) for f in filas[cab + 1:] if solo_digitos(val(f, "cliente"))]
        cliente_es_dni = bool(largos) and sum(7 <= n <= 9 for n in largos) >= len(largos) / 2

    salida, errores = [], []
    for n, f in enumerate(filas[cab + 1:], start=cab + 2):
        if not any(texto(v) for v in f):
            continue
        if "completo" in col or "completo_nombre_primero" in col:
            nombre_primero = "completo" not in col
            ape, nom = separar_nombre(texto(val(f, "completo" if not nombre_primero else "completo_nombre_primero")), nombres, nombre_primero)
        else:
            ape, nom = texto(val(f, "apellido")).upper(), _titulo(texto(val(f, "nombre")))
        dni = solo_digitos(val(f, "dni"))
        legajo = texto(val(f, "legajo"))
        if "cliente" in col:
            c = solo_digitos(val(f, "cliente"))
            if cliente_es_dni and not dni:
                dni = c
            elif not cliente_es_dni and not legajo:
                legajo = c
        if not (ape or nom) and not dni:
            continue  # renglón de totales, notas, etc.
        if legajo and re.fullmatch(r"\d+\.0", legajo):
            legajo = legajo[:-2]
        fila = {
            "fila": n, "legajo": legajo, "dni": dni, "apellido": ape[:100], "nombre": nom[:100],
            "curso": texto(val(f, "curso")) or (curso or "").strip(), "area": texto(val(f, "area")),
            "email": limpiar_emails(val(f, "email")), "telefono": texto(val(f, "telefono"))[:40] or None,
        }
        falta = [k for k, v in (("DNI", dni), ("apellido", ape), ("nombre", nom)) if not v]
        if falta:
            errores.append(f"Fila {n}: falta {', '.join(falta)}")
            fila["error"] = "Falta " + ", ".join(falta)
        elif not 6 <= len(dni) <= 10:
            errores.append(f"Fila {n}: el DNI «{dni}» no parece válido")
            fila["error"] = "DNI inválido"
        salida.append(fila)
    reconocidas = {t: texto(filas[cab][j]) for t, j in col.items()}
    if "cliente" in reconocidas:
        reconocidas["dni" if cliente_es_dni else "legajo"] = reconocidas.pop("cliente")
    return {"filas": salida, "errores": errores, "columnas": reconocidas,
            "trae_curso": "curso" in col, "fila_encabezados": cab + 1}
