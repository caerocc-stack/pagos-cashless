"""
Portal público de facturas para proveedores (/facturas) y bandeja de facturas recibidas del personal.

Público (sin cuenta): cualquiera puede subir uno o más PDF. Protecciones: solo PDF reales de hasta 4 MB,
límite de envíos por IP y por día, campo trampa contra robots, archivos en un depósito PRIVADO
(nunca quedan con una URL pública) y respuesta mínima.

Cada PDF se lee (QR de AFIP + texto) y, si tiene los datos esenciales y está a nombre de APAI, entra
directo a Gastos como "por revisar"; si no, queda en la bandeja para cargarlo a mano.
"""
import hashlib
import json
import os
import re
from datetime import date
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app import config_util, consultas_util as cu
from app.auth import get_current_user, requiere_admin
from app.database import get_db
from app.factura_pdf import a_json, leer_factura, digitos, nombre_valido
from app.models.factura_recibida import FacturaRecibida, ESTADOS
from app.models.gasto import Gasto
from app.models.proveedor import Proveedor
from app.routers.gastos import gasto_duplicado
from app.seguridad import auditar, ip_cliente, registrar_fallo, segundos_bloqueo
from app.storage_util import storage_configurado, subir_privado, url_privada_firmada
from app.tz import ahora_ar

publico = APIRouter(prefix="/api/publico", tags=["Portal de facturas (público)"])
router = APIRouter(prefix="/api/facturas-recibidas", tags=["Facturas recibidas"])

APP_URL = (os.getenv("APP_URL") or "https://pagos-cashless.vercel.app").rstrip("/")
MAX_BYTES = 4 * 1024 * 1024        # Vercel acepta pedidos de hasta 4,5 MB
POR_IP_HORA, POR_DIA = 40, 500


@publico.get("/apai")
def datos_apai(db: Session = Depends(get_db)):
    return config_util.datos_apai(db)


def _limpio(s: str | None, n: int) -> str | None:
    s = re.sub(r"[\x00-\x1f\x7f<>]", " ", (s or "")).strip()
    return s[:n] or None


def procesar(db: Session, fr: FacturaRecibida, contenido: bytes, qr: str | None = None) -> dict:
    """Lee la factura y, si se puede, la carga como gasto por revisar. Devuelve los datos leídos."""
    apai = config_util.get_config(db, "apai_cuit")
    try:
        d = leer_factura(contenido, qr, apai)
    except Exception:
        d = {"completa": False, "faltan": ["todo"], "texto": False, "fuente": []}
    fr.datos = a_json(d)
    if not d.get("completa"):
        fr.estado = "revisar"
        fr.motivo = ("PDF escaneado o sin texto: hay que cargarla a mano" if not d.get("texto") and "qr" not in d.get("fuente", [])
                     else "No se pudo leer: " + ", ".join(d.get("faltan", [])))
        return d
    dup = gasto_duplicado(db, d["cuit"], d.get("punto_venta"), d["numero"], d.get("tipo"))
    if dup:
        fr.estado, fr.gasto_id = "duplicada", dup.id
        fr.motivo = f"Ya estaba cargada como gasto #{dup.id}"
        return d
    otra = (db.query(FacturaRecibida).filter(FacturaRecibida.id != fr.id, FacturaRecibida.estado == "cargada").all())
    for o in otra:
        try:
            od = json.loads(o.datos or "{}")
        except ValueError:
            continue
        if od.get("cuit") == d["cuit"] and od.get("numero") == d["numero"] and od.get("punto_venta") == d.get("punto_venta"):
            fr.estado, fr.gasto_id, fr.motivo = "duplicada", o.gasto_id, "La misma factura ya se había recibido"
            return d

    prov = db.query(Proveedor).filter(Proveedor.cuit == d["cuit"]).first()
    nombre = d.get("razon_social") if nombre_valido(d.get("razon_social")) else None
    if not prov:
        prov = Proveedor(cuit=d["cuit"], razon_social=(nombre or fr.proveedor_declarado or f"CUIT {d['cuit']} (completar razón social)")[:160],
                         email=fr.email if fr.email and "@" in fr.email else None)
        db.add(prov)
        db.flush()
    previo = (db.query(Gasto).filter(Gasto.proveedor_id == prov.id, Gasto.revisado.isnot(False))
              .order_by(Gasto.fecha.desc(), Gasto.id.desc()).first())
    notas = []
    if d.get("receptor_es_apai") is False:
        notas.append("ATENCIÓN: la factura no figura a nombre de APAI")
    if not nombre and not fr.proveedor_declarado and prov.razon_social.startswith("CUIT "):
        notas.append("No se pudo leer la razón social del proveedor: completala")
    if fr.comentario:
        notas.append("Comentario del proveedor: " + fr.comentario)
    g = Gasto(fecha=d["fecha"], tipo_comprobante=d.get("tipo") or "Factura C", punto_venta=d.get("punto_venta"),
              numero=d["numero"], proveedor_id=prov.id, razon_social=prov.razon_social, cuit=d["cuit"],
              importe=Decimal(str(d["importe"])), concepto=d.get("concepto") or (previo.concepto if previo else None),
              rubro=prov.rubro or (previo.rubro if previo else None), categoria=previo.categoria if previo else None,
              destino=previo.destino if previo else None, vencimiento=d.get("vencimiento"), cae=d.get("cae"),
              adjunto_url=f"/api/facturas-recibidas/{fr.id}/archivo", origen="portal", revisado=False,
              factura_recibida_id=fr.id, creado_por="Portal de proveedores", notas=" · ".join(notas)[:400] or None)
    db.add(g)
    db.flush()
    fr.estado, fr.gasto_id = "cargada", g.id
    fr.motivo = "Cargada como gasto pendiente de pago" + (" — no está a nombre de APAI" if d.get("receptor_es_apai") is False else "")
    return d


