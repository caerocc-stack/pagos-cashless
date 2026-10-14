"""
Lectura de facturas en PDF (las que suben los proveedores en /facturas).

1) Si hay QR de AFIP/ARCA (lo decodifica el navegador al subir, o viene como enlace en el PDF), sus datos
   mandan: CUIT emisor, tipo, punto de venta, número, fecha e importe total.
2) El texto del PDF completa o confirma: razón social, CAE, vencimiento, neto/IVA, concepto y el receptor
   (para verificar que la factura esté hecha a nombre de APAI).
Funciona con las facturas electrónicas de AFIP ("Comprobantes en línea") y con la mayoría de los sistemas
de facturación; si no encuentra lo esencial, la factura queda para cargar a mano.
"""
import base64
import io
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIPOS_AFIP = {
    1: "Factura A", 2: "Comprobante", 3: "Nota de Crédito",
    6: "Factura B", 7: "Comprobante", 8: "Nota de Crédito",
    11: "Factura C", 12: "Comprobante", 13: "Nota de Crédito",
    51: "Factura A", 52: "Comprobante", 53: "Nota de Crédito",
    81: "Ticket", 82: "Ticket", 83: "Ticket",
}
NC_AFIP = {3, 8, 13, 53}
QR_HOSTS = ("afip.gob.ar/fe/qr", "arca.gob.ar/fe/qr", "afip.gob.ar/genericos/comprobantes/cae", "arca.gob.ar/genericos/comprobantes/cae")


def digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def cuit_valido(cuit) -> bool:
    """Dígito verificador del CUIT/CUIL."""
    c = digitos(cuit)
    if len(c) != 11:
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    r = 11 - sum(int(a) * b for a, b in zip(c[:10], pesos)) % 11
    dv = 0 if r == 11 else 9 if r == 10 else r
    return dv == int(c[10])


def _importe(txt: str) -> Decimal | None:
    """'398000,00' / '398.000,00' / '1,234.56' / '$ 12.345' -> Decimal."""
    t = re.sub(r"[^\d.,-]", "", txt or "")
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.search(r"\.\d{3}$", t):
        t = t.replace(".", "")
    try:
        return Decimal(t).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _fecha(txt: str) -> date | None:
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", txt or "")
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = y + 2000 if y < 100 else y
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def leer_qr_afip(texto: str | None) -> dict | None:
    """Datos del QR de AFIP: https://www.afip.gob.ar/fe/qr/?p=<base64(JSON)>."""
    if not texto or len(texto) > 3000:
        return None
    t = texto.strip()
    if not any(h in t for h in QR_HOSTS):
        return None
    crudo = re.search(r"[?&]p=(\{.*\})", t)  # algunos sistemas ponen el JSON sin codificar
    m = re.search(r"[?&]p=([A-Za-z0-9+/=_%-]+)", t)
    if not crudo and not m:
        return None
    try:
        if crudo:
            j = json.loads(crudo.group(1))
        else:
            p = m.group(1).replace("%3D", "=").replace("%2B", "+").replace("%2F", "/").replace("-", "+").replace("_", "/")
            j = json.loads(base64.b64decode(p + "=" * (-len(p) % 4)).decode("utf-8", "ignore"))
        cuit = digitos(j.get("cuit"))
        tipo = int(j.get("tipoCmp"))
        return {
            "cuit": cuit, "tipo_cmp": tipo, "tipo": TIPOS_AFIP.get(tipo, "Comprobante"), "es_nc": tipo in NC_AFIP,
            "punto_venta": str(int(j.get("ptoVta"))).zfill(4), "numero": str(int(j.get("nroCmp"))).zfill(8),
            "fecha": date.fromisoformat(str(j.get("fecha"))[:10]),
            "importe": Decimal(str(j.get("importe"))).quantize(Decimal("0.01")),
            "cae": digitos(j.get("codAut"))[:20] or None, "receptor": digitos(j.get("nroDocRec")) or None,
        }
    except Exception:
        return None


def juntar_espaciado(texto: str) -> str:
    """Algunos PDF guardan el texto con espacios entre letras ('F A C T U R A  B 0 0 0 7'): se juntan."""
    return re.sub(r"(?<!\S)(?:\S ){3,}\S(?!\S)", lambda m: m.group().replace(" ", ""), texto)


EMPRESA = re.compile(r"\b(S\.?\s?A\.?\s?S?\.?|S\.?\s?R\.?\s?L\.?|S\.?\s?A\.?\s?C\.?\s?I\.?|S\.?\s?H\.?|COOP\w*|S\.?\s?C\.?)\s*$", re.I)
NO_NOMBRE = re.compile(r"ORIGINAL|DUPLICADO|TRIPLICADO|FACTURA|TIQUE|COMPROBANTE|^COD\b|C[OÓ]DIGO|C\.?U\.?I\.?T|IVA|DOMICILIO|INICIO|"
                       r"ASOC|PADRES|APAI|INAC|TOTAL|FECHA|P[AÁ]GINA|PUNTO DE VENTA|RESPONSABLE|MONOTRIBUTO|CONSUMIDOR|"
                       r"LOCALIDAD|DIRECCI[OÓ]N|CLIENTE|VENDEDOR|COND\.|REL\.|SE[NÑ]OR|REMITO|:", re.I)


