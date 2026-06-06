# -*- coding: utf-8 -*-
"""Informe institucional EXTENSO de APAI Pay - autor Carlos Cambareri (sin logo APAI)."""
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
from datetime import datetime

CAP = r"C:\Users\Carlos\proyectos\pagos-cashless\scripts\capturas"
SALIDA = r"C:\Users\Carlos\Desktop\APAI_Pay_Informe.pdf"

NAVY = (21, 35, 59)
NAVY2 = (31, 51, 84)
RED = (160, 30, 34)
SKY = (61, 127, 196)
GRAY = (90, 100, 120)
LIGHT = (238, 242, 247)
LINE = (210, 220, 232)

PAGE_H = 297
MARGIN_B = 16


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 16, "F")
        self.set_fill_color(*RED)
        self.rect(0, 16, 210, 1.1, "F")
        self.set_xy(14, 4.5)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, "APAI Pay", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(150, 5.5)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(180, 195, 215)
        self.cell(46, 5, "Informe de funcionalidades", align="R")
        self.set_y(24)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*GRAY)
        self.cell(0, 6, "APAI Pay  -  Elaborado por Carlos Cambareri", align="L")
        self.set_y(-12)
        self.cell(0, 6, f"Pagina {self.page_no() - 1}", align="R")


def titulo(pdf, texto):
    if pdf.get_y() > PAGE_H - 45:
        pdf.add_page()
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "  " + texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.set_fill_color(*RED)
    pdf.rect(14, pdf.get_y(), 40, 0.8, "F")
    pdf.ln(4)


def subt(pdf, texto):
    if pdf.get_y() > PAGE_H - 30:
        pdf.add_page()
    pdf.set_text_color(*RED)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, texto, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(0.5)


def parrafo(pdf, texto, size=10.5):
    pdf.set_text_color(40, 45, 55)
    pdf.set_font("Helvetica", "", size)
    pdf.multi_cell(0, 5.4, texto)
    pdf.ln(1.6)


def bullet(pdf, texto):
    if pdf.get_y() > PAGE_H - 22:
        pdf.add_page()
    y0 = pdf.get_y()
    pdf.set_fill_color(*SKY)
    pdf.ellipse(16, y0 + 1.7, 1.8, 1.8, "F")
    pdf.set_x(21)
    pdf.set_text_color(55, 60, 70)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(175, 5, texto)
    pdf.ln(0.6)


def vinheta(pdf, tit, texto):
    if pdf.get_y() > PAGE_H - 28:
        pdf.add_page()
    y0 = pdf.get_y()
    pdf.set_fill_color(*RED)
    pdf.rect(14, y0 + 1.2, 2.2, 4, "F")
    pdf.set_x(19)
    pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(0, 6, tit, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(19)
    pdf.set_text_color(55, 60, 70)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(176, 5.2, texto)
    pdf.ln(1.6)


def imagen(pdf, nombre, caption=None):
    ruta = f"{CAP}\\{nombre}"
    iw, ih = Image.open(ruta).size
    w = 182.0
    h = w * ih / iw
    if pdf.get_y() + h + 8 > PAGE_H - MARGIN_B:
        pdf.add_page()
    x, y = 14, pdf.get_y()
    pdf.image(ruta, x=x, y=y, w=w)
    pdf.set_draw_color(*LINE)
    pdf.rect(x, y, w, h)
    pdf.set_y(y + h + 2)
    if caption:
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*GRAY)
        pdf.cell(0, 5, caption, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)


pdf = PDF(format="A4", unit="mm")
pdf.set_auto_page_break(auto=True, margin=MARGIN_B)
pdf.set_margins(14, 24, 14)

