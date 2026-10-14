"""
Datos de una factura a partir del texto que saca el OCR de una página escaneada (más el QR de AFIP,
si se pudo leer). El OCR comete errores típicos (6↔0, 7↔2, espacios dentro de los números, años
como 7026); acá se corrigen con validaciones: dígito verificador del CUIT, proveedores ya cargados,
fechas posibles y el TOTAL del comprobante.

Devuelve, por campo, el valor y de dónde salió ("qr", "ocr", "ocr corregido") para que la pantalla
de revisión marque lo dudoso.
"""
import re
from datetime import date
from decimal import Decimal

from app.factura_pdf import TIPOS_AFIP, _importe, cuit_valido, digitos, leer_qr_afip

PREFIJOS = ("20", "23", "24", "27", "30", "33", "34")
# confusiones habituales del OCR entre dígitos (y letras que se leen como dígitos)
PARECIDOS = {"0": "698", "6": "085", "8": "036", "3": "8", "5": "6", "7": "21", "2": "7", "1": "7", "9": "08", "4": "9"}
LETRAS = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8", "Z": "2", "G": "6"})


def _numeros(texto: str) -> str:
    """Corrige letras leídas en lugar de dígitos (O→0, S→5…) solo dentro de los números, sin tocar las palabras."""
    def fix(m):
        g = m.group()
        if sum(c.isdigit() for c in g) < 2:
            return g
        # la letra de la factura pegada al número (B00035-…) no se toca; solo las letras entre dígitos
        inicio = re.match(r"[A-Za-z|]*", g).group()
        return inicio + g[len(inicio):].translate(LETRAS)
    return re.sub(r"[0-9OoDQIl|SBZG]+", fix, texto)


def codigo_barras(texto: str) -> dict:
    """Código de barras de AFIP impreso como número: CUIT(11) + tipo(3) + punto de venta(4-5) + CAE(14)
    + vencimiento del CAE(8) + dígito verificador. Da CUIT, tipo y punto de venta exactos."""
    for m in re.finditer(r"(?<!\d)(\d{11})(\d{3})(\d{4,5})(\d{14})(20\d{6})\d(?!\d)", re.sub(r"[\s*]", "", texto)):
        cuit, tipo, pv, cae = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        if cuit_valido(cuit) and (tipo in TIPOS_AFIP or tipo in TIQUES):
            return {"cuit": cuit, "tipo": TIQUES.get(tipo) or TIPOS_AFIP[tipo], "punto_venta": pv.zfill(4), "cae": cae}
    return {}


TIQUES = {81: "Tique Factura A", 82: "Tique Factura B", 83: "Tique", 111: "Tique Factura C", 118: "Tique Factura M"}


def _variantes(c: str):
    """CUITs válidos a un dígito de distancia (el OCR suele errar uno)."""
    for i, ch in enumerate(c):
        for alt in PARECIDOS.get(ch, ""):
            v = c[:i] + alt + c[i + 1:]
            if v[:2] in PREFIJOS and cuit_valido(v):
                yield v


def _distancia(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))


def buscar_cuit(texto: str, excluir: set[str], conocidos: set[str]) -> tuple[str | None, str]:
    """El CUIT del emisor: el primero válido que no sea el de APAI. Si el OCR erró un dígito, se busca
    el válido más cercano (preferentemente uno de un proveedor ya cargado)."""
    crudo = _numeros(texto)
    candidatos = []
    for m in re.finditer(r"(?<!\d)(\d{2})\s*[-.‐–—]?\s*(\d{8})\s*[-.‐–—]?\s*(\d)(?!\d)", crudo):
        candidatos.append("".join(m.groups()))
    for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", crudo):
        candidatos.append(m.group(1))
    candidatos = [c for c in candidatos if not any(_distancia(c, x) <= 2 for x in excluir)]  # APAI mal leído
    for c in candidatos:  # 1) exacto
        if c[:2] in PREFIJOS and cuit_valido(c) and c not in excluir:
            return c, "ocr"
    for c in candidatos:  # 2) un proveedor conocido a 1-2 dígitos de distancia
        cerca = [k for k in conocidos if _distancia(k, c) <= 2 and k not in excluir]
        if cerca:
            return min(cerca, key=lambda k: _distancia(k, c)), "ocr corregido"
    for c in candidatos:  # 3) el CUIT válido más cercano
        v = next((x for x in _variantes(c) if x not in excluir), None)
        if v:
            return v, "ocr corregido"
    return None, ""


