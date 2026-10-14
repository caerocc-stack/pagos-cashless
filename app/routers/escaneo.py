"""
Carga de facturas desde un PDF escaneado.

El navegador separa las páginas, lee el QR de AFIP y hace el OCR (Tesseract) de cada una; acá llega
solo el texto. Se interpreta cada página (app/ocr_factura.py), se juntan las facturas de dos hojas,
se marcan las hojas que no son facturas y las copias repetidas, se buscan duplicados ya cargados y
se sugiere el destino (hoja del Excel), rubro y concepto según la última factura del proveedor.
Nada se guarda acá: el registro lo hace la pantalla de revisión con el alta normal de gastos.
"""
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import config_util
from app.database import get_db
from app.factura_pdf import digitos
from app.models.gasto import Gasto
from app.models.proveedor import Proveedor
from app.ocr_factura import leer_pagina
from app.routers.gastos import gasto_duplicado
from app.tz import ahora_ar

router = APIRouter(prefix="/api/escaneo-facturas", tags=["Facturas escaneadas"])

NO_FACTURA = re.compile(r"comprobante\s+de\s+(recarga|pago|transferencia)|recargaste|mercado\s*pago|transferencia\s+enviada|"
                        r"constancia\s+de|resumen\s+de\s+cuenta", re.I)
SEGUNDA_HOJA = re.compile(r"P[aá]g(?:ina)?\.?\s*([2-9])\s*/\s*([2-9])|Hoja\s*([2-9])\s*(?:de|/)\s*[2-9]", re.I)


class Pagina(BaseModel):
    n: int
    texto: str = Field(default="", max_length=30000)
    qr: str | None = Field(default=None, max_length=3000)


class Analisis(BaseModel):
    archivo: str | None = Field(default=None, max_length=200)
    anio: int
    mes: int = Field(ge=1, le=12)
    paginas: list[Pagina] = Field(min_length=1, max_length=150)


def _a_texto(v):
    return v.isoformat() if isinstance(v, date) else (str(v) if v is not None else None)


def _clave(d: dict):
    return (d.get("cuit"), (d.get("numero") or "").lstrip("0"))


@router.post("/analizar")
def analizar(data: Analisis, db: Session = Depends(get_db)):
    proveedores = {p.cuit: p.razon_social for p in db.query(Proveedor).all() if p.cuit}
    cuit_apai = config_util.get_config(db, "apai_cuit") or ""
    hoy = ahora_ar().date()
    facturas: list[dict] = []
    for p in sorted(data.paginas, key=lambda x: x.n):
        d = leer_pagina(p.texto, p.qr, cuit_apai, proveedores, hoy, (data.anio, data.mes))
        datos = {k: d.get(k) for k in ("fecha", "tipo", "punto_venta", "numero", "cuit", "razon_social", "importe", "cae")}
        hay_texto = len(re.sub(r"\W", "", p.texto)) > 40
        previa = facturas[-1] if facturas else None
        # 2ª hoja: solo si es del mismo proveedor (o no tiene cabecera); a veces se escanea antes que la 1ª
        segunda = SEGUNDA_HOJA.search(p.texto) and previa and (not datos.get("cuit") or datos.get("cuit") == previa["datos"].get("cuit"))
        misma = previa and datos.get("cuit") and datos.get("numero") and _clave(datos) == _clave(previa["datos"])
        sin_cabecera = not datos.get("cuit") and not datos.get("numero") and not datos.get("fecha")
        if previa and previa["tipo_pagina"] == "factura" and (segunda or misma or (sin_cabecera and datos.get("importe") and not previa["datos"].get("importe"))):
            # 2ª hoja (o copia DUPLICADO) de la factura anterior: completa lo que faltaba
            previa["paginas"].append(p.n)
            for k, v in datos.items():
                if v and (not previa["datos"].get(k) or (k == "importe" and segunda)):
                    previa["datos"][k] = v
                    previa["fuentes"][k] = d["fuentes"].get(k, "ocr")
            previa["nota"] = f"Factura de varias hojas: se unieron las páginas {', '.join(map(str, previa['paginas']))}"
            continue
        if not hay_texto:
            tipo = "vacia"
        elif NO_FACTURA.search(p.texto) and not datos.get("cuit"):
            tipo = "otro"
        elif not datos.get("cuit") and not datos.get("numero") and not datos.get("importe"):
            tipo = "otro"
        else:
            tipo = "factura"
        facturas.append({"paginas": [p.n], "tipo_pagina": tipo, "datos": datos, "fuentes": dict(d["fuentes"]), "nota": None})

    salida = []
    vistas: dict = {}
    for f in facturas:
        d = f["datos"]
        cuit = d.get("cuit")
        dup = None
        if cuit and d.get("numero"):
            g = gasto_duplicado(db, cuit, d.get("punto_venta"), d.get("numero"), d.get("tipo"))
            dup = {"id": g.id, "fecha": str(g.fecha), "importe": float(g.importe)} if g else None
        sug = {}
        if cuit:
            g = (db.query(Gasto).filter(Gasto.cuit == digitos(cuit), Gasto.revisado.isnot(False))
                 .order_by(Gasto.fecha.desc(), Gasto.id.desc()).first())
            if g:
                sug = {"categoria": g.categoria, "rubro": g.rubro, "concepto": g.concepto, "destino": g.destino}
            prov = db.query(Proveedor).filter(Proveedor.cuit == digitos(cuit)).first()
            if prov:
                sug["proveedor_id"] = prov.id
                if not sug.get("rubro") and prov.rubro:
                    sug["rubro"] = prov.rubro
        faltan = [n for k, n in (("cuit", "CUIT"), ("fecha", "fecha"), ("numero", "número"), ("importe", "total")) if not d.get(k)]
        dudosos = [k for k, v in f["fuentes"].items() if v in ("ocr corregido", "estimado") and k in ("cuit", "fecha", "numero", "importe")]
        fuera = bool(d.get("fecha")) and (d["fecha"].year, d["fecha"].month) != (data.anio, data.mes)
        repetida = None  # la misma factura escaneada dos veces en el PDF (original y duplicado)
        if cuit and d.get("numero") and f["tipo_pagina"] == "factura":
            repetida = vistas.get(_clave(d))
            vistas.setdefault(_clave(d), f["paginas"][0])
        salida.append({
            "paginas": f["paginas"], "tipo_pagina": f["tipo_pagina"], "nota": f["nota"],
            "datos": {k: (float(v) if k == "importe" and v is not None else _a_texto(v)) for k, v in d.items()},
            "fuentes": f["fuentes"], "faltan": faltan, "dudosos": dudosos, "duplicado": dup,
            "fuera_del_mes": fuera, "sugerencia": sug, "repetida_en_pdf": repetida,
            "con_qr": "qr" in f["fuentes"].values(),
        })
    resumen = {
        "paginas": len(data.paginas), "facturas": sum(1 for f in salida if f["tipo_pagina"] == "factura"),
        "completas": sum(1 for f in salida if f["tipo_pagina"] == "factura" and not f["faltan"]),
        "con_qr": sum(1 for f in salida if f["con_qr"]), "duplicadas": sum(1 for f in salida if f["duplicado"] or f["repetida_en_pdf"]),
        "otras": sum(1 for f in salida if f["tipo_pagina"] != "factura"),
    }
    return {"facturas": salida, "resumen": resumen}
