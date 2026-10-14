"""
Estado de cuenta de un alumno, cuota por cuota y curso por curso.

Reglas (definidas por la Asociación):
- Cada cuota mensual vence el ÚLTIMO DÍA de su mes; la matrícula vence con la primera cuota del curso.
  Una cuota que todavía no venció no es deuda: figura "a vencer".
- Cada pago se imputa por su FECHA DE PAGO (no por la de acreditación): un pago hecho el 30/09 que
  se acredita en octubre paga la cuota de septiembre; uno del 09/10 acreditado el 12/10 paga octubre.
- Primero cubre la cuota del mes en que se pagó; lo que sobra cubre lo más viejo que se deba
  (matrícula y cuotas atrasadas, en orden) y, si todavía sobra, queda a favor.
- Un alumno puede cursar más de un curso en el año (aeronavegantes, exámenes): cada curso tiene sus
  cuotas. Si en el mes del pago hay cuotas de varios cursos, se elige la del curso cuyo importe
  coincide con el pagado. Un pago puede imputarse a mano a un curso (pago.curso_id).
"""
import calendar
import re
from datetime import date
from decimal import Decimal

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MES_INICIO = 3  # las cuotas arrancan en marzo
CERO = Decimal("0")


def fin_de_mes(anio: int, mes: int) -> date:
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def fecha_imputacion(p) -> date:
    """Fecha que define qué cuota paga: la de pago (lo pagado el 30/09 paga septiembre aunque SIRO lo procese
    en octubre); si no se informó, la de proceso. La cobranza del mes (cuándo entró la plata) va siempre por
    la fecha de proceso: ver `fecha_cobro`."""
    return p.fecha_pago or p.fecha


def fecha_cobro(p) -> date:
    """Fecha en que entró el pago: la Fecha de Proceso del listado de cobranzas de SIRO."""
    return p.fecha


def anio_de_pago(p) -> int:
    return fecha_imputacion(p).year


def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _lista_meses(meses: list[int]) -> str:
    nombres = [MESES[m - 1] for m in meses]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def plan_simple(curso, mes_inicio: int | None = None) -> list[dict]:
    """Un único curso (el caso habitual)."""
    mes_inicio = mes_inicio or getattr(curso, "mes_inicio", None) or MES_INICIO
    return [{"clave": "principal", "curso": curso, "nombre": curso.nombre, "mes_inicio": mes_inicio,
             "principal": True, "curso_id": getattr(curso, "id", None)}] if curso else []


def etiqueta_curso(pl: dict, alumno) -> str:
    """Nombre corto del curso como figura en el padrón (1°A, DESP AER A, ORR B...)."""
    if pl.get("etiqueta"):
        return pl["etiqueta"]
    if pl.get("principal") and getattr(alumno, "curso", None):
        return alumno.curso
    return re.sub(r"\s*\(.*\)$", "", pl.get("nombre") or "")


def estado_con_anterior(estado: str, debe_anterior: bool, anio: int) -> str:
    """Quien está al día con el año pero debe el anterior no se muestra igual que quien no debe nada."""
    return f"Al día · debe {anio - 1}" if debe_anterior and estado in ("Al día", "Pagado") else estado


def _detalle(adeudadas: int, meses: list[int], matricula: Decimal) -> str:
    partes = []
    if matricula > 0:
        partes.append("la matrícula")
    if adeudadas:
        partes.append(f"{adeudadas} cuota{'s' if adeudadas > 1 else ''} ({_lista_meses(meses)})")
    return ("Debe " + " y ".join(partes)) if partes else ""