@publico.post("/facturas")
async def recibir_factura(request: Request, archivo: UploadFile = File(...), envio: str = Form(...),
                          proveedor: str | None = Form(None), email: str | None = Form(None),
                          comentario: str | None = Form(None), qr: str | None = Form(None), web: str | None = Form(None),
                          db: Session = Depends(get_db)):
    ip = ip_cliente(request)
    if web:  # campo trampa: solo lo completan los robots
        raise HTTPException(400, "No se pudo procesar el envío.")
    if (espera := segundos_bloqueo(db, f"facturas-ip:{ip}", POR_IP_HORA, 60)) or segundos_bloqueo(db, "facturas-dia", POR_DIA, 1440):
        raise HTTPException(429, "Se recibieron demasiadas facturas seguidas. Probá de nuevo en un rato.")
    if not re.fullmatch(r"[a-f0-9]{16,40}", envio or ""):
        raise HTTPException(400, "Envío inválido.")
    contenido = await archivo.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise HTTPException(400, "El archivo supera los 4 MB. Si es una factura escaneada, bajá la resolución.")
    if not contenido.startswith(b"%PDF-"):
        raise HTTPException(400, "Solo se aceptan facturas en PDF.")
    registrar_fallo(db, f"facturas-ip:{ip}")
    registrar_fallo(db, "facturas-dia")

    nombre = _limpio(re.sub(r"[\\/]", "_", archivo.filename or "factura.pdf"), 200) or "factura.pdf"
    sha = hashlib.sha256(contenido).hexdigest()
    previa = db.query(FacturaRecibida).filter(FacturaRecibida.sha256 == sha, FacturaRecibida.estado != "descartada").first()
    if previa:
        db.commit()
        return {"ok": True, "estado": "duplicada", "mensaje": "Esta factura ya nos había llegado. ¡Gracias!"}

    fr = FacturaRecibida(envio=envio, archivo_nombre=nombre, tamanio=len(contenido), sha256=sha,
                         proveedor_declarado=_limpio(proveedor, 160), email=_limpio(email, 150),
                         comentario=_limpio(comentario, 500), ip=ip[:60], estado="revisar")
    try:
        if storage_configurado():
            fr.ruta_storage = subir_privado(contenido)
        else:
            fr.contenido = contenido
    except ValueError as e:
        # Si Storage falla (p. ej. clave de Supabase sin permisos) la factura no se pierde: queda en la base
        print("AVISO: factura guardada en la base porque Storage falló:", e, flush=True)
        fr.contenido = contenido
    db.add(fr)
    db.flush()
    d = procesar(db, fr, contenido, (qr or "")[:3000] or None)
    primero = db.query(FacturaRecibida).filter(FacturaRecibida.envio == envio).count() == 1
    db.commit()
    if primero:
        quien = escape(fr.proveedor_declarado or d.get("razon_social") or "Un proveedor")
        cu.avisar_admins(db, "Nueva factura de proveedor", f"<p><b>{quien}</b> subió facturas en el portal de proveedores.</p>"
                         "<p>Ya están en Gastos (pestaña «Recibidas de proveedores»).</p>", f"{APP_URL}/#gastos")
    leida = fr.estado == "cargada"
    return {"ok": True, "estado": "recibida" if fr.estado != "duplicada" else "duplicada",
            "leida": leida, "proveedor": d.get("razon_social"), "numero": f"{d.get('punto_venta') or ''}-{d.get('numero') or ''}".strip("-") or None,
            "importe": float(d["importe"]) if d.get("importe") is not None else None,
            "fecha": d["fecha"].isoformat() if isinstance(d.get("fecha"), date) else None,
            "a_nombre_de_apai": d.get("receptor_es_apai"),
            "mensaje": "Factura recibida. ¡Gracias!" if fr.estado != "duplicada" else "Esta factura ya estaba cargada. ¡Gracias!"}


