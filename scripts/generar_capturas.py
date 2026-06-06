# -*- coding: utf-8 -*-
"""Genera capturas de ejemplo (mockups) del sistema APAI Pay con la estetica real."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

SAL = Path(r"C:\Users\Carlos\proyectos\pagos-cashless\scripts\capturas")
SAL.mkdir(exist_ok=True)

NAVY = (21, 35, 59)
NAVY2 = (31, 51, 84)
RED = (160, 30, 34)
SKY = (61, 127, 196)
GREEN = (22, 163, 74)
AMBER = (217, 119, 6)
PURPLE = (139, 92, 246)
BG = (238, 244, 250)
CARD = (255, 255, 255)
LINE = (226, 232, 240)
GTXT = (91, 107, 128)
DARK = (28, 37, 54)
LBLUE = (234, 243, 251)
WHITE = (255, 255, 255)

F = r"C:\Windows\Fonts\arial.ttf"
FB = r"C:\Windows\Fonts\arialbd.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FB if bold else F, size)


def rrect(d, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def text(d, xy, s, f, color, anchor=None):
    d.text(xy, s, font=f, fill=color, anchor=anchor)


def header(d, w, activo="Cobrar"):
    d.rectangle([0, 0, w, 56], fill=NAVY)
    d.rectangle([0, 56, w, 59], fill=RED)
    # logo circle
    d.ellipse([16, 12, 48, 44], fill=WHITE)
    text(d, (32, 28), "AP", font(13, True), NAVY, anchor="mm")
    text(d, (60, 17), "APAI Pay", font(16, True), WHITE)
    text(d, (60, 38), "Sistema de Pagos Cashless", font(9), (155, 182, 210))
    items = ["Cobrar", "Alumnos", "Operaciones", "Tarjetas", "Reportes", "Importar"]
    x = 250
    for it in items:
        wn = d.textlength(it, font=font(11))
        if it == activo:
            rrect(d, [x - 10, 18, x + wn + 10, 40], 7, RED)
            text(d, (x, 23), it, font(11), WHITE)
        else:
            text(d, (x, 23), it, font(11), (195, 210, 230))
        x += wn + 26
    text(d, (w - 150, 24), "Carlos Cambareri", font(10), (174, 191, 214))


def guardar(img, nombre):
    img.save(SAL / nombre)
    print("OK", nombre)


# ============ 1. COBRO ============
def cap_cobro():
    w, h = 1100, 560
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    header(d, w, "Cobrar")

    # Card izquierda
    rrect(d, [30, 90, 540, 520], 12, CARD)
    text(d, (52, 108), "1. Identificar alumno", font(15, True), NAVY)
    text(d, (52, 142), "UID de tarjeta", font(10), GTXT)
    rrect(d, [52, 162, 400, 196], 8, (247, 249, 252), LINE, 1)
    text(d, (66, 172), "Escanear tarjeta o escribir UID...", font(10), (150, 165, 185))
    rrect(d, [410, 162, 518, 196], 8, SKY)
    text(d, (464, 179), "Buscar", font(11, True), WHITE, anchor="mm")

    # alumno seleccionado
    rrect(d, [52, 230, 518, 360], 10, CARD, LINE, 1)
    d.rectangle([52, 230, 57, 360], fill=SKY)
    text(d, (74, 250), "GONZALEZ, Mateo", font(18, True), NAVY)
    rrect(d, [74, 284, 230, 308], 6, LBLUE)
    text(d, (152, 296), "4°A Aviónica", font(10, True), SKY, anchor="mm")
    text(d, (360, 250), "SALDO DISPONIBLE", font(8), GTXT)
    text(d, (360, 266), "$3.250,00", font(22, True), GREEN)
    text(d, (74, 326), "Legajo: 90011  (datos de ejemplo)", font(10), GTXT)

    # Card derecha (cobrar)
    rrect(d, [560, 90, 1070, 520], 12, CARD)
    text(d, (582, 108), "2. Cobrar", font(15, True), NAVY)
    montos = ["$50", "$100", "$150", "$200", "$500"]
    x = 582
    for m in montos:
        rrect(d, [x, 142, x + 86, 184], 8, (241, 245, 249), LINE, 2)
        text(d, (x + 43, 163), m, font(12, True), DARK, anchor="mm")
        x += 96
    text(d, (582, 206), "Monto ($)", font(10), GTXT)
    rrect(d, [582, 226, 1048, 262], 8, (247, 249, 252), LINE, 1)
    text(d, (596, 236), "150,00", font(12), DARK)
    text(d, (582, 282), "Descripción (opcional)", font(10), GTXT)
    rrect(d, [582, 302, 1048, 338], 8, (247, 249, 252), LINE, 1)
    text(d, (596, 312), "Fotocopias x10", font(11), (150, 165, 185))
    rrect(d, [582, 372, 1048, 430], 10, GREEN)
    text(d, (815, 401), "COBRAR", font(20, True), WHITE, anchor="mm")
    guardar(img, "cobro.png")


# ============ 2. ALUMNOS ============
def cap_alumnos():
    w, h = 1100, 540
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    header(d, w, "Alumnos")

    # toolbar
    rrect(d, [30, 84, 720, 120], 8, CARD, LINE, 1)
    text(d, (46, 95), "Buscar por nombre, apellido, legajo o DNI...", font(11), (150, 165, 185))
    rrect(d, [735, 84, 880, 120], 8, CARD, LINE, 1)
    text(d, (752, 95), "Todos los cursos", font(11), DARK)
    rrect(d, [895, 84, 1070, 120], 8, SKY)
    text(d, (982, 102), "+ Nuevo Alumno", font(11, True), WHITE, anchor="mm")

    # tabla
    cols = ["LEGAJO", "DNI", "APELLIDO", "NOMBRE", "CURSO", "ÁREA", "SALDO"]
    xs = [40, 140, 250, 430, 590, 760, 940]
    y = 140
    d.rectangle([30, y, 1070, y + 34], fill=NAVY)
    for c, x in zip(cols, xs):
        text(d, (x, y + 10), c, font(9, True), (205, 217, 234))
    rows = [
        ("90011", "45111222", "GONZALEZ", "Mateo", "4°A", "Aviónica", "$3.250,00", GREEN),
        ("90012", "45222333", "LOPEZ", "Sofía", "1°A", "Ciclo Básico", "$1.800,00", GREEN),
        ("90013", "45333444", "MARTINEZ", "Bruno", "6°B", "Mecánica", "$520,00", GREEN),
        ("90014", "45444555", "FERNANDEZ", "Lucía", "5°A", "Aviónica", "$0,00", (150, 165, 185)),
        ("90015", "45555666", "RODRIGUEZ", "Tomás", "2°C", "Ciclo Básico", "$2.100,00", GREEN),
        ("90016", "45666777", "SANCHEZ", "Valentina", "7°A", "Mecánica", "$640,00", GREEN),
        ("90017", "45777888", "ROMERO", "Juan", "3°B", "Ciclo Básico", "$980,00", GREEN),
    ]
    y += 34
    for i, r in enumerate(rows):
        if i % 2 == 0:
            d.rectangle([30, y, 1070, y + 36], fill=(247, 249, 252))
        vals = r[:7]
        col = r[7]
        for j, (v, x) in enumerate(zip(vals, xs)):
            c = col if j == 6 else DARK
            fnt = font(10, j == 6)
            text(d, (x, y + 11), v, fnt, c)
        d.line([30, y + 36, 1070, y + 36], fill=LINE)
        y += 36
    guardar(img, "alumnos.png")


# ============ 3. REPORTES ============
def cap_reportes():
    w, h = 1100, 560
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    header(d, w, "Reportes")

    kpis = [
        ("RECARGAS", "$1.240.000", "84 operaciones", GREEN),
        ("CONSUMOS (VENTAS)", "$386.500", "612 ventas", RED),
        ("TICKET PROMEDIO", "$631", "por venta", NAVY),
        ("SALDO EN SISTEMA", "$853.500", "318 con saldo", SKY),
    ]
    x = 30
    for label, val, sub, col in kpis:
        rrect(d, [x, 84, x + 252, 168], 10, CARD)
        d.rectangle([x, 84, x + 5, 168], fill=col)
        text(d, (x + 22, 100), label, font(8, True), GTXT)
        text(d, (x + 22, 118), val, font(20, True), NAVY)
        text(d, (x + 22, 148), sub, font(9), (150, 165, 185))
        x += 262

    # grafico barras consumo por curso
    rrect(d, [30, 184, 1070, 520], 12, CARD)
    text(d, (52, 202), "Consumo por curso", font(14, True), NAVY)
    datos = [("4°A Avi", 0.95), ("6°B Mec", 0.78), ("5°A Avi", 0.66), ("7°A Mec", 0.6),
             ("2°C CB", 0.52), ("1°A CB", 0.44), ("3°B CB", 0.4), ("5°B Mec", 0.3)]
    base_y = 470
    bx = 90
    maxh = 210
    for nombre, v in datos:
        bh = int(maxh * v)
        rrect(d, [bx, base_y - bh, bx + 78, base_y], 6, SKY)
        text(d, (bx + 39, base_y + 8), nombre, font(9), GTXT, anchor="ma")
        text(d, (bx + 39, base_y - bh - 16), f"${int(v*420)}k", font(9, True), NAVY, anchor="ma")
        bx += 120
    guardar(img, "reportes.png")


# ============ 4. CUPONES + EMAIL ============
def cap_cupones():
    w, h = 1100, 600
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    header(d, w, "Operaciones")

    rrect(d, [30, 84, 1070, 330], 12, CARD)
    text(d, (52, 102), "Cupones APAI Pay (cuota y recarga)", font(15, True), NAVY)
    rrect(d, [52, 134, 190, 166], 7, SKY)
    text(d, (121, 150), "Cuota del mes", font(10, True), WHITE, anchor="mm")
    rrect(d, [200, 134, 340, 166], 7, (241, 245, 249), LINE, 1)
    text(d, (270, 150), "Recarga ApaiCard", font(10), DARK, anchor="mm")
    rrect(d, [770, 134, 900, 166], 7, CARD, SKY, 1)
    text(d, (835, 150), "Vista previa", font(10), SKY, anchor="mm")
    rrect(d, [910, 134, 1050, 166], 7, CARD, SKY, 1)
    text(d, (980, 150), "Editar plantillas", font(10), SKY, anchor="mm")

    text(d, (52, 196), "Área a enviar", font(10), GTXT)
    rrect(d, [52, 216, 300, 250], 8, (247, 249, 252), LINE, 1)
    text(d, (66, 226), "Mecánica", font(11), DARK)
    text(d, (330, 196), "Monto de la cuota ($)", font(10), GTXT)
    rrect(d, [330, 216, 560, 250], 8, (247, 249, 252), LINE, 1)
    text(d, (344, 226), "45000", font(11), DARK)
    text(d, (600, 210), "Cuota de junio · 178 con email · 4 excluidos", font(10), GTXT)
    rrect(d, [600, 232, 1050, 286], 10, RED)
    text(d, (825, 259), "Enviar cuota del mes", font(13, True), WHITE, anchor="mm")

    # Vista previa email
    text(d, (30, 348), "Vista previa del email que recibe la familia:", font(11, True), NAVY)
    ex, ey, ew = 360, 372, 380
    rrect(d, [ex, ey, ex + ew, ey + 210], 10, CARD, LINE, 1)
    d.rectangle([ex, ey, ex + ew, ey + 52], fill=NAVY)
    # redondear top con tapa
    text(d, (ex + 18, ey + 12), "APAI Pay", font(14, True), WHITE)
    text(d, (ex + 18, ey + 32), "Cuota societaria", font(9), (155, 182, 210))
    text(d, (ex + ew / 2, ey + 74), "$45.000,00", font(20, True), GREEN, anchor="ma")
    text(d, (ex + 18, ey + 108), "Estimada familia de GONZALEZ, Mateo:", font(9), DARK)
    text(d, (ex + 18, ey + 126), "Adjuntamos el cupón de la cuota de APAI", font(9), GTXT)
    text(d, (ex + 18, ey + 140), "correspondiente al mes de junio de 2026.", font(9), GTXT)
    rrect(d, [ex + 110, ey + 162, ex + ew - 110, ey + 192], 8, RED)
    text(d, (ex + ew / 2, ey + 177), "Pagar cupón", font(10, True), WHITE, anchor="mm")
    guardar(img, "cupones.png")


cap_cobro()
cap_alumnos()
cap_reportes()
cap_cupones()
print("Listo")