def nombre_valido(s: str | None) -> bool:
    """Descarta rótulos tomados como razón social ('COD 06', 'FACTURA B 0007-…', números)."""
    s = (s or "").strip()
    return len(s) >= 4 and sum(c.isalpha() for c in s) >= 4 and not NO_NOMBRE.search(s) and not re.search(r"\d{4,}", s)


SUFIJO_EMPRESA = r"(?:S\.?\s?R\.?\s?L\.?|S\.?\s?A\.?\s?S\.?|S\.?\s?A\.?(?:\s?C\.?\s?I\.?(?:\s?F\.?)?)?|S\.?\s?H\.?|COOP\w*)"


def buscar_razon_social(plano: str, cuit: str | None = None) -> str | None:
    m = re.search(r"(?<!/ )Raz[oó]n Social:\s*(.+?)(?:\s+Fecha de Emisi|\s+CUIT|\n|$)", plano, re.I)
    if m and nombre_valido(m.group(1)) and not re.search(r"ASOC|PADRES", m.group(1), re.I):
        return m.group(1).strip()[:160]
    if cuit and len(cuit) == 11:  # "GRUPO AGG SRL 30-71576552-3": el nombre junto al CUIT del emisor
        cuit_re = rf"{cuit[:2]}-?{cuit[2:10]}-?{cuit[10]}"
        for l in plano.splitlines():
            m = re.search(rf"^\s*([^\d:]{{4,80}}?)\s*{cuit_re}\s*$", l)  # sin "CUIT:" en el medio (eso es el domicilio)
            if m and nombre_valido(m.group(1).strip(" -|·")):
                return m.group(1).strip(" -|·")[:160]
    lineas = [l.strip(" |·-") for l in plano.splitlines()[:15]]
    for l in lineas:  # nombre de empresa al principio del renglón ("GRUPO AGG SRL Nº: 0035-…")
        m = re.match(rf"([A-ZÁÉÍÓÚÑ][\w&.,' ]{{1,70}}?\b{SUFIJO_EMPRESA})(?=\s|$)", l)
        if m and nombre_valido(m.group(1)):
            return m.group(1).strip()[:160]
    for l in lineas:  # 1) nombre de fantasía "… de Nochetti Silvia Beatriz": el titular
        m = re.search(r"\bde\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,4})(?=\s+[A-ZÁÉÍÓÚÑ]{3,}|\s*$)", l)
        if m and nombre_valido(m.group(1)):
            return m.group(1).upper()[:160]
    for l in lineas:  # 2) la que termina como nombre de empresa (S.A., S.R.L., …)
        if EMPRESA.search(l) and nombre_valido(l):
            return l[:160]
    for l in lineas:  # 2) primera línea en mayúsculas que no sea un rótulo
        if len(l) > 5 and l.upper() == l and nombre_valido(l):
            return l[:160]
    return None