def buscar_fecha(texto: str, hoy: date, periodo: tuple[int, int] | None = None) -> tuple[date | None, str]:
    """Fecha de emisión. Primero la rotulada como emisión; descarta inicio de actividades, vencimientos e
    impresión. Corrige años y meses mal leídos (7026, 02/00/2026) con el período que se está cargando."""
    t = _numeros(texto)
    fecha_re = r"(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2,4})(?!\d)"
    rotuladas = list(re.finditer(r"F[oe]cha\s+d[oe]\s+Emisi[oó]n\s*[:.]?\s*" + fecha_re, t, re.I))
    rotuladas += list(re.finditer(r"(?<![\w ]de )(?:F[oe]cha|FECHA)\s*[:.]?\s*" + fecha_re, t))
    otras = [m for m in re.finditer(r"(?<!\d)" + fecha_re, t)
             if not re.search(r"(inicio|activ|vto|venc|impres|vigenc|desde|hasta|fin|cae)", t[max(0, m.start() - 40):m.start()], re.I)]
    anio_p, mes_p = periodo or (hoy.year, hoy.month)

    def armar(m):
        d, mth, y = (int(x) for x in m.groups()[-3:])
        fuente = "ocr"
        if y < 100:
            y += 2000
        if not (hoy.year - 1 <= y <= hoy.year):
            y, fuente = anio_p, "ocr corregido"
        if not 1 <= mth <= 12:
            mth, fuente = mes_p, "ocr corregido"
        try:
            f = date(y, mth, d)
        except ValueError:
            return None
        return (f, fuente) if f <= hoy else None

    for m in rotuladas:
        r = armar(m)
        if r:
            return r
    cand = [r for r in (armar(m) for m in otras) if r]
    if periodo:  # la más cercana al mes que se está cargando
        ref = date(anio_p, mes_p, 15)
        cand.sort(key=lambda r: abs((r[0] - ref).days))
    return cand[0] if cand else (None, "")


def buscar_numero(texto: str) -> tuple[str | None, str | None]:
    t = _numeros(texto)
    m = re.search(r"Punt[oa]\s+d[oe]\s+Vent[ao]\s*[:.]?\s*(\d{1,5}).{0,20}?C[oa]mp[,.]?\s*Nr[oa]\s*[:.]?\s*(\d{1,8})", t, re.I | re.S)
    if m:
        return m.group(1).zfill(4), m.group(2).zfill(8)
    m = re.search(r"(?<!\d)(\d{4,5})\s*[-.‐–—]\s*(\d{8})(?!\d)", t)
    if m:
        return m.group(1).zfill(4), m.group(2)
    m = re.search(r"P\.?\s*V\.?\s*N?(?:ro)?\.?[°º\"”:]*\s*(\d{1,5}).{0,25}?N(?:ro|°|º)\.?\s*T?\.?\s*(\d{4,8})", t, re.I | re.S)
    if m:
        return m.group(1).zfill(4), m.group(2).zfill(8)
    m = re.search(r"(?<!\d)(\d{4,5})\s*-\s*N\W{0,3}\s*T\.?\s*(\d{4,8})(?!\d)", t, re.I)  # tique: 00004 - Nº T. 00007893
    if m:
        return m.group(1).zfill(4), m.group(2).zfill(8)
    m = re.search(r"(?<![A-Za-z0-9])[ABC]\s?(\d{4})(\d{8})(?!\d)", t)  # B001200092823
    if m:
        return m.group(1), m.group(2)
    return None, None


def buscar_tipo(texto: str) -> str | None:
    m = re.search(r"C[oó]d(?:igo)?\.?\s*[:N°º]*\s*0*(\d{1,3})", texto, re.I)
    if m:
        cod = int(m.group(1))
        if cod in TIQUES:
            return TIQUES[cod]
        if cod in TIPOS_AFIP:
            return TIPOS_AFIP[cod]
    if re.search(r"NOTA\s+DE\s+CR[EÉ]DITO", texto, re.I):
        return "Nota de Crédito"
    m = re.search(r"FACTURA\s*[\"“”'(]?\s*([ABC])\b", texto, re.I) or re.search(r"^\s*\W{0,3}([ABC])\s*$", texto, re.M)
    if m and re.search(r"FACTURA", texto, re.I):
        letra = m.group(1).upper()
        return ("Tique Factura " if re.search(r"TIQUE|TICKET", texto, re.I) else "Factura ") + letra
    if re.search(r"TIQUE|TICKET", texto, re.I):
        return "Tique"
    return None