# ===================== PORTADA =====================
pdf.add_page()
pdf.set_fill_color(*NAVY)
pdf.rect(0, 0, 210, 297, "F")
pdf.set_fill_color(*NAVY2)
pdf.rect(0, 96, 210, 74, "F")
pdf.set_fill_color(*RED)
pdf.rect(0, 96, 210, 2, "F")
pdf.set_xy(0, 110)
pdf.set_font("Helvetica", "B", 42)
pdf.set_text_color(255, 255, 255)
pdf.cell(210, 16, "APAI Pay", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_xy(0, 134)
pdf.set_font("Helvetica", "", 13.5)
pdf.set_text_color(150, 180, 215)
pdf.cell(210, 8, "Plataforma de pagos, cuotas y cobranzas para el colegio", align="C")
pdf.set_xy(0, 150)
pdf.set_font("Helvetica", "", 10.5)
pdf.set_text_color(150, 180, 215)
pdf.cell(210, 6, "Informe completo de funcionalidades", align="C")
meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
hoy = datetime.now()
pdf.set_xy(0, 262)
pdf.set_font("Helvetica", "B", 12)
pdf.set_text_color(255, 255, 255)
pdf.cell(210, 7, "Carlos Cambareri", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_x(0)
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(140, 155, 180)
pdf.cell(210, 6, f"{hoy.day} de {meses[hoy.month-1]} de {hoy.year}", align="C")

# ===================== 1. RESUMEN =====================
pdf.add_page()
titulo(pdf, "1.  Que es APAI Pay")
parrafo(pdf,
    "APAI Pay es una plataforma integral, desarrollada a medida, que administra de punta a punta el dinero "
    "del colegio. Reune en un solo sistema cuatro funciones que hoy se hacen por separado y de forma manual: "
    "el cobro sin efectivo en los puntos de venta, la carga de saldo de los alumnos, la gestion de la cuota "
    "societaria (un aporte voluntario de las familias) y el envio de cupones de pago.")
parrafo(pdf,
    "Cada alumno tiene una tarjeta personal (la ApaiCard) con la que paga sus consumos -por ejemplo en la "
    "fotocopiadora- simplemente apoyandola en un lector. El saldo no viaja en la tarjeta sino que se guarda "
    "de forma segura en la nube, lo que lo hace imposible de adulterar. Los padres cargan ese saldo y abonan "
    "la cuota a traves de cupones que el sistema genera y envia automaticamente por correo electronico. "
    "Cada operacion queda registrada en el instante, y la plataforma ofrece reportes y estadisticas en "
    "tiempo real para controlar todo lo que ocurre.")
subt(pdf, "En una frase")
parrafo(pdf,
    "APAI Pay reemplaza el efectivo, las planillas sueltas y el seguimiento manual de cuotas por un sistema "
    "unico, ordenado, seguro y disponible las 24 horas desde cualquier computadora.")
subt(pdf, "Todo lo que incluye")
bullet(pdf, "Cobro sin efectivo con tarjeta RFID en los puntos de venta.")
bullet(pdf, "Saldo de cada alumno almacenado de forma segura en la nube.")
bullet(pdf, "Registro completo de alumnos con su historial de movimientos.")
bullet(pdf, "Clasificacion de alumnos por area: Ciclo Basico, Avionica y Mecanica.")
bullet(pdf, "Recargas de saldo, reintegros en efectivo y transferencias de saldo entre alumnos.")
bullet(pdf, "Envio masivo de cupones de la cuota societaria (aporte voluntario de las familias).")
bullet(pdf, "Cobranza online integrada con SIRO (Banco Roela).")
bullet(pdf, "Envio automatico de cupones por email con plantillas editables.")
bullet(pdf, "Reportes, estadisticas y graficos en tiempo real.")
bullet(pdf, "Exportacion a Excel y comprobantes en PDF para las familias.")
bullet(pdf, "Acceso protegido con usuarios, backup automatico y costo operativo cero.")

# ===================== 2. EL PROBLEMA =====================
titulo(pdf, "2.  Los problemas que resuelve")
parrafo(pdf,
    "La administracion de APAI maneja todos los dias dinero en efectivo, cobros de cuota de cientos de "
    "familias e informacion repartida en multiples planillas. Eso genera trabajo, riesgo y falta de "
    "control. APAI Pay ataca cada uno de esos puntos.")
vinheta(pdf, "El manejo de efectivo",
        "Los alumnos llevan dinero que se pierde, se extravia o se gasta en otra cosa. En los puntos de venta hay que cuidar la plata, dar vuelto y cuadrar caja. Con la tarjeta, el efectivo desaparece del circuito diario.")
vinheta(pdf, "El envio y seguimiento de la cuota",
        "Enviar y controlar los cupones de la cuota (voluntaria) de cientos de familias es un trabajo manual enorme y propenso a errores. APAI Pay lo hace en pocos clics, mes a mes, completando el nombre del mes automaticamente.")
vinheta(pdf, "La falta de control y transparencia",
        "Hoy es dificil saber con exactitud cuanto se vendio, cuanto se cobro y quien hizo cada operacion. El sistema registra todo con fecha, hora, monto y operador, y lo informa al instante.")
vinheta(pdf, "La informacion dispersa",
        "Los datos de alumnos, pagos y saldos viven en planillas separadas. La plataforma centraliza todo en un solo lugar, ordenado, respaldado y accesible desde cualquier equipo.")
vinheta(pdf, "El riesgo de perdida de datos",
        "Una planilla se puede borrar o corromper. APAI Pay hace una copia de seguridad completa todos los dias de forma automatica.")

# ===================== 3. EL DINERO =====================
titulo(pdf, "3.  El dinero: donde esta y como se mueve")
parrafo(pdf,
    "Una duda habitual y muy logica es: si el alumno paga con la tarjeta, donde esta realmente la plata? "
    "La respuesta es simple y tranquilizadora: el dinero siempre esta en la cuenta bancaria de APAI. "
    "El saldo de la tarjeta es solamente un numero en el sistema que representa lo que la familia ya pago. "
    "No hay dinero guardado 'adentro' de la tarjeta.")
subt(pdf, "El recorrido del dinero")
bullet(pdf, "La familia paga por el banco (con el cupon o por transferencia). Ese dinero real entra a la cuenta de APAI.")
bullet(pdf, "APAI carga en la tarjeta del alumno un saldo igual a lo que pago. Es un numero en el sistema, no billetes en la tarjeta.")
bullet(pdf, "El alumno usa la tarjeta y ese numero va bajando con cada compra. El dinero real ya estaba en el banco desde el primer paso.")
bullet(pdf, "Si en algun caso se devuelve saldo (reintegro), recien ahi sale dinero real de la cuenta.")
subt(pdf, "Una comparacion facil")
parrafo(pdf,
    "Funciona igual que una tarjeta de regalo o la tarjeta SUBE: uno carga un monto y despues lo va usando. "
    "La plata no esta en el plastico; el plastico solo sirve para identificar de quien es el saldo. El dinero "
    "esta respaldado y guardado de forma segura en el banco.")
subt(pdf, "Por que es seguro")
bullet(pdf, "El saldo no se guarda en la tarjeta, asi que nadie puede 'fabricar' plata copiando una tarjeta.")
bullet(pdf, "Cada peso de saldo esta respaldado por dinero real que entro al banco.")
bullet(pdf, "El reporte 'Saldo total en el sistema' muestra en todo momento cuanta plata de las familias falta consumir.")
pdf.set_fill_color(*LIGHT)
pdf.set_text_color(*NAVY)
pdf.set_font("Helvetica", "B", 10)
pdf.multi_cell(0, 6,
    "  En resumen: el saldo de las tarjetas es dinero real de las familias, ya cobrado y guardado en el "
    "banco. Se convierte en ingreso de APAI recien cuando el alumno consume su saldo.", fill=True)
pdf.ln(3)

# ===================== 4. COBRO =====================
titulo(pdf, "4.  Cobro sin efectivo con la ApaiCard")
parrafo(pdf,
    "Es el corazon del uso diario. En la fotocopiadora o en cualquier punto de venta, el operador identifica "
    "al alumno y le descuenta el importe de su saldo en el momento. Es rapido, no requiere efectivo y queda "
    "registrado automaticamente.")
subt(pdf, "Como se cobra")
bullet(pdf, "Se apoya la tarjeta del alumno en un lector USB que escribe su numero al instante; o se busca al alumno por apellido, nombre, legajo o DNI.")
bullet(pdf, "El sistema muestra los datos del alumno, su curso/area y el saldo disponible.")
bullet(pdf, "El operador ingresa el monto (con botones de importes frecuentes para ir mas rapido) y, si quiere, una descripcion del consumo.")
bullet(pdf, "Al confirmar, el saldo se descuenta y la venta queda registrada con el nombre del operador.")
subt(pdf, "Controles automaticos")
bullet(pdf, "Si el alumno no tiene saldo suficiente, el sistema avisa y no permite el cobro.")
bullet(pdf, "Si la tarjeta esta dada de baja o el alumno inactivo, tambien lo informa.")
subt(pdf, "Saldo seguro en la nube")
parrafo(pdf,
    "Una decision clave de diseno: el dinero nunca se guarda en la tarjeta -que podria copiarse o clonarse- "
    "sino en el servidor. La tarjeta solo identifica al alumno. Asi, aunque alguien duplicara una tarjeta, "
    "no podria 'fabricar' saldo. Y si un alumno pierde la tarjeta, se da de baja la anterior y se emite una "
    "nueva: el saldo se conserva intacto porque estaba en la nube.")
imagen(pdf, "cobro.png", "Pantalla de cobro: identificacion del alumno y descuento del saldo en el momento.")

# ===================== 4. ALUMNOS =====================
titulo(pdf, "5.  Registro y gestion de alumnos")
parrafo(pdf,
    "La plataforma administra el padron completo de alumnos. De cada uno guarda: legajo, DNI, nombre, "
    "apellido, curso, area, email de la familia, saldo actual y su codigo de cliente para la cobranza. "
    "Hay mas de 600 alumnos reales ya cargados y clasificados.")
subt(pdf, "Alta, edicion y baja")
bullet(pdf, "Alta de un alumno nuevo con todos sus datos en un formulario simple.")
bullet(pdf, "Edicion de los datos de cualquier alumno en cualquier momento (corregir nombre, curso, email, area, etc.).")
bullet(pdf, "Baja de un alumno cuando deja el colegio, con su informacion asociada.")
subt(pdf, "Busqueda y orden")
bullet(pdf, "Buscador que filtra a medida que se escribe por nombre, apellido, legajo o DNI.")
bullet(pdf, "Filtro por curso y ordenamiento por cualquier columna (legajo, apellido, curso, area, saldo) con un clic.")
subt(pdf, "Ficha del alumno con su historial")
parrafo(pdf,
    "Al abrir la ficha de un alumno se ve, en una sola pantalla: sus datos personales, el area, el email, "
    "su codigo de cliente, el saldo actual, las tarjetas que tiene asignadas (activas e inactivas) y el "
    "detalle de sus ultimos movimientos (fecha, tipo de operacion, monto y descripcion). Desde ahi tambien "
    "se puede generar el comprobante PDF de movimientos para enviar a la familia.")
subt(pdf, "Datos especiales para la cuota")
parrafo(pdf,
    "En la ficha de cada alumno se puede marcar 'no enviarle cupon de cuota' (por ejemplo, becados o casos "
    "particulares que no deben abonar ese mes) y tambien asignarle un 'monto de cuota personalizado' "
    "distinto al general. El sistema respeta estas excepciones automaticamente en los envios masivos.")
imagen(pdf, "alumnos.png", "Padron de alumnos con clasificacion por area, saldo y acciones por alumno.")

# ===================== 5. IMPORTACION + AREAS =====================
titulo(pdf, "6.  Importacion masiva y clasificacion por areas")
subt(pdf, "Carga masiva desde Excel")
parrafo(pdf,
    "En lugar de cargar a los alumnos uno por uno, se sube una planilla de Excel con las columnas legajo, "
    "DNI, nombre, apellido, curso y, opcionalmente, el email (columna Mail) y el area. El sistema da de alta "
    "a cientos de alumnos en segundos. Si un alumno ya existe, no lo duplica: actualiza su email y su area. "
    "Es ideal al inicio del ciclo lectivo o para sumar a los ingresantes.")
subt(pdf, "Tres areas")
parrafo(pdf,
    "Cada alumno pertenece a una de las tres areas del colegio: Ciclo Basico, Avionica o Mecanica. El sistema "
    "las reconoce automaticamente a partir del curso, de modo que los mas de 600 alumnos ya quedaron "
    "clasificados sin trabajo manual. El area se usa para enviar cupones segmentados y para los reportes.")

# ===================== 6. TARJETAS =====================
titulo(pdf, "7.  Gestion de tarjetas")
parrafo(pdf,
    "Las tarjetas RFID son la llave de identificacion del alumno. El sistema permite administrarlas por "
    "completo.")
vinheta(pdf, "Emision de tarjetas",
        "Se asocia una tarjeta nueva a un alumno apoyandola en el lector o escribiendo su numero. Un alumno puede tener mas de una tarjeta a lo largo del tiempo.")
vinheta(pdf, "Consulta rapida",
        "Apoyando una tarjeta se ve al instante a que alumno pertenece y cuanto saldo tiene.")
vinheta(pdf, "Reposicion por perdida o robo",
        "Si se pierde una tarjeta, se desactiva para que no pueda usarse y se emite una nueva. El saldo del alumno no se pierde: queda en la nube y se asocia a la tarjeta nueva.")

# ===================== 7. OPERACIONES =====================
titulo(pdf, "8.  Operaciones de saldo")
subt(pdf, "Recarga de saldo")
parrafo(pdf,
    "Acredita el dinero que la familia abono (por cupon o transferencia) en la cuenta del alumno. Tiene un "
    "monto minimo configurable (hoy $1.000) y queda registrada con el operador que la realizo y una "
    "descripcion.")
subt(pdf, "Reintegro en efectivo")
parrafo(pdf,
    "Permite devolver saldo a un alumno cuando corresponde, con un tope de seguridad configurable (hoy "
    "$2.500) para evitar errores. Tambien queda registrado.")
subt(pdf, "Transferencia de saldo entre alumnos")
parrafo(pdf,
    "Una funcion muy util, por ejemplo entre hermanos: permite pasar saldo de la tarjeta de un alumno a la "
    "de otro. El sistema descuenta el importe del alumno de origen y lo acredita en el de destino, generando "
    "dos movimientos vinculados (uno de salida y uno de entrada) para que quede perfecta la trazabilidad de "
    "ambos. Verifica que el alumno de origen tenga saldo suficiente y que no sea la misma tarjeta.")
subt(pdf, "Todo queda asentado")
parrafo(pdf,
    "Cada recarga, reintegro, transferencia y consumo genera un movimiento con fecha y hora exactas, tipo de "
    "operacion, monto, descripcion y el operador responsable. Nada queda librado a la memoria.")

# ===================== 8. HISTORIAL =====================
titulo(pdf, "9.  Historial de movimientos")
parrafo(pdf,
    "El sistema lleva el registro de absolutamente todos los movimientos y permite consultarlos de tres "
    "formas, segun lo que se necesite ver.")
vinheta(pdf, "Ultimos movimientos del sistema",
        "Sin buscar nada, muestra los ultimos 10 movimientos de todo el colegio, con el alumno, el curso, la fecha, el tipo, el monto, la descripcion y el operador. Util para ver la actividad reciente de un vistazo.")
vinheta(pdf, "Movimientos del dia",
        "Con un boton muestra todas las operaciones realizadas en el dia, ideal para el cierre y el control diario.")
vinheta(pdf, "Historial completo de un alumno",
        "Al elegir un alumno, muestra automaticamente todo su historico de movimientos (no solo del dia), para revisar el detalle de su cuenta.")
subt(pdf, "Datos de cada movimiento")
bullet(pdf, "Fecha y hora exactas de la operacion.")
bullet(pdf, "Alumno y curso al que corresponde.")
bullet(pdf, "Tipo: consumo, recarga, reintegro, transferencia enviada o recibida.")
bullet(pdf, "Monto (positivo o negativo segun sume o reste saldo).")
bullet(pdf, "Descripcion del concepto y operador que la realizo.")

# ===================== 9. CUOTAS =====================
titulo(pdf, "10.  Cuota societaria mensual")
parrafo(pdf,
    "El modulo que convierte a APAI Pay en una herramienta de gestion completa. Permite enviar la cuota "
    "mensual (un aporte voluntario de las familias) de forma masiva, ordenada y con un minimo de trabajo.")
subt(pdf, "Envio masivo en pocos clics")
parrafo(pdf,
    "Se selecciona el area (Ciclo Basico, Avionica, Mecanica) o un curso puntual, se confirma el monto de la "
    "cuota (el que APAI defina) y el sistema genera y envia el cupon a todas las familias correspondientes. El "
    "nombre del mes en curso se completa solo en el asunto y en el texto del correo, por lo que la misma "
    "plantilla sirve todos los meses sin tener que editarla.")
subt(pdf, "Excluir a quienes no corresponde ese mes")
parrafo(pdf,
    "Cada alumno puede marcarse como excluido de la cuota. Esos alumnos quedan fuera del envio masivo "
    "automaticamente (por ejemplo, becados o casos especiales). El sistema informa cuantos quedaron "
    "excluidos en cada envio, asi se tiene el control.")
subt(pdf, "Montos distintos por alumno")
parrafo(pdf,
    "Si una familia tiene un acuerdo de un valor diferente, se le carga un monto de cuota personalizado. En "
    "el envio masivo, ese alumno recibe su importe particular y el resto el monto general, todo en la misma "
    "operacion.")
subt(pdf, "Antes de enviar se puede ver")
parrafo(pdf,
    "El contador muestra a cuantos alumnos con email se les va a enviar y cuantos estan excluidos, y la vista "
    "previa permite ver exactamente como llegara el correo a la familia. Recien despues se confirma el envio.")
imagen(pdf, "cupones.png", "Envio de la cuota del mes por area y vista previa del email que recibe la familia.")

# ===================== 10. SIRO + EMAIL =====================
titulo(pdf, "11.  Cobranza online (SIRO) y envio por email")
subt(pdf, "Cupones de pago integrados con SIRO")
parrafo(pdf,
    "La plataforma se integra con SIRO (la plataforma de cobranzas de Banco Roela) para generar cupones de "
    "pago electronico, tanto para la cuota como para las recargas de saldo. Cada cupon queda asociado al "
    "alumno mediante su codigo de cliente, de modo que el pago se identifica correctamente. Las familias "
    "pueden abonarlo por los medios habituales de SIRO (pago online, debito o en efectivo en la red de "
    "cobranzas).")
subt(pdf, "Envio automatico por correo")
parrafo(pdf,
    "El cupon llega al email de la familia con un mensaje institucional prolijo. No hay que mandar nada a "
    "mano: el sistema lo envia solo al generar la cuota o la recarga.")
subt(pdf, "Plantillas totalmente editables")
parrafo(pdf,
    "Los textos del correo (asunto y cuerpo) se editan desde el propio sistema, por separado para la cuota y "
    "para las recargas. Se pueden usar 'comodines' que el sistema reemplaza solo por los datos reales de "
    "cada familia: el nombre del alumno, el monto, el legajo, el curso, el mes y el ano. Asi cada correo "
    "sale personalizado sin esfuerzo.")

# ===================== 11. REPORTES =====================
titulo(pdf, "12.  Reportes y estadisticas")
parrafo(pdf,
    "APAI Pay no solo cobra: informa. Toda la actividad se traduce en indicadores, tablas y graficos en "
    "tiempo real, con filtros por rango de fechas, para tomar decisiones con datos y rendir cuentas con "
    "transparencia.")
subt(pdf, "Panel de indicadores (KPIs)")
bullet(pdf, "Total de recargas del periodo (monto y cantidad de operaciones).")
bullet(pdf, "Total de consumos o ventas (monto y cantidad).")
bullet(pdf, "Total de reintegros (monto y cantidad).")
bullet(pdf, "Total de transferencias entre alumnos.")
bullet(pdf, "Saldo total disponible en el sistema (la suma de todos los saldos).")
bullet(pdf, "Cantidad total de alumnos y cuantos tienen saldo cargado.")
bullet(pdf, "Ticket promedio: cuanto se gasta en promedio por venta.")
subt(pdf, "Consumo por curso y por area")
parrafo(pdf,
    "Una tabla y un grafico muestran cuanto consume cada curso: el total gastado, la cantidad de operaciones, "
    "cuantos alumnos compraron y el promedio de gasto por alumno. Permite saber con datos que curso o que area "
    "consume mas y cual menos, util para planificar compras, stock y precios.")
subt(pdf, "Tendencia diaria y ranking de alumnos")
bullet(pdf, "Grafico de la evolucion del consumo dia por dia (ultimos 30 dias) para ver picos y tendencias.")
bullet(pdf, "Ranking de los 10 alumnos que mas consumen en el periodo elegido.")
imagen(pdf, "reportes.png", "Panel de estadisticas con indicadores y consumo por curso.")

# ===================== 12. EXPORTACION =====================
titulo(pdf, "13.  Exportacion y comprobantes")
subt(pdf, "Exportacion a Excel")
parrafo(pdf,
    "Con un clic se descargan en Excel: el listado de movimientos del periodo, el padron completo de alumnos "
    "con sus saldos, el resumen general y el detalle de consumo por curso. Ideal para la contabilidad y para "
    "rendir cuentas.")
subt(pdf, "Comprobante de movimientos para las familias")
parrafo(pdf,
    "Desde la ficha de cada alumno se genera un comprobante en PDF, con membrete, que detalla sus movimientos "
    "y su saldo. Se puede compartir directamente por WhatsApp o por email para que los padres consulten el "
    "estado de la cuenta de su hijo.")
subt(pdf, "Reporte general en PDF")
parrafo(pdf,
    "El reporte completo (indicadores, consumo por curso y ranking de alumnos) se exporta en PDF con "
    "membrete, listo para presentar en una reunion de comision.")

# ===================== 13. SEGURIDAD + TECNOLOGIA =====================
titulo(pdf, "14.  Seguridad, respaldo y tecnologia")
vinheta(pdf, "Acceso protegido y multiusuario",
        "El ingreso requiere usuario y contrasena, con bloqueo automatico ante varios intentos fallidos (proteccion contra ataques) y conexion segura. Se pueden crear usuarios distintos para cada operador, de modo que quede registrado quien hizo cada cobro.")
vinheta(pdf, "Backup automatico diario",
        "Todos los dias se realiza una copia de seguridad completa de la base de datos, sin intervencion manual. Tambien se puede descargar un backup en cualquier momento.")
vinheta(pdf, "Saldo y datos en la nube",
        "La informacion vive en servidores profesionales en la nube, disponibles las 24 horas y respaldados, no en una computadora que puede fallar.")
vinheta(pdf, "Accesible desde cualquier PC, sin instalar",
        "Funciona en el navegador. Se entra desde la computadora de la oficina o cualquier equipo con internet, sin instalar programas.")
vinheta(pdf, "Costo operativo cero",
        "Esta construido sobre servicios en la nube de nivel profesional que no generan gasto mensual de servidores ni licencias para su uso.")

# ===================== 14. COMO FUNCIONA + CASOS =====================
titulo(pdf, "15.  Como funciona, paso a paso")
pasos = [
    ("1", "La familia abona", "Recibe por email el cupon de la cuota o de recarga y lo paga (online o en efectivo)."),
    ("2", "Se acredita", "El pago se registra; en las recargas, el saldo queda disponible en la ApaiCard del alumno."),
    ("3", "El alumno consume", "Apoya su tarjeta en el lector y el saldo se descuenta solo, al instante."),
    ("4", "Queda registrado", "Cada movimiento se guarda con fecha, hora, monto y operador, visible al momento."),
    ("5", "Control y reportes", "APAI consulta estadisticas, exporta a Excel y envia comprobantes a los padres."),
]
for num, t, desc in pasos:
    if pdf.get_y() > PAGE_H - 24:
        pdf.add_page()
    y0 = pdf.get_y()
    pdf.set_fill_color(*SKY)
    pdf.ellipse(15, y0, 8, 8, "F")
    pdf.set_xy(15, y0)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(8, 8, num, align="C")
    pdf.set_xy(27, y0 - 0.5)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 5, t, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(27, y0 + 4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(55, 60, 70)
    pdf.multi_cell(169, 4.8, desc)
    pdf.ln(2.5)

subt(pdf, "Casos de uso concretos")
bullet(pdf, "Un alumno compra fotocopias: apoya la tarjeta, se descuenta y listo, sin efectivo.")
bullet(pdf, "Inicio de mes: se envia la cuota de Mecanica a todas las familias del area en un clic.")
bullet(pdf, "Una familia que no aporta ese mes: se la marca como excluida y no recibe el cupon.")
bullet(pdf, "Un padre pide el detalle de gastos de su hijo: se le manda el PDF por WhatsApp.")
bullet(pdf, "Dos hermanos: se transfiere saldo de una tarjeta a la otra.")
bullet(pdf, "Fin de mes: se exporta a Excel el resumen para la contabilidad.")

# ===================== 16. CONCLUSION =====================
titulo(pdf, "16.  Por que conviene APAI Pay")
parrafo(pdf,
    "APAI Pay no es un proyecto a futuro: es un sistema ya desarrollado, probado y funcionando, con mas de "
    "600 alumnos cargados y clasificados. Esta listo para ponerse en marcha.")
vinheta(pdf, "Mas orden y transparencia",
        "Cada movimiento queda registrado de forma automatica, con fecha, hora, monto y operador. Se termina el seguimiento manual y se gana claridad para informar a la comunidad.")
vinheta(pdf, "Mas seguridad",
        "Sin efectivo circulando entre los chicos, con el saldo respaldado en el banco y los datos protegidos y respaldados todos los dias.")
vinheta(pdf, "Mas tiempo para la administracion",
        "Tareas que hoy llevan horas (enviar cupones, controlar movimientos, armar reportes) se resuelven en pocos clics.")
vinheta(pdf, "Mejor comunicacion con las familias",
        "Reciben sus cupones y comprobantes por email o WhatsApp, con la imagen de una institucion ordenada y moderna.")
vinheta(pdf, "Crece con APAI",
        "Permite sumar puntos de venta, usuarios y nuevas funciones a futuro sin rehacer nada.")

pdf.output(SALIDA)
print("PDF generado:", SALIDA)
