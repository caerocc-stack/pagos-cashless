"""
Lector del extracto de cuenta en PDF de Banco Roela (cuenta SIRO).

Cada movimiento puede ocupar hasta 3 líneas: un prefijo arriba de la fecha
(ej. "TRANSF.INTERB.DISTINTO TIT.-30708358130"), la línea con fecha/comprobante/
concepto/importe y un sufijo abajo (resto del nombre). Las líneas sueltas se
asignan a la línea con fecha más cercana en vertical, dentro de la misma página.

Control de integridad: saldo inicial + suma de movimientos debe dar el saldo
final que informa el propio extracto (si no cierra, se avisa).
"""
import io
import re
import hashlib
from datetime import date, datetime
from decimal import Decimal

RE_FECHA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})\b")
RE_LINEA = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(?:(\d{4,})\s+)?([A-Z0-9]{2,7})\b\s*(.*)$")
RE_IMPORTE = re.compile(r"(-?)\$\s?([\d.]+,\d{2})\s*$")
RE_IMPORTE_EN = re.compile(r"(-?)\$\s?([\d.]+,\d{2})")
RE_CUIT = re.compile(r"\b((?:20|23|24|27|30|33|34)\d{9})\b")
RE_PERIODO = re.compile(r"entre el (\d{1,2})/(\d{1,2})/(\d{4}) y el (\d{1,2})/(\d{1,2})/(\d{4})")
PREFIJOS = ("TRANSF", "CREDITO POR COBRO", "DEBITO DIRECTO", "BAK -", "DEBIN")
IGNORAR = ("Extracto de Cuenta", "entre el ", "Página", "P�gina", "Fecha Comprobante", "ASOC DE PADRES Y ALUM",
           "1° Titular", "1� Titular", "C.B.U.", "Nro.")

# Clasificación por código de concepto
# Solo estos egresos se concilian con facturas de proveedores
EGRESOS_CONCILIABLES = {
    "190100": "Transferencia a terceros",
    "F30100": "DEBIN (débito inmediato)",
    "146": "Débito directo",
}
# Egresos que NO son gastos a conciliar (no llevan factura): se informan aparte en el resumen
EGRESOS_NO_CONCILIABLES = {
    "256": "haberes",            # Pago de haberes (sueldos)
    "880100": "pago_automatico",  # Pago automático (sin CUIT)
}
COMISIONES_IMPUESTOS = {"148", "130", "127", "288", "169", "170", "178", "181", "193", "194", "214",
                        "222", "248", "249", "254"}
INGRESOS_SIRO = {"497", "501", "502", "510", "515", "530", "536", "560", "561", "564"}
INGRESO_QR = "580"


def _num(signo: str, txt: str) -> Decimal:
    v = Decimal(txt.replace(".", "").replace(",", "."))
    return -v if signo == "-" else v


def _fecha(txt: str) -> date:
    return datetime.strptime(txt, "%d/%m/%Y").date()


def categoria_de(concepto: str, importe: Decimal) -> str:
    if concepto in EGRESOS_CONCILIABLES:
        return "pago"
    if concepto in EGRESOS_NO_CONCILIABLES:
        return EGRESOS_NO_CONCILIABLES[concepto]
    if concepto in COMISIONES_IMPUESTOS:
        return "comision"
    if concepto in INGRESOS_SIRO:
        return "ingreso_siro"
    if concepto == INGRESO_QR:
        return "ingreso_qr"
    return "otro_ingreso" if importe >= 0 else "otro_egreso"


CUIT_PROPIO = "33690068619"  # APAI: aparece en débitos de AFIP, no es un proveedor


def extraer_cuit_y_nombre(desc: str):
    """CUIT del destinatario y el nombre que lo acompaña (el banco a veces lo corta)."""
    desc = desc or ""
    if desc.startswith("DEBITO DIRECTO-"):
        empresa = desc[len("DEBITO DIRECTO-"):].split("-")[0].strip() or None
        m = RE_CUIT.search(desc)
        return (m.group(1) if m and m.group(1) != CUIT_PROPIO else None), empresa
    m = RE_CUIT.search(desc)
    if m and m.group(1) == CUIT_PROPIO:
        m = None
    if not m:
        return None, None
    resto = desc[m.end():].strip(" -.,")
    if not resto:
        resto = desc[: m.start()]
        resto = re.sub(r"^(TRANSF\.INTERB\.[A-Z .]*TIT\.|TRANSF\.INTERB\.PAGO DE HABER|DEBIN- Debito Inmediato Distinto titular|DEBITO DIRECTO)\s*-?", "", resto).strip(" -.,")
    return m.group(1), (resto or None)


