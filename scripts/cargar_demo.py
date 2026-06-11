# -*- coding: utf-8 -*-
"""Carga datos FICTICIOS de demo: tarjetas, saldos y movimientos para todos los alumnos."""
import sys
import random
from pathlib import Path
from datetime import timedelta
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.alumno import Alumno
from app.models.tarjeta import Tarjeta
from app.models.saldo import Saldo
from app.models.movimiento import Movimiento
from app.tz import ahora_ar

random.seed(7)
db = SessionLocal()

OPERADORES = ["Ana Maria", "Carlos", "Sofia", "Mariano", "Lucia"]
CONCEPTOS = ["Fotocopias", "Libro Matemática", "Libro Inglés", "Materiales Taller",
             "Fotocopias + Materiales Taller", "Anillado", "Impresiones color",
             "Fotocopias + Libro Inglés"]

# Limpiar movimientos y tarjetas previos (NO toca alumnos ni borra el padron)
db.query(Movimiento).delete()
db.query(Tarjeta).delete()
db.commit()

alumnos = db.query(Alumno).all()
por_id = {a.id: a for a in alumnos}
ahora = ahora_ar()


def fecha_random(max_dias=30):
    return ahora - timedelta(days=random.randint(0, max_dias),
                             hours=random.randint(0, 12), minutes=random.randint(0, 59))


usados = set()
def nuevo_uid():
    while True:
        u = ''.join(random.choice('0123456789ABCDEF') for _ in range(8))
        if u not in usados:
            usados.add(u)
            return u


tarjetas, movimientos = [], []
saldos = {}

for a in alumnos:
    tarjetas.append(Tarjeta(uid=nuevo_uid(), alumno_id=a.id, activa=True))

    recarga = Decimal(str(random.choice([1500, 2000, 3000, 5000, 10000])))
    movimientos.append(Movimiento(
        alumno_id=a.id, tipo='recarga', monto=recarga,
        descripcion='Recarga por transferencia',
        operador=random.choice(OPERADORES), created_at=fecha_random(30)))
    saldo = recarga

    for _ in range(random.randint(0, 5)):
        if saldo <= 50:
            break
        c = Decimal(str(random.choice([50, 100, 150, 200, 250, 300, 500])))
        if c > saldo:
            c = saldo
        movimientos.append(Movimiento(
            alumno_id=a.id, tipo='consumo', monto=-c,
            descripcion=random.choice(CONCEPTOS),
            operador=random.choice(OPERADORES), created_at=fecha_random(25)))
        saldo -= c

    if random.random() < 0.12 and saldo >= 500:
        r = Decimal(str(random.choice([500, 1000])))
        if r <= saldo:
            movimientos.append(Movimiento(
                alumno_id=a.id, tipo='reintegro', monto=-r,
                descripcion='Reintegro en efectivo',
                operador=random.choice(OPERADORES), created_at=fecha_random(20)))
            saldo -= r

    saldos[a.id] = saldo

# Transferencias entre alumnos (hermanos / amigos)
ids = list(por_id.keys())
transf = 0
for _ in range(60):
    o, d = random.choice(ids), random.choice(ids)
    if o == d or saldos.get(o, Decimal(0)) < 500:
        continue
    m = Decimal(str(random.choice([200, 500, 1000])))
    if m > saldos[o]:
        continue
    f = fecha_random(15)
    ao, ad = por_id[o], por_id[d]
    movimientos.append(Movimiento(
        alumno_id=o, tipo='transferencia_out', monto=-m,
        descripcion=f'Transferencia a {ad.apellido}, {ad.nombre}', referencia_id=d,
        operador=random.choice(OPERADORES), created_at=f))
    movimientos.append(Movimiento(
        alumno_id=d, tipo='transferencia_in', monto=m,
        descripcion=f'Transferencia de {ao.apellido}, {ao.nombre}', referencia_id=o,
        operador=random.choice(OPERADORES), created_at=f))
    saldos[o] -= m
    saldos[d] += m
    transf += 1

db.add_all(tarjetas)
db.add_all(movimientos)

saldos_db = {s.alumno_id: s for s in db.query(Saldo).all()}
for aid, val in saldos.items():
    if aid in saldos_db:
        saldos_db[aid].monto = val
    else:
        db.add(Saldo(alumno_id=aid, monto=val))

db.commit()
print(f"OK -> Tarjetas: {len(tarjetas)} | Movimientos: {len(movimientos)} | Transferencias: {transf}")
print(f"Saldo total cargado: ${sum(saldos.values()):,.2f}")
db.close()
