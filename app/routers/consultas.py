"""Mesa de ayuda del lado de la Asociación: consultas del portal y reportes de problemas del personal."""
import os
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, requiere_admin
from app.models.alumno import Alumno
from app.models.usuario import Usuario
from app.models.portal import Consulta, MensajeConsulta, CuentaPadre
from app.seguridad import auditar
from app import consultas_util as cu
from app.tz import ahora_ar

router = APIRouter(prefix="/api/consultas", tags=["Consultas"])
APP_URL = (os.getenv("APP_URL") or "https://pagos-cashless.vercel.app").rstrip("/")

# Respuestas rápidas para el personal (se pueden editar antes de enviar)
RESPUESTAS_RAPIDAS = [
    ("Pago registrado", "¡Hola! Ya registramos el pago y figura en «Cuotas y pagos». Muchas gracias."),
    ("Pago no encontrado", "¡Hola! Todavía no encontramos ese pago. ¿Nos podés adjuntar el comprobante con la fecha, "
                           "el importe y el código con el que pagaste?"),
    ("Cupón reenviado", "¡Hola! Te reenviamos el cupón: lo tenés en la pestaña «Cupones» del portal y en tu correo."),
    ("Datos actualizados", "¡Hola! Ya actualizamos los datos del alumno. Gracias por avisar."),
    ("Acreditación pendiente", "¡Hola! Los pagos demoran entre 48 y 72 horas hábiles en acreditarse. "
                               "Si pasado ese plazo no figura, respondé este mensaje con el comprobante."),
]


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _dto(x: Consulta, db: Session, detalle=False) -> dict:
    a = db.get(Alumno, x.alumno_id) if x.alumno_id else None
    autor = None
    if x.cuenta_id:
        c = db.get(CuentaPadre, x.cuenta_id)
        autor = c.email if c else None
    elif x.usuario_id:
        u = db.get(Usuario, x.usuario_id)
        autor = u.nombre if u else None
    d = {"id": x.id, "origen": x.origen, "categoria": x.categoria, "categoria_titulo": cu.titulo(x.categoria),
         "asunto": x.asunto, "estado": x.estado, "sin_leer": not x.leida_admin, "autor": autor,
         "alumno": ({"id": a.id, "nombre": f"{a.apellido}, {a.nombre}", "curso": a.curso, "legajo": a.legajo} if a else None),
         "creada": _fmt(x.created_at), "actualizada": _fmt(x.actualizada), "mensajes_n": len(x.mensajes)}
    if detalle:
        d["mensajes"] = [{"autor": m.autor, "autor_nombre": m.autor_nombre, "texto": m.texto,
                          "adjunto_url": m.adjunto_url, "fecha": _fmt(m.created_at)} for m in x.mensajes]
        d["respuestas_rapidas"] = [{"titulo": t, "texto": tx} for t, tx in RESPUESTAS_RAPIDAS]
    return d


@router.get("/")
def listar(estado: str | None = None, origen: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Consulta)
    if estado:
        q = q.filter(Consulta.estado == estado)
    if origen:
        q = q.filter(Consulta.origen == origen)
    return [_dto(x, db) for x in q.order_by(Consulta.leida_admin, Consulta.actualizada.desc()).limit(300).all()]


@router.get("/contador")
def contador(db: Session = Depends(get_db)):
    return {"sin_leer": db.query(Consulta).filter(Consulta.leida_admin.is_(False)).count(),
            "abiertas": db.query(Consulta).filter(Consulta.estado == "abierta").count()}