def estado_cuenta(alumno, planes, pagos, anio: int, hoy: date | None = None, mes_corte: int | None = None) -> dict:
    """
    planes: lista de cursos del alumno en el año (ver plan_simple); por compatibilidad también acepta
            un Curso suelto o None.
    pagos:  pagos del alumno imputables a `anio` (ver anio_de_pago).
    Vencido = cuotas cuyo vencimiento ya pasó (respecto de `hoy`); si se indica `mes_corte`
    (filtro del personal) se toman como vencidas todas las cuotas hasta ese mes inclusive.
    """
    if not isinstance(planes, list):
        planes = plan_simple(planes)
    hoy = hoy or date.today()
    cond = (alumno.condicion or "").strip().lower()
    deuda_ant = _dec(alumno.deuda_anio_anterior)
    pagos = sorted(pagos, key=lambda p: (fecha_imputacion(p), p.id or 0))
    total_pagado = sum((_dec(p.importe) for p in pagos), CERO)
    varios = len(planes) > 1

    base = {"anio": anio, "pagado": float(total_pagado), "deuda_anterior": float(deuda_ant), "items": [],
            "cuotas_adeudadas": 0, "matricula_adeudada": 0.0, "meses_adeudados": [], "detalle_deuda": "",
            "proximo": None, "saldo_a_favor": 0.0, "cuotas_pagas": 0, "cursos": []}

    exento = cond in ("becado", "exento") or bool(getattr(alumno, "cuota_excluir", False))
    if exento or not planes:
        estado = (alumno.condicion or "Exento") if exento else "Sin curso"
        base.update(esperado=0.0, deuda=0.0, deuda_total=float(deuda_ant), estado=estado,
                    pagos=[_pago_dto(p, [], anio) for p in pagos], debe_anio_anterior=deuda_ant > 0,
                    cursos=[{"clave": pl["clave"], "nombre": pl["nombre"], "etiqueta": etiqueta_curso(pl, alumno),
                             "area": getattr(pl["curso"], "area", None), "curso_id": pl.get("curso_id"),
                             "principal": bool(pl.get("principal")), "estado": estado, "cobrado": float(total_pagado) if i == 0 else 0.0,
                             "esperado_anual": 0.0, "deuda": 0.0, "items": []} for i, pl in enumerate(planes)])
        return base

    def vencido(mes: int) -> bool:
        return mes <= mes_corte if mes_corte is not None else fin_de_mes(anio, mes) < hoy

    # Cuotas de cada curso
    items = []
    for orden, pl in enumerate(planes):
        c = pl["curso"]
        cuota = _dec(getattr(alumno, "cuota_personalizada", None) if pl.get("principal") and getattr(alumno, "cuota_personalizada", None) else c.cuota)
        matricula = _dec(c.matricula)
        inicio = max(1, min(12, int(pl.get("mes_inicio") or MES_INICIO)))
        n = max(0, min(int(c.n_cuotas or 0), 12 - inicio + 1))
        pl["_cuota"], pl["_matricula"], pl["_n"], pl["_orden"] = cuota, matricula, n, orden
        sufijo = f" ({pl['nombre']})" if varios else ""
        if matricula > 0:
            items.append({"plan": pl["clave"], "orden": orden, "clave": "matricula", "concepto": "Matrícula" + sufijo,
                          "mes": inicio, "importe": matricula, "pagado": CERO, "es_matricula": True})
        for i in range(n):
            mes = inicio + i
            items.append({"plan": pl["clave"], "orden": orden, "clave": f"cuota-{mes}",
                          "concepto": (f"Cuota de {MESES[mes - 1]}" if n > 1 else "Cuota") + sufijo,
                          "mes": mes, "importe": cuota, "pagado": CERO, "es_matricula": False})
    # Orden de antigüedad: por mes; dentro del mes, matrícula antes que cuota; y por orden de curso
    items.sort(key=lambda it: (it["mes"], 0 if it["es_matricula"] else 1, it["orden"]))
    plan_por_curso = {pl.get("curso_id"): pl["clave"] for pl in planes if pl.get("curso_id")}

    def aplicar(it, monto: Decimal, destino: list, p) -> Decimal:
        falta = it["importe"] - it["pagado"]
        if monto <= 0 or falta <= 0:
            return monto
        usa = min(falta, monto)
        it["pagado"] += usa
        # qué pago la cubrió, con su fecha de proceso y el mes en que se pagó
        it.setdefault("pagos", []).append({"id": p.id, "fecha": str(p.fecha), "importe": float(usa),
                                           "mes_pago": _mes_relativo(fecha_imputacion(p), anio)})
        destino.append({"concepto": it["concepto"], "mes": it["mes"], "importe": usa, "plan": it["plan"],
                        "tipo": "matricula" if it["es_matricula"] else "cuota"})
        return monto - usa

    # Matrícula del año ya pagada por fuera (p. ej. abonada en el año anterior)
    if getattr(alumno, "matricula_paga", False):
        for it in items:
            if it["es_matricula"] and it["plan"] == planes[0]["clave"]:
                it["pagado"] = it["importe"]
                it["prepago"] = it["importe"]  # cubierta, pero no es plata cobrada este año

    imputaciones = []
    a_favor = CERO
    ant_saldo = deuda_ant  # deuda del año anterior que todavía queda
    for p in pagos:
        resto, destino = _dec(p.importe), []
        f = fecha_imputacion(p)
        forzado = plan_por_curso.get(getattr(p, "curso_id", None))
        candidatos = [it for it in items if not forzado or it["plan"] == forzado]
        # 0) la matrícula se reconoce por su monto
        mat = next((it for it in candidatos if it["es_matricula"] and resto > 0 and it["importe"] - it["pagado"] == resto), None)
        if mat:
            resto = aplicar(mat, resto, destino, p)
        if resto > 0 and f.year == anio:  # 1) la cuota del mes en que pagó (si hay de varios cursos, la del importe pagado)
            propias = [it for it in candidatos if it["clave"] == f"cuota-{f.month}" and it["importe"] > it["pagado"]]
            if propias:
                exacta = next((it for it in propias if it["importe"] - it["pagado"] == resto), None)
                resto = aplicar(exacta or propias[0], resto, destino, p)
        for it in candidatos:  # 2) lo más viejo que ya venció
            if resto <= 0:
                break
            if vencido(it["mes"]):
                resto = aplicar(it, resto, destino, p)
        if resto > 0 and ant_saldo > 0 and not forzado:  # 3) deuda del año anterior
            usa = min(resto, ant_saldo)
            ant_saldo -= usa
            resto -= usa
            destino.append({"concepto": f"Deuda {anio - 1}", "importe": usa, "tipo": "deuda_anterior"})
        for it in candidatos:  # 4) adelanto de cuotas que todavía no vencieron
            if resto <= 0:
                break
            resto = aplicar(it, resto, destino, p)
        if resto > 0:
            a_favor += resto
            destino.append({"concepto": "Saldo a favor", "importe": resto, "tipo": "a_favor"})
        imputaciones.append(_pago_dto(p, destino, anio))

    # Resumen general y por curso
    tot = {"esperado": CERO, "deuda": CERO, "adeudadas": 0, "matricula": CERO}
    meses_gral, proximo, salida = [], None, []
    por_plan = {pl["clave"]: {"esperado": CERO, "deuda": CERO, "adeudadas": 0, "meses": [], "matricula": CERO,
                              "items": [], "proximo": None} for pl in planes}
    for it in items:
        saldo = it["importe"] - it["pagado"]
        venc = fin_de_mes(anio, it["mes"])
        es_vencido = vencido(it["mes"])
        pp = por_plan[it["plan"]]
        if saldo <= 0:
            est = "pagada"
        elif es_vencido:
            est = "parcial" if it["pagado"] > 0 else "adeudada"
        else:
            est = "a_vencer"
        if es_vencido:
            pp["esperado"] += it["importe"]
            if saldo > 0:
                pp["deuda"] += saldo
                if it["es_matricula"]:
                    pp["matricula"] += saldo
                else:
                    pp["adeudadas"] += 1
                    pp["meses"].append(it["mes"])
        elif saldo > 0:
            prox = {"concepto": it["concepto"], "vence": venc.isoformat(), "importe": float(saldo)}
            if pp["proximo"] is None:
                pp["proximo"] = prox
            if proximo is None:
                proximo = prox
        pagos_it = it.get("pagos", [])
        dto = {"concepto": it["concepto"], "mes": it["mes"], "vence": venc.isoformat(), "importe": float(it["importe"]),
               "pagado": float(it["pagado"]), "saldo": float(max(saldo, CERO)), "estado": est, "vencida": es_vencido,
               "curso": next(pl["nombre"] for pl in planes if pl["clave"] == it["plan"]), "plan": it["plan"],
               "es_matricula": it["es_matricula"],
               # pagos que la cubrieron (fecha de proceso) y si se pagó después de su mes
               "pagos": [{k: v for k, v in x.items() if k != "mes_pago"} for x in pagos_it],
               "pagada_el": pagos_it[-1]["fecha"] if pagos_it and saldo <= 0 else None,
               "con_atraso": any(x["mes_pago"] > it["mes"] for x in pagos_it),
               "prepaga": bool(it.get("prepago"))}
        salida.append(dto)
        pp["items"].append(dto)

    cursos = []
    for pl in planes:
        pp = por_plan[pl["clave"]]
        tot["esperado"] += pp["esperado"]; tot["deuda"] += pp["deuda"]
        tot["adeudadas"] += pp["adeudadas"]; tot["matricula"] += pp["matricula"]
        meses_gral += [(m, pl["nombre"]) for m in pp["meses"]]
        esperado_anual = sum((it["importe"] for it in items if it["plan"] == pl["clave"]), CERO)
        cobrado = sum((it["pagado"] - it.get("prepago", CERO) for it in items if it["plan"] == pl["clave"]), CERO)
        if pl is planes[0]:  # lo que fue a deuda anterior o quedó a favor se cuenta en el curso principal
            cobrado += (deuda_ant - ant_saldo) + a_favor
        completo = all(it["pagado"] >= it["importe"] for it in items if it["plan"] == pl["clave"])
        est_plan = ("Moroso" if cobrado > 0 else "Sin pagos") if pp["deuda"] > 0 else ("Pagado" if completo else "Al día")
        cursos.append({"clave": pl["clave"], "nombre": pl["nombre"], "curso_id": pl.get("curso_id"),
                       "etiqueta": etiqueta_curso(pl, alumno), "area": getattr(pl["curso"], "area", None),
                       "esperado_anual": float(esperado_anual), "cobrado": float(cobrado), "completo": completo,
                       "principal": bool(pl.get("principal")), "mes_inicio": pl.get("mes_inicio") or MES_INICIO,
                       "cuota": float(pl["_cuota"]), "matricula": float(pl["_matricula"]), "n_cuotas": pl["_n"],
                       "esperado": float(pp["esperado"]), "deuda": float(pp["deuda"]), "cuotas_adeudadas": pp["adeudadas"],
                       "matricula_adeudada": float(pp["matricula"]), "meses_adeudados": [MESES[m - 1] for m in pp["meses"]],
                       "detalle_deuda": _detalle(pp["adeudadas"], pp["meses"], pp["matricula"]),
                       "estado": est_plan, "proximo": pp["proximo"], "items": pp["items"]})

    if varios:
        detalle = " · ".join(f"{c['nombre']}: {c['detalle_deuda'][0].lower()}{c['detalle_deuda'][1:]}" for c in cursos if c["detalle_deuda"])
        meses_txt = [f"{MESES[m - 1]} ({nombre})" for m, nombre in meses_gral]
    else:
        detalle = cursos[0]["detalle_deuda"]
        meses_txt = cursos[0]["meses_adeudados"]

    if tot["deuda"] <= 0:
        estado = "Pagado" if all(c["completo"] for c in cursos) else "Al día"  # Pagado = año (o curso) completo
    elif total_pagado <= 0:
        estado = "Sin pagos"
    else:
        estado = "Moroso"
    estado = estado_con_anterior(estado, ant_saldo > 0, anio)

    principal = cursos[0]
    base.update(
        esperado=float(tot["esperado"]), deuda=float(tot["deuda"]), deuda_total=float(tot["deuda"] + ant_saldo), estado=estado,
        deuda_anterior=float(ant_saldo), deuda_anterior_original=float(deuda_ant), debe_anio_anterior=ant_saldo > 0,
        imputado_deuda_anterior=float(deuda_ant - ant_saldo),
        items=salida, cuotas_adeudadas=tot["adeudadas"], matricula_adeudada=float(tot["matricula"]),
        meses_adeudados=meses_txt, detalle_deuda=detalle, proximo=proximo, saldo_a_favor=float(a_favor),
        cuotas_pagas=sum(1 for s in salida if s["estado"] == "pagada" and not s["es_matricula"]),
        pagos=imputaciones, cuota=principal["cuota"], matricula=principal["matricula"], n_cuotas=principal["n_cuotas"],
        cursos=cursos,
    )
    return base