# ---------------------------------------------------------------- bandeja del personal

def _dto(fr: FacturaRecibida, db: Session) -> dict:
    try:
        d = json.loads(fr.datos or "{}")
    except ValueError:
        d = {}
    g = db.get(Gasto, fr.gasto_id) if fr.gasto_id else None
    return {"id": fr.id, "envio": fr.envio, "archivo": fr.archivo_nombre, "tamanio": fr.tamanio,
            "recibida": fr.created_at.strftime("%Y-%m-%dT%H:%M:%S") if fr.created_at else None,
            "proveedor_declarado": fr.proveedor_declarado, "email": fr.email, "comentario": fr.comentario,
            "estado": fr.estado, "estado_texto": ESTADOS.get(fr.estado, fr.estado), "motivo": fr.motivo, "datos": d,
            "gasto": {"id": g.id, "revisado": g.revisado, "importe": float(g.importe), "pagado": bool(g.forma_pago)} if g else None}


@router.get("/")
def listar(estado: str | None = None, db: Session = Depends(get_db)):
    q = db.query(FacturaRecibida)
    if estado:
        q = q.filter(FacturaRecibida.estado == estado)
    return [_dto(x, db) for x in q.order_by(FacturaRecibida.created_at.desc()).limit(300).all()]


@router.get("/contador")
def contador(db: Session = Depends(get_db)):
    sin_cargar = db.query(FacturaRecibida).filter(FacturaRecibida.estado == "revisar").count()
    sin_revisar = db.query(Gasto).filter(Gasto.revisado.is_(False)).count()
    return {"sin_cargar": sin_cargar, "sin_revisar": sin_revisar, "por_revisar": sin_cargar + sin_revisar}


@router.get("/{fid}/archivo")
def archivo(fid: int, db: Session = Depends(get_db)):
    fr = db.get(FacturaRecibida, fid)
    if not fr:
        raise HTTPException(404, "Factura no encontrada")
    if fr.ruta_storage:
        try:
            return RedirectResponse(url_privada_firmada(fr.ruta_storage), status_code=302)
        except Exception:
            raise HTTPException(503, "No se pudo abrir el archivo en este momento.")
    if fr.contenido:
        nombre = re.sub(r'[^\w .()-]', "_", fr.archivo_nombre)
        return Response(fr.contenido, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{nombre}"', "Cache-Control": "private, no-store"})
    raise HTTPException(404, "El archivo no está disponible")


@router.post("/{fid}/descartar")
def descartar(fid: int, request: Request, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    fr = db.get(FacturaRecibida, fid)
    if not fr:
        raise HTTPException(404, "Factura no encontrada")
    if fr.estado == "cargada" and fr.gasto_id:
        raise HTTPException(400, "Ya se cargó como gasto: si no corresponde, eliminá el gasto primero.")
    fr.estado = "descartada"
    auditar(db, "factura_recibida_descartada", admin["sub"], f"#{fr.id} {fr.archivo_nombre}", request)
    db.commit()
    return {"ok": True, "mensaje": "Factura descartada"}


@router.post("/{fid}/reprocesar")
def reprocesar(fid: int, datos: dict, db: Session = Depends(get_db), admin=Depends(requiere_admin)):
    """Vuelve a leer la factura (por ejemplo con el QR leído en esta computadora)."""
    fr = db.get(FacturaRecibida, fid)
    if not fr:
        raise HTTPException(404, "Factura no encontrada")
    if fr.estado == "cargada":
        return {"ok": True, "mensaje": "Ya está cargada como gasto", "estado": fr.estado}
    contenido = fr.contenido
    if contenido is None and fr.ruta_storage:
        import urllib.request
        with urllib.request.urlopen(url_privada_firmada(fr.ruta_storage, 60), timeout=30) as r:
            contenido = r.read(MAX_BYTES + 1)
    if not contenido:
        raise HTTPException(404, "El archivo no está disponible")
    procesar(db, fr, contenido, str(datos.get("qr") or "")[:3000] or None)
    db.commit()
    return {"ok": True, "estado": fr.estado, "mensaje": ESTADOS.get(fr.estado, fr.estado), "gasto_id": fr.gasto_id}
