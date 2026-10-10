"""
Estado de cuenta de un alumno, cuota por cuota.

Reglas (definidas por la Asociación):
- Cada cuota mensual vence el ÚLTIMO DÍA de su mes; la matrícula vence con la primera cuota (marzo).
  Una cuota que todavía no venció no es deuda: figura "a vencer".
- Cada pago se imputa por su FECHA DE PAGO (no por la de acreditación): un pago hecho el 30/09 que
  se acredita en octubre paga la cuota de septiembre; uno del 09/10 acreditado el 12/10 paga octubre.
- Primero cubre la cuota del mes en que se pagó; lo que sobra cubre lo más viejo que se deba
  (matrícula y cuotas atrasadas, en orden) y, si todavía sobra, queda a favor para las cuotas siguientes.
"""
import calendar
from datetime import date
from decimal import Decimal

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MES_INICIO = 3  # las cuotas arrancan en marzo
CERO = Decimal("0")


def fin_de_mes(anio: int, mes: int) -> date:
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def fecha_imputacion(p) -> date:
    """Fecha que define a qué mes corresponde un pago: la de pago; si no se informó, la de proceso."""
    return p.fecha_pago or p.fecha


def anio_de_pago(p) -> int:
    return fecha_imputacion(p).year


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _lista_meses(meses: list[int]) -> str:
    nombres = [MESES[m - 1] for m in meses]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def estado_cuenta(alumno, curso, pagos, anio: int, hoy: date | None = None, mes_corte: int | None = None) -> dict:
    """
    pagos: pagos del alumno imputables a `anio` (ver anio_de_pago).
    Vencido = cuotas cuyo vencimiento ya pasó (respecto de `hoy`); si se indica `mes_corte`
    (filtro del personal) se toman como vencidas todas las cuotas hasta ese mes inclusive.
    """
    hoy = hoy or date.today()
    cond = (alumno.condicion or "").strip().lower()
    deuda_ant = _dec(alumno.deuda_anio_anterior)
    pagos = sorted(pagos, key=lambda p: (fecha_imputacion(p), p.id or 0))
    total_pagado = sum((_dec(p.importe) for p in pagos), CERO)

    base = {"anio": anio, "pagado": float(total_pagado), "deuda_anterior": float(deuda_ant), "items": [],
            "cuotas_adeudadas": 0, "matricula_adeudada": 0.0, "meses_adeudados": [], "detalle_deuda": "",
            "proximo": None, "saldo_a_favor": 0.0, "cuotas_pagas": 0}

    exento = cond in ("becado", "exento") or bool(getattr(alumno, "cuota_excluir", False))
    if exento or not curso:
        estado = (alumno.condicion or "Exento") if exento else "Sin curso"
        base.update(esperado=0.0, deuda=0.0, deuda_total=float(deuda_ant), estado=estado,
                    pagos=[_pago_dto(p, []) for p in pagos])
        return base

    cuota = _dec(getattr(alumno, "cuota_personalizada", None) or curso.cuota)
    matricula = _dec(curso.matricula)
    n = max(0, min(int(curso.n_cuotas or 0), 12 - MES_INICIO + 1))

    def vencido(mes: int) -> bool:
        return mes <= mes_corte if mes_corte is not None else fin_de_mes(anio, mes) < hoy

    items = []
    if matricula > 0:
        items.append({"clave": "matricula", "concepto": "Matrícula", "mes": MES_INICIO, "importe": matricula})
    for i in range(n):
        mes = MES_INICIO + i
        items.append({"clave": f"cuota-{mes}", "concepto": f"Cuota de {MESES[mes - 1]}" if n > 1 else "Cuota",
                      "mes": mes, "importe": cuota})
    for it in items:
        it["pagado"] = CERO

    def aplicar(it, monto: Decimal, destino: list) -> Decimal:
        falta = it["importe"] - it["pagado"]
        if monto <= 0 or falta <= 0:
            return monto
        usa = min(falta, monto)
        it["pagado"] += usa
        destino.append(it["concepto"])
        return monto - usa

    imputaciones = []
    a_favor = CERO
    for p in pagos:
        resto, destino = _dec(p.importe), []
        f = fecha_imputacion(p)
        if f.year == anio:  # 1) la cuota del mes en que pagó
            propio = next((it for it in items if it["clave"] == f"cuota-{f.month}"), None)
            if propio:
                resto = aplicar(propio, resto, destino)
        for it in items:  # 2) lo más viejo que se deba (matrícula primero)
            if resto <= 0:
                break
            resto = aplicar(it, resto, destino)
        if resto > 0:
            a_favor += resto
            destino.append("saldo a favor")
        imputaciones.append(_pago_dto(p, destino))

    esperado = deuda = CERO
    adeudadas, meses_deuda = 0, []
    matricula_debe = CERO
    proximo = None
    salida = []
    for it in items:
        saldo = it["importe"] - it["pagado"]
        venc = fin_de_mes(anio, it["mes"])
        es_vencido = vencido(it["mes"])
        if saldo <= 0:
            est = "pagada"
        elif es_vencido:
            est = "parcial" if it["pagado"] > 0 else "adeudada"
        else:
            est = "a_vencer"
        if es_vencido:
            esperado += it["importe"]
            if saldo > 0:
                deuda += saldo
                if it["clave"] == "matricula":
                    matricula_debe = saldo
                else:
                    adeudadas += 1
                    meses_deuda.append(it["mes"])
        elif saldo > 0 and proximo is None:
            proximo = {"concepto": it["concepto"], "vence": venc.isoformat(), "importe": float(saldo)}
        salida.append({"concepto": it["concepto"], "mes": it["mes"], "vence": venc.isoformat(),
                       "importe": float(it["importe"]), "pagado": float(it["pagado"]), "saldo": float(max(saldo, CERO)),
                       "estado": est, "vencida": es_vencido})

    partes = []
    if matricula_debe > 0:
        partes.append("la matrícula")
    if adeudadas:
        partes.append(f"{adeudadas} cuota{'s' if adeudadas > 1 else ''} ({_lista_meses(meses_deuda)})")
    detalle = ("Debe " + " y ".join(partes)) if partes else ""

    if deuda <= 0:
        estado = "Al día"
    elif total_pagado <= 0:
        estado = "Sin pagos"
    else:
        estado = "Moroso"

    base.update(
        esperado=float(esperado), deuda=float(deuda), deuda_total=float(deuda + deuda_ant), estado=estado,
        items=salida, cuotas_adeudadas=adeudadas, matricula_adeudada=float(matricula_debe),
        meses_adeudados=[MESES[m - 1] for m in meses_deuda], detalle_deuda=detalle, proximo=proximo,
        saldo_a_favor=float(a_favor), cuotas_pagas=sum(1 for s in salida if s["estado"] == "pagada" and s["concepto"] != "Matrícula"),
        pagos=imputaciones, cuota=float(cuota), matricula=float(matricula), n_cuotas=n,
    )
    return base


def _pago_dto(p, destino: list) -> dict:
    return {"id": p.id, "fecha": str(p.fecha), "fecha_pago": str(p.fecha_pago) if p.fecha_pago else None,
            "importe": float(p.importe), "canal": p.canal, "via": p.via,
            "imputado_a": ", ".join(dict.fromkeys(destino)) if destino else None}