def leer_pdf(contenido: bytes) -> dict:
    """Devuelve {'periodo', 'saldo_inicial', 'saldo_final', 'movimientos': [...], 'cierra', 'diferencia'}."""
    import pdfplumber  # import diferido: solo se usa al importar extractos

    movimientos, saldo_inicial, saldo_final, periodo = [], None, None, None
    try:
        pdf = pdfplumber.open(io.BytesIO(contenido))
    except Exception:
        raise ValueError("No se pudo abrir el PDF. Verificá que sea el extracto descargado del banco.")
    with pdf:
        for page in pdf.pages:
            lineas = [l for l in page.extract_text_lines() if l["text"].strip()]
            if periodo is None:
                for l in lineas:
                    m = RE_PERIODO.search(l["text"])
                    if m:
                        d1, m1, a1, d2, m2, a2 = map(int, m.groups())
                        periodo = (date(a1, m1, d1), date(a2, m2, d2))
                        break
            filas, sueltas = [], []
            for l in lineas:
                t = l["text"].strip()
                centro = (l["top"] + l["bottom"]) / 2
                if t.startswith(IGNORAR) or t.startswith("Saldo al"):
                    if t.startswith("Saldo al"):
                        mi = RE_IMPORTE.search(t)
                        if mi:
                            saldo_final = _num(*mi.groups())
                    continue
                if "Saldo Al Inicio" in t:
                    mi = RE_IMPORTE.search(t)
                    if mi and saldo_inicial is None:
                        saldo_inicial = _num(*mi.groups())
                    continue
                m = RE_LINEA.match(t)
                if m:
                    filas.append({"centro": centro, "m": m, "pre": [], "post": []})
                else:
                    sueltas.append((centro, t))
            # Asignar cada línea suelta a la fila con fecha más cercana
            for centro, t in sueltas:
                if not filas:
                    continue
                cerca = min(filas, key=lambda f: abs(f["centro"] - centro))
                # Empate (equidistante entre dos filas): los prefijos conocidos van con la de abajo
                abajo = [f for f in filas if f["centro"] > centro]
                if abajo and t.startswith(PREFIJOS):
                    sig = min(abajo, key=lambda f: f["centro"] - centro)
                    if abs(abs(sig["centro"] - centro) - abs(cerca["centro"] - centro)) < 2:
                        cerca = sig
                (cerca["pre"] if centro < cerca["centro"] else cerca["post"]).append(t)
            for f in filas:
                fecha_txt, comp, conc, resto = f["m"].groups()
                texto = " ".join(f["pre"] + [resto] + f["post"])
                mi = RE_IMPORTE.search(resto) or RE_IMPORTE_EN.search(texto)
                if not mi:
                    continue
                importe = _num(*mi.groups())
                desc = RE_IMPORTE_EN.sub("", texto)
                desc = re.sub(r"\s+", " ", desc).strip()
                cuit, nombre = extraer_cuit_y_nombre(desc)
                movimientos.append({
                    "fecha": _fecha(fecha_txt), "comprobante": comp, "concepto": conc,
                    "descripcion": desc[:250], "importe": importe,
                    "categoria": categoria_de(conc, importe), "cuit": cuit, "razon_social": nombre,
                })

    if not movimientos:
        raise ValueError("No encontré movimientos en el PDF. ¿Es el extracto de cuenta de Banco Roela?")
    suma = sum((m["importe"] for m in movimientos), Decimal("0"))
    diferencia = None
    if saldo_inicial is not None and saldo_final is not None:
        diferencia = (saldo_inicial + suma) - saldo_final
    # Hash estable por movimiento: permite re-importar el mismo extracto sin duplicar
    vistos = {}
    for m in movimientos:
        base = f"{m['fecha']}|{m['comprobante']}|{m['concepto']}|{m['importe']}|{m['descripcion']}"
        vistos[base] = vistos.get(base, 0) + 1
        m["hash"] = hashlib.sha1(f"roela|{base}|{vistos[base]}".encode()).hexdigest()
    return {
        "periodo": periodo, "saldo_inicial": saldo_inicial, "saldo_final": saldo_final,
        "movimientos": movimientos, "cierra": diferencia == 0, "diferencia": diferencia,
    }


def resumen(datos: dict) -> dict:
    """Totales por categoría para el panel del extracto."""
    tot = {}
    for m in datos["movimientos"]:
        c = m["categoria"]
        t = tot.setdefault(c, {"cantidad": 0, "total": Decimal("0")})
        t["cantidad"] += 1
        t["total"] += m["importe"]
    return {k: {"cantidad": v["cantidad"], "total": float(v["total"])} for k, v in tot.items()}
