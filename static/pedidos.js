// =====================================================================
//  Pedido de materiales y servicios (formulario público, sin cuenta)
// =====================================================================
const $ = id => document.getElementById(id);
const UNIDADES = ['Unidad', 'Caja', 'Paquete', 'Resma', 'Bolsa', 'Rollo', 'Juego', 'Par', 'Docena', 'Metro', 'Metro²',
    'Litro', 'Kilo', 'Gramo', 'Hora', 'Servicio', 'Otra'];
const CAMPOS = ['producto', 'cantidad', 'unidad', 'marca', 'modelo', 'color', 'tamanio', 'caracteristicas', 'descripcion'];
const BORRADOR = 'apai-pedido-borrador';
let items = [];

function esc(s) { return s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function toast(msg, tipo = 'success') {
    const el = $('toast'); el.textContent = msg; el.className = 'toast ' + tipo + ' show';
    setTimeout(() => el.classList.remove('show'), 3500);
}
const itemVacio = () => ({ producto: '', cantidad: '1', unidad: 'Unidad', marca: '', modelo: '', color: '', tamanio: '', caracteristicas: '', descripcion: '' });

// ---------------------------------------------------------------- productos
function pintarItems(enfocar = null) {
    $('pd-items').innerHTML = items.map((it, i) => `
        <li class="pd-item${i === enfocar && items.length > 1 ? ' pd-entra' : ''}" data-i="${i}">
            <div class="pd-item-cab">
                <span class="pd-item-n">Producto ${i + 1}</span>
                <span style="flex:1"></span>
                <button type="button" class="btn btn-sm btn-ghost" onclick="duplicarItem(${i})" title="Duplicar este producto"><svg class="ic"><use href="#i-copy"/></svg>Duplicar</button>
                ${items.length > 1 ? `<button type="button" class="btn btn-sm btn-ghost pd-quitar" onclick="quitarItem(${i})" aria-label="Quitar el producto ${i + 1}"><svg class="ic"><use href="#i-trash"/></svg>Quitar</button>` : ''}
            </div>
            <div class="pd-grid">
                <div class="pd-c-prod"><label for="it${i}-producto">Producto o servicio <span class="pd-req" aria-hidden="true">*</span></label>
                    <input type="text" id="it${i}-producto" data-c="producto" maxlength="160" value="${esc(it.producto)}" placeholder="Ej.: Cable unipolar, resma A4, service de aire acondicionado…">
                    <div class="pd-error" id="err-it${i}-producto"></div></div>
                <div class="pd-c-cant"><label for="it${i}-cantidad">Cantidad <span class="pd-req" aria-hidden="true">*</span></label>
                    <input type="text" id="it${i}-cantidad" data-c="cantidad" inputmode="decimal" maxlength="12" value="${esc(it.cantidad)}">
                    <div class="pd-error" id="err-it${i}-cantidad"></div></div>
                <div class="pd-c-unid"><label for="it${i}-unidad">Unidad de medida</label>
                    <select id="it${i}-unidad" data-c="unidad">${UNIDADES.map(u => `<option ${u === it.unidad ? 'selected' : ''}>${u}</option>`).join('')}</select></div>
                <div><label for="it${i}-marca">Marca</label><input type="text" id="it${i}-marca" data-c="marca" maxlength="80" value="${esc(it.marca)}"></div>
                <div><label for="it${i}-modelo">Modelo</label><input type="text" id="it${i}-modelo" data-c="modelo" maxlength="80" value="${esc(it.modelo)}"></div>
                <div><label for="it${i}-color">Color</label><input type="text" id="it${i}-color" data-c="color" maxlength="60" value="${esc(it.color)}"></div>
                <div><label for="it${i}-tamanio">Tamaño o medida</label><input type="text" id="it${i}-tamanio" data-c="tamanio" maxlength="80" value="${esc(it.tamanio)}" placeholder="Ej.: 2,5 mm², A4, 1 m"></div>
                <div class="pd-c-ancho"><label for="it${i}-caracteristicas">Características</label>
                    <input type="text" id="it${i}-caracteristicas" data-c="caracteristicas" maxlength="300" value="${esc(it.caracteristicas)}" placeholder="Ej.: 220 V, de acero inoxidable, para uso exterior"></div>
                <div class="pd-c-ancho"><label for="it${i}-descripcion">Descripción adicional <span class="muted">(opcional)</span></label>
                    <textarea id="it${i}-descripcion" data-c="descripcion" rows="2" maxlength="1000" placeholder="Cualquier dato que ayude: un código, un link, dónde se instala, una marca alternativa…">${esc(it.descripcion)}</textarea></div>
            </div>
        </li>`).join('');
    resumen();
    if (enfocar !== null) {
        const el = $(`it${enfocar}-producto`);
        if (el) { el.focus({ preventScroll: true }); el.closest('.pd-item').scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    }
}

function agregarItem() { items.push(itemVacio()); pintarItems(items.length - 1); guardarBorrador(); }
function duplicarItem(i) { items.splice(i + 1, 0, { ...items[i] }); pintarItems(i + 1); guardarBorrador(); }
function quitarItem(i) {
    const it = items[i];
    if ((it.producto || it.marca || it.descripcion) && !confirm(`¿Quitar «${it.producto || 'el producto ' + (i + 1)}»?`)) return;
    items.splice(i, 1);
    pintarItems();
    guardarBorrador();
}

$('pd-items').addEventListener('input', e => {
    const li = e.target.closest('.pd-item'), c = e.target.dataset.c;
    if (!li || !c) return;
    items[+li.dataset.i][c] = e.target.value;
    e.target.classList.remove('pd-mal');
    const err = $(`err-it${li.dataset.i}-${c}`);
    if (err) err.textContent = '';
    resumen();
    guardarBorrador();
});

function cantidadNum(v) {
    const t = String(v || '').trim().replace(/\./g, '').replace(',', '.');
    return /^\d+(\.\d+)?$/.test(t) ? Number(t) : NaN;
}

function resumen() {
    const ok = items.filter(it => it.producto.trim()).length;
    $('pd-resumen').textContent = ok ? `${ok} producto${ok === 1 ? '' : 's'} en el pedido.` : '';
}

// ---------------------------------------------------------------- borrador (por si se cierra la página)
const DATOS = ['pd-nombre', 'pd-cargo', 'pd-email', 'pd-tel', 'pd-sector', 'pd-fecha', 'pd-motivo'];
function guardarBorrador() {
    try {
        const d = { items, tipo: (document.querySelector('[name=pd-tipo]:checked') || {}).value, urgente: $('pd-urgente').checked };
        DATOS.forEach(id => { d[id] = $(id).value; });
        localStorage.setItem(BORRADOR, JSON.stringify(d));
    } catch { /* sin almacenamiento: no pasa nada */ }
}
function leerBorrador() {
    try {
        const d = JSON.parse(localStorage.getItem(BORRADOR) || 'null');
        if (!d) return false;
        DATOS.forEach(id => { if (d[id] != null) $(id).value = d[id]; });
        if (d.tipo) { const r = document.querySelector(`[name=pd-tipo][value="${d.tipo}"]`); if (r) r.checked = true; }
        $('pd-urgente').checked = !!d.urgente;
        if (Array.isArray(d.items) && d.items.length) items = d.items.map(x => ({ ...itemVacio(), ...x }));
        return true;
    } catch { return false; }
}
function borrarBorrador() { try { localStorage.removeItem(BORRADOR); } catch { } }
document.querySelectorAll('#pd-form input:not([data-c]), #pd-form textarea:not([data-c])').forEach(el =>
    el.addEventListener('input', () => { el.classList.remove('pd-mal'); guardarBorrador(); }));

// ---------------------------------------------------------------- envío
function marcar(id, errId, texto) {
    const el = $(id), err = $(errId);
    if (el) el.classList.add('pd-mal');
    if (err) err.textContent = texto;
    return el;
}

function validar() {
    document.querySelectorAll('.pd-error').forEach(e => { e.textContent = ''; });
    document.querySelectorAll('.pd-mal').forEach(e => e.classList.remove('pd-mal'));
    const errores = [];
    const nombre = $('pd-nombre').value.trim();
    if (nombre.length < 3) errores.push(marcar('pd-nombre', 'err-nombre', 'Escribí tu nombre y apellido.'));
    const email = $('pd-email').value.trim();
    if (email && !/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email)) errores.push(marcar('pd-email', 'err-email', 'Revisá el correo (ej.: nombre@gmail.com).'));
    if ($('pd-sector').value.trim().length < 2) errores.push(marcar('pd-sector', 'err-sector', 'Indicá para qué sector o área es.'));
    if ($('pd-fecha').value && $('pd-fecha').value < hoyISO()) errores.push(marcar('pd-fecha', 'err-fecha', 'La fecha ya pasó.'));
    const conDatos = items.map((it, i) => ({ it, i })).filter(({ it }) => CAMPOS.some(c => c !== 'unidad' && c !== 'cantidad' && String(it[c] || '').trim()));
    if (!conDatos.length) errores.push(marcar('it0-producto', 'err-it0-producto', 'Agregá al menos un producto.'));
    conDatos.forEach(({ it, i }) => {
        if (!it.producto.trim()) errores.push(marcar(`it${i}-producto`, `err-it${i}-producto`, 'Falta el nombre del producto.'));
        const n = cantidadNum(it.cantidad);
        if (!(n > 0)) errores.push(marcar(`it${i}-cantidad`, `err-it${i}-cantidad`, 'Poné una cantidad (ej.: 2 o 1,5).'));
    });
    return { errores: errores.filter(Boolean), conDatos };
}

async function enviarPedido(ev) {
    ev.preventDefault();
    const msg = $('pd-msg');
    msg.hidden = true;
    const { errores, conDatos } = validar();
    if (errores.length) {
        errores[0].focus();
        errores[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        msg.textContent = errores.length === 1 ? 'Revisá el campo marcado.' : `Revisá los ${errores.length} campos marcados.`;
        msg.className = 'p-msg error'; msg.hidden = false;
        return;
    }
    const boton = $('pd-boton');
    boton.disabled = true;
    boton.innerHTML = 'Enviando…';
    const cuerpo = {
        solicitante: $('pd-nombre').value.trim(), cargo: $('pd-cargo').value.trim() || null, email: $('pd-email').value.trim() || null,
        telefono: $('pd-tel').value.trim() || null, sector: $('pd-sector').value.trim(),
        tipo: document.querySelector('[name=pd-tipo]:checked').value, motivo: $('pd-motivo').value.trim() || null,
        necesario_para: $('pd-fecha').value || null, urgente: $('pd-urgente').checked, web: $('pd-web').value,
        items: conDatos.map(({ it }) => ({
            producto: it.producto.trim(), cantidad: cantidadNum(it.cantidad), unidad: it.unidad,
            marca: it.marca.trim() || null, modelo: it.modelo.trim() || null, color: it.color.trim() || null,
            tamanio: it.tamanio.trim() || null, caracteristicas: it.caracteristicas.trim() || null, descripcion: it.descripcion.trim() || null,
        })),
    };
    try {
        const res = await fetch('/api/publico/pedidos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
        let data = {};
        try { data = await res.json(); } catch { }
        if (!res.ok) {
            const d = data.detail;
            throw new Error(Array.isArray(d) ? 'Revisá los datos del pedido: ' + (d[0] && d[0].msg || '') : (d || 'No se pudo enviar el pedido.'));
        }
        borrarBorrador();
        mostrarListo(data, cuerpo);
    } catch (e) {
        msg.textContent = e.message + ' Tu pedido sigue guardado en esta página: podés volver a intentar.';
        msg.className = 'p-msg error'; msg.hidden = false;
        boton.disabled = false;
        boton.innerHTML = '<svg class="ic"><use href="#i-send"/></svg>Enviar pedido';
    }
}

function unidadTexto(u, n) {
    const plural = { Unidad: 'unidades', Par: 'pares', 'Metro²': 'm²', Otra: 'otras' };
    const t = Number(n) === 1 ? u : (plural[u] || u + 's');
    return t === 'm²' ? t : t.toLowerCase();
}

function mostrarListo(data, cuerpo) {
    $('pd-formulario').hidden = true;
    const fmtCant = n => Number(n).toLocaleString('es-AR', { maximumFractionDigits: 2 });
    $('pd-listo').innerHTML = `
        <div class="pd-ok-icono"><svg class="ic"><use href="#i-check"/></svg></div>
        <h1>¡Pedido enviado!</h1>
        <p class="pd-numero">Pedido N° <b>${esc(data.numero)}</b></p>
        <p class="muted">La administración de APAI ya lo recibió${cuerpo.email ? ` y te mandamos el comprobante a <b>${esc(cuerpo.email)}</b>` : ''}.
        Guardá el número por si tenés que consultar por él.</p>
        <ul class="pd-ok-lista">${cuerpo.items.map(it => `<li><b>${fmtCant(it.cantidad)} ${esc(unidadTexto(it.unidad, it.cantidad))}</b> · ${esc(it.producto)}${[it.marca, it.modelo].filter(Boolean).length ? ` <span class="muted">(${esc([it.marca, it.modelo].filter(Boolean).join(' '))})</span>` : ''}</li>`).join('')}</ul>
        <p class="muted">Para: <b>${esc(cuerpo.sector)}</b>${cuerpo.urgente ? ' · <b>urgente</b>' : ''}</p>
        <button type="button" class="btn btn-primary p-ancho" onclick="nuevoPedido()">Hacer otro pedido</button>`;
    $('pd-listo').hidden = false;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function nuevoPedido() {
    // se mantienen los datos de la persona; se vacían el destino y los productos
    ['pd-sector', 'pd-fecha', 'pd-motivo'].forEach(id => { $(id).value = ''; });
    $('pd-urgente').checked = false;
    items = [itemVacio()];
    pintarItems();
    guardarBorrador();
    $('pd-listo').hidden = true;
    $('pd-formulario').hidden = false;
    const b = $('pd-boton'); b.disabled = false; b.innerHTML = '<svg class="ic"><use href="#i-send"/></svg>Enviar pedido';
    window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- inicio
$('pd-fecha').min = hoyISO();
document.querySelectorAll('[name=pd-tipo], #pd-urgente').forEach(el => el.addEventListener('change', guardarBorrador));
if (!leerBorrador() || !items.length) items = [itemVacio()];
pintarItems();