@router.get("/{cid}")
def ver(cid: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    x = db.get(Consulta, cid)
    if not x:
        raise HTTPException(404, "Consulta no encontrada")
    if not x.leida_admin and user["rol"] == "admin":
        x.leida_admin = True
        db.commit()
    return _dto(x, db, detalle=True)


class Respuesta(BaseModel):
    texto: str
    cerrar: bool = False


@router.post("/{cid}/responder")
def responder(cid: int, data: Respuesta, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    x = db.get(Consulta, cid)
    if not x:
        raise HTTPException(404, "Consulta no encontrada")
    texto = (data.texto or "").strip()
    if not texto:
        raise HTTPException(400, "Escribí la respuesta.")
    db.add(MensajeConsulta(consulta_id=x.id, autor="admin", autor_nombre=admin["nombre"], texto=texto[:4000]))
    x.estado = "cerrada" if data.cerrar else "respondida"
    x.leida_admin = True
    x.leida_autor = False
    x.actualizada = ahora_ar()
    auditar(db, "consulta_respondida", admin["sub"], f"#{x.id}", request)
    db.commit()
    # Aviso por correo al autor
    if x.cuenta_id:
        c = db.get(CuentaPadre, x.cuenta_id)
        if c:
            cu.avisar_padre(c.email, f"Respuesta a tu consulta: {x.asunto}",
                            f"<p>La Asociación respondió tu consulta <b>«{escape(x.asunto)}»</b>:</p>"
                            f"<blockquote style='border-left:3px solid #cbd5e1;margin:0;padding:6px 12px;color:#334155'>"
                            f"{escape(texto[:1500]).replace(chr(10), '<br>')}</blockquote>"
                            "<p>Podés contestar desde el portal.</p>", f"{APP_URL}/portal#consulta-{x.id}")
    elif x.usuario_id:
        u = db.get(Usuario, x.usuario_id)
        if u and u.email:
            cu.enviar_seguro(u.email, f"APAI Pay · Respuesta a tu reporte #{x.id}",
                             f"<p>Respuesta a «{escape(x.asunto)}»:</p><p>{escape(texto[:1500])}</p>")
    return {"ok": True, "mensaje": "Respuesta enviada" + (" y consulta cerrada" if data.cerrar else "")}


class CambioEstado(BaseModel):
    estado: str


@router.post("/{cid}/estado")
def cambiar_estado(cid: int, data: CambioEstado, request: Request, admin=Depends(requiere_admin), db: Session = Depends(get_db)):
    if data.estado not in ("abierta", "respondida", "cerrada"):
        raise HTTPException(400, "Estado inválido")
    x = db.get(Consulta, cid)
    if not x:
        raise HTTPException(404, "Consulta no encontrada")
    x.estado = data.estado
    x.leida_admin = True
    x.actualizada = ahora_ar()
    auditar(db, "consulta_estado", admin["sub"], f"#{x.id} → {data.estado}", request)
    db.commit()
    return {"ok": True}


class Reporte(BaseModel):
    asunto: str
    texto: str
    pantalla: str | None = None


@router.post("/reportar")
def reportar(data: Reporte, request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Botón «Reportar un problema» del sistema (cualquier usuario, también los de solo lectura)."""
    asunto, texto = (data.asunto or "").strip(), (data.texto or "").strip()
    if not asunto or len(texto) < 5:
        raise HTTPException(400, "Completá el asunto y contá qué pasó.")
    if data.pantalla:
        texto += f"\n\n(Pantalla: {data.pantalla[:80]})"
    x = Consulta(origen="sistema", usuario_id=user["uid"], categoria="sistema", asunto=asunto[:160],
                 estado="abierta", leida_admin=False, leida_autor=True)
    db.add(x)
    db.flush()
    db.add(MensajeConsulta(consulta_id=x.id, autor="usuario", autor_nombre=user["nombre"], texto=texto[:4000]))
    auditar(db, "reporte_problema", user["sub"], f"#{x.id} {asunto[:80]}", request)
    db.commit()
    cu.avisar_admins(db, f"Problema reportado: {asunto}",
                     f"<p><b>{escape(user['nombre'])}</b> reportó un problema en el sistema:</p>"
                     f"<p>{escape(texto[:800]).replace(chr(10), '<br>')}</p>", f"{APP_URL}/#consultas")
    return {"ok": True, "mensaje": "Gracias. El reporte llegó al administrador del sistema."}