def _texto_pdf(contenido: bytes) -> tuple[str, list[str]]:
    """Texto de la primera página (las facturas AFIP repiten ORIGINAL/DUPLICADO/TRIPLICADO) y enlaces."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        if not pdf.pages:
            return "", []
        p = pdf.pages[0]
        texto = p.extract_text() or ""
        tokens = texto.split()
        if tokens and sum(len(t) <= 2 for t in tokens) / len(tokens) > 0.45:
            # PDF de letra de ancho fijo con espacios sueltos ("N o ch et t i"): se rearma con la posición de
            # cada letra, sin los espacios, y se separan las palabras por la distancia real entre letras
            sin_espacios = p.filter(lambda o: o.get("object_type") != "char" or (o.get("text") or "").strip())
            texto = sin_espacios.extract_text(x_tolerance=1.5) or texto
        return texto, [h.get("uri") or "" for h in (p.hyperlinks or [])]


def leer_factura(contenido: bytes, qr_texto: str | None = None, cuit_apai: str = "") -> dict:
    texto, enlaces = _texto_pdf(contenido)
    qr = leer_qr_afip(qr_texto) or next((leer_qr_afip(u) for u in enlaces if leer_qr_afip(u)), None)
    apai = digitos(cuit_apai)
    d: dict = {"fuente": [], "texto": bool(texto.strip())}
    plano = juntar_espaciado(re.sub(r"[ \t]+", " ", texto))

    # --- Texto
    if texto.strip():
        d["fuente"].append("texto")
        cuits = [digitos(m) for m in re.findall(r"\b(?:20|23|24|27|30|33|34)-?\d{8}-?\d\b", plano)]
        cuits = [c for c in cuits if cuit_valido(c)]
        emisores = [c for c in cuits if c != apai]
        if emisores:
            d["cuit"] = emisores[0]
        d["receptor_es_apai"] = bool(apai) and apai in cuits
        rs = buscar_razon_social(plano, d.get("cuit"))
        if rs:
            d["razon_social"] = rs
        m = re.search(r"Punto de Venta:?\s*(\d{1,5})\s*Comp\.?\s*Nro:?\s*(\d{1,8})", plano, re.I) \
            or re.search(r"\b(\d{4,5})\s*-\s*(\d{8})\b", plano)
        if m:
            d["punto_venta"], d["numero"] = str(int(m.group(1))).zfill(4), str(int(m.group(2))).zfill(8)
        m = re.search(r"Fecha de Emisi[oó]n:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", plano, re.I) or re.search(r"Fecha:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", plano, re.I)
        if m:
            d["fecha"] = _fecha(m.group(1))
        # el total, en el mismo renglón del rótulo (el encabezado de la tabla "… TOTAL" no cuenta)
        m = re.search(r"Importe Total:?[ \t]*\$?[ \t]*(\d[\d.,]*)", plano, re.I)
        if m:
            d["importe"] = _importe(m.group(1))
        else:
            from app.ocr_factura import buscar_importe
            imp, _ = buscar_importe(plano)
            if imp:
                d["importe"] = imp
        m = re.search(r"Importe Neto Gravado:?\s*\$?\s*([\d.,]+)", plano, re.I)
        if m:
            d["neto"] = _importe(m.group(1))
        ivas = [_importe(x) for x in re.findall(r"IVA\s*\d{1,2}(?:[.,]\d+)?\s*%:?\s*\$?\s*([\d.,]+)", plano, re.I)]
        if ivas:
            d["iva"] = sum((x for x in ivas if x), Decimal("0"))
        m = re.search(r"C\.?A\.?E\.?\s*N?[°º]?:?\s*(\d{14})", plano, re.I)
        if m:
            d["cae"] = m.group(1)
        m = re.search(r"Vto\.? para el pago:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", plano, re.I)
        if m:
            d["vencimiento"] = _fecha(m.group(1))
        m = re.search(r"COD\.?\s*0?(\d{2,3})", plano)
        cod = int(m.group(1)) if m else None
        if re.search(r"NOTA DE CR[EÉ]DITO", plano, re.I):
            d["tipo"], d["es_nc"] = "Nota de Crédito", True
        elif cod in TIPOS_AFIP:
            d["tipo"], d["es_nc"] = TIPOS_AFIP[cod], cod in NC_AFIP
        else:
            m = re.search(r"^\s*([ABCM])\s*$", plano, re.M) or re.search(r"\bFACTURA\s+([ABCM])\b", plano)
            if m and re.search(r"FACTURA", plano, re.I):
                d["tipo"] = "Factura A" if m.group(1) == "M" else f"Factura {m.group(1)}"
        m = re.search(r"Condici[oó]n frente al IVA:\s*(.+?)(?:\s+Fecha|\s+Domicilio|\n|$)", plano)
        if m:
            d["condicion_iva"] = m.group(1).strip()[:60]
        # Concepto: primera línea del detalle
        m = re.search(r"(?:Producto\s*/\s*Servicio|Descripci[oó]n)[^\n]*\n(.+)", plano, re.I)
        if m:
            concepto = re.split(r"\s+\d+[.,]\d{2}\s", m.group(1) + " ")[0].strip()
            if 3 <= len(concepto) <= 200 and not re.match(r"^(Subtotal|Importe)", concepto, re.I):
                d["concepto"] = concepto[:200]

    # --- QR (manda sobre el texto en los datos que trae)
    if qr:
        d["fuente"].append("qr")
        for k in ("cuit", "tipo", "es_nc", "punto_venta", "numero", "fecha", "importe"):
            d[k] = qr[k]
        d["cae"] = d.get("cae") or qr.get("cae")
        if qr.get("receptor") and apai:
            d["receptor_es_apai"] = qr["receptor"] == apai or d.get("receptor_es_apai", False)

    if d.get("es_nc") and d.get("importe"):
        d["importe"] = -abs(d["importe"])
    d["completa"] = all(d.get(k) for k in ("cuit", "fecha", "numero", "importe"))
    faltan = [n for k, n in (("cuit", "CUIT"), ("fecha", "fecha"), ("numero", "número"), ("importe", "importe")) if not d.get(k)]
    d["faltan"] = faltan
    return d


def a_json(d: dict) -> str:
    def conv(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, Decimal):
            return float(v)
        return v
    return json.dumps({k: conv(v) for k, v in d.items()}, ensure_ascii=False)
