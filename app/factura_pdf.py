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


def _texto_pdf(contenido: bytes) -> tuple[str, list[str]]:
    """Texto de la primera página (las facturas AFIP repiten ORIGINAL/DUPLICADO/TRIPLICADO) y enlaces."""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        if not pdf.pages:
            return "", []
        p = pdf.pages[0]
        return p.extract_text() or "", [h.get("uri") or "" for h in (p.hyperlinks or [])]


def leer_factura(contenido: bytes, qr_texto: str | None = None, cuit_apai: str = "") -> dict:
    texto, enlaces = _texto_pdf(contenido)
    qr = leer_qr_afip(qr_texto) or next((leer_qr_afip(u) for u in enlaces if leer_qr_afip(u)), None)
    apai = digitos(cuit_apai)
    d: dict = {"fuente": [], "texto": bool(texto.strip())}
    plano = re.sub(r"[ \t]+", " ", texto)

    # --- Texto
    if texto.strip():
        d["fuente"].append("texto")
        cuits = [digitos(m) for m in re.findall(r"\b(?:20|23|24|27|30|33|34)-?\d{8}-?\d\b", plano)]
        cuits = [c for c in cuits if cuit_valido(c)]
        emisores = [c for c in cuits if c != apai]
        if emisores:
            d["cuit"] = emisores[0]
        d["receptor_es_apai"] = bool(apai) and apai in cuits
        m = re.search(r"(?<!/ )Raz[oó]n Social:\s*(.+?)(?:\s+Fecha de Emisi|\s+CUIT|\n|$)", plano)
        if m:
            d["razon_social"] = m.group(1).strip()[:160]
        else:  # otros sistemas: primera línea en mayúsculas que no sea un rótulo
            for linea in plano.splitlines()[:8]:
                l = linea.strip()
                if len(l) > 5 and l.upper() == l and not re.search(r"ORIGINAL|DUPLICADO|FACTURA|COD\.|^[ABCM]$", l):
                    d["razon_social"] = l[:160]
                    break
        m = re.search(r"Punto de Venta:?\s*(\d{1,5})\s*Comp\.?\s*Nro:?\s*(\d{1,8})", plano, re.I) \
            or re.search(r"\b(\d{4,5})\s*-\s*(\d{8})\b", plano)
        if m:
            d["punto_venta"], d["numero"] = str(int(m.group(1))).zfill(4), str(int(m.group(2))).zfill(8)
        m = re.search(r"Fecha de Emisi[oó]n:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", plano, re.I) or re.search(r"Fecha:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", plano, re.I)
        if m:
            d["fecha"] = _fecha(m.group(1))
        m = re.search(r"Importe Total:?\s*\$?\s*([\d.,]+)", plano, re.I) or re.search(r"\bTOTAL:?\s*\$?\s*([\d.,]+)", plano, re.I)
        if m:
            d["importe"] = _importe(m.group(1))
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
            m = re.search(r"^\s*([ABCM])\s*$", plano, re.M)
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