def _mes_relativo(f: date, anio: int) -> int:
    """Mes de una fecha respecto del año de la cuenta (13 = año siguiente, 0 = año anterior)."""
    return f.month if f.year == anio else (13 if f.year > anio else 0)


def _pago_dto(p, destino: list, anio: int | None = None) -> dict:
    """Un pago con el detalle de qué cubrió: cada cuota en su renglón, marcando las atrasadas (cuotas de
    meses anteriores al del pago) y los adelantos."""
    mes_pago = _mes_relativo(fecha_imputacion(p), anio) if anio else None
    detalle: dict = {}
    for d in destino:  # una misma cuota cubierta en dos pasos va en un solo renglón
        k = (d["concepto"], d.get("plan"))
        if k in detalle:
            detalle[k]["importe"] += d["importe"]
        else:
            detalle[k] = dict(d)
    lineas = []
    for d in detalle.values():
        mes = d.get("mes")
        lineas.append({"concepto": d["concepto"], "importe": float(d["importe"]), "tipo": d["tipo"], "mes": mes,
                       "atrasada": d["tipo"] == "deuda_anterior" or (mes is not None and mes_pago is not None and mes < mes_pago),
                       "adelanto": mes is not None and mes_pago is not None and mes > mes_pago})
    return {"id": p.id, "fecha": str(p.fecha), "fecha_pago": str(p.fecha_pago) if p.fecha_pago else None,
            "importe": float(p.importe), "canal": p.canal, "via": p.via, "curso_id": getattr(p, "curso_id", None),
            "imputado_a": ", ".join(x["concepto"] for x in lineas) or None, "detalle": lineas}