def _montos_texto(t: str) -> list[Decimal]:
    return [v for v in (_importe(x) for x in re.findall(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})|\d+[.,]\d{2}(?!\d)", t)) if v]


def _total_por_iva(t: str, todos: list[Decimal], estimar: bool = False) -> Decimal | None:
    """Régimen de Transparencia Fiscal: 'IVA contenido' permite deducir el total (21 % o 10,5 %).
    Devuelve el monto de la factura que cierra con ese IVA; si ninguno, el total calculado con el 21 %
    cuando coincide con la suma de los renglones."""
    m = re.search(r"IVA\s*conten\w*\s*[:;.]?\s*\$?\s*(\d[\d.,]*\d)", t, re.I)
    iva = _importe(m.group(1)) if m else None
    if not iva or iva <= 0:
        return None
    for alicuota in (Decimal(21), Decimal("10.5")):
        estimado = (iva * (100 + alicuota) / alicuota).quantize(Decimal("0.01"))
        cerca = [x for x in todos if abs(x - estimado) <= max(Decimal(1), estimado * Decimal("0.002"))]
        if cerca:
            return max(cerca, key=todos.count)
    if estimar:  # sin monto que cierre: el total calculado con el 21 % (queda marcado para revisar)
        return (iva * Decimal(121) / Decimal(21)).quantize(Decimal("0.01"))
    return None


def buscar_importe(texto: str) -> tuple[Decimal | None, str]:
    """El TOTAL del comprobante (no el subtotal ni el "total a abonar" con deuda anterior). Une números
    partidos por el OCR ('48009, 11', '145, 000. 00') y corrige un dígito mal leído si el mismo monto
    aparece repetido en la factura (subtotal, renglón)."""
    t = re.sub(r"([.,]\s*\d)[dDoO](?!\w)", r"\g<1>0", texto)          # '. 0d' -> '. 00'
    t = re.sub(r"(\d)\s*([.,])\s+(?=\d{3}\b)", r"\1\2", t)            # '145, 000' -> '145,000'
    t = re.sub(r"(\d)\s*([.,])\s+(\d{2})(?!\d)", r"\1\2\3", t)        # '48009, 11' -> '48009,11'
    montos = []
    for m in re.finditer(r"(?<!SUB)(?<!SUB )(?<!Sub)(?<!Sub-)\b(?:IMPORTE\s+)?(?:TOTA[L!1I|]|TOT\.?\s*VENTA|A\s+PAGAR|TOTAL\s+PAGADO)(?![A-Za-z])"
                         r"(?!\s*(?:DESC|SIN|DE\s*\$?US|IVA|NETO|A\s+ABONAR))[^\d\n]{0,25}(\d[\d.,]*\d)", t, re.I):
        v = _importe(m.group(1))
        if v and v > 0:
            montos.append(v)
    todos = _montos_texto(t)
    por_iva = _total_por_iva(t, todos)
    if not montos:
        # rótulos en una línea y valores en la siguiente ("SUBTOTAL IMPUESTO TOTAL $" / "143600.00 143600.00"):
        # el último renglón así que tenga solo montos (el encabezado de la tabla de productos no cuenta)
        valores = []
        for m in re.finditer(r"\bTOTAL\b[^\n]*\n([^\n]*)", t, re.I):
            if _montos_texto(m.group(1)) and not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", m.group(1)):  # sin palabras: no es un renglón de productos
                valores = _montos_texto(m.group(1)) or valores
        if valores:
            return valores[-1], "ocr"
        if por_iva:
            return por_iva, "ocr corregido"
        estimado = _total_por_iva(t, todos, estimar=True)
        return (estimado, "estimado") if estimado else (None, "")
    total = montos[-1]
    # el "$" leído como dígito ("$40000" -> "440000"): el mismo monto sin el primer dígito se repite en la factura
    sin_primero = f"{total:.2f}"[1:]
    if sin_primero and sin_primero[0] != ".":
        alt = Decimal(sin_primero)
        if alt > 0 and todos.count(alt) >= 2 and todos.count(total) <= 1:
            return alt, "ocr corregido"
    if por_iva and abs(por_iva - total) > max(Decimal(1), total * Decimal("0.01")) and por_iva in todos:
        return por_iva, "ocr corregido"  # el total leído no cierra con el IVA contenido; sí otro monto de la factura
    parecidos = [x for x in set(todos) if x != total and abs(x - total) < max(Decimal(1), total * Decimal("0.001"))]
    mejor = max(parecidos, key=todos.count, default=None)
    if mejor is not None and todos.count(mejor) >= 2 and todos.count(mejor) > todos.count(total):
        return mejor, "ocr corregido"
    return total, "ocr"


def razon_social(texto: str, cuit: str | None, proveedores: dict[str, str]) -> tuple[str | None, str]:
    if cuit and cuit in proveedores:
        return proveedores[cuit], "proveedor"
    # rótulo "Razón Social:" del emisor (el del cliente es APAI: "Apellido y Nombre / Razón Social")
    for m in re.finditer(r"(?<!/ )Raz[oó]n\s+Soc[il]al\s*[:;.]?\s*([^\n]+?)(?:\s+F[oe]cha|\s+C\.?U\.?I\.?T|\s+Domicilio|$)", texto, re.I | re.M):
        nombre = m.group(1).strip(" .:-|")
        if len(nombre) >= 3 and not re.search(r"ASOC|PADRES|APAI|INAC", nombre, re.I):
            return nombre[:160], "ocr"
    for linea in texto.splitlines()[:12]:
        l = re.sub(r"[^\wÁÉÍÓÚÑáéíóúñ .,&-]", "", linea).strip()
        if len(l) >= 5 and sum(c.isalpha() for c in l) >= 4 and l.upper() == l and not re.search(r"\d{3}", l) \
                and not re.search(r"ORIGINAL|DUPLICADO|FACTURA|TIQUE|C\.?U\.?I\.?T|IVA|DOMICILIO|INICIO|ASOC|PADRES|TOTAL", l):
            return l[:160], "ocr"
    return None, ""


def leer_pagina(texto: str, qr_texto: str | None, cuit_apai: str, proveedores: dict[str, str], hoy: date,
                periodo: tuple[int, int] | None = None) -> dict:
    """Datos de la factura de una página. `proveedores`: {cuit: razón social} de los ya cargados."""
    excluir = {digitos(cuit_apai)} if cuit_apai else set()
    d: dict = {"fuentes": {}}
    qr = leer_qr_afip(qr_texto) if qr_texto else None

    def poner(campo, valor, fuente):
        if valor not in (None, ""):
            d[campo] = valor
            d["fuentes"][campo] = fuente

    cuit, f = buscar_cuit(texto, excluir, set(proveedores))
    poner("cuit", cuit, f)
    fecha, f = buscar_fecha(texto, hoy, periodo)
    poner("fecha", fecha, f)
    pv, nro = buscar_numero(texto)
    poner("punto_venta", pv, "ocr")
    poner("numero", nro, "ocr")
    poner("tipo", buscar_tipo(texto), "ocr")
    imp, f = buscar_importe(texto)
    poner("importe", imp, f)
    m = re.search(r"C\.?\s*A\.?\s*E\.?\s*[N°º:.]*\s*(\d{14})", texto, re.I)
    poner("cae", m.group(1) if m else None, "ocr")
    for k, v in codigo_barras(texto).items():  # código de barras de AFIP: exacto
        poner(k, v, "codigo de barras")
    if qr:  # el QR de AFIP es exacto: manda sobre el OCR
        for k in ("cuit", "tipo", "punto_venta", "numero", "fecha", "importe", "cae"):
            poner(k, qr.get(k), "qr")
        if qr.get("es_nc") and d.get("importe"):
            d["importe"] = -abs(d["importe"])
    rs, f = razon_social(texto, d.get("cuit"), proveedores)
    poner("razon_social", rs, f)
    d["faltan"] = [n for k, n in (("cuit", "CUIT"), ("fecha", "fecha"), ("importe", "importe"), ("numero", "número")) if not d.get(k)]
    d["dudosos"] = [k for k, v in d["fuentes"].items() if v in ("ocr", "ocr corregido", "estimado") and k in ("cuit", "fecha", "importe", "numero")]
    return d
