// =====================================================================
//  Portal de proveedores: subir facturas a APAI (sin cuenta)
// =====================================================================
const $ = id => document.getElementById(id);
const MAX = 4 * 1024 * 1024;
let archivos = [];   // {file, estado: 'pendiente'|'enviando'|'ok'|'mal', texto}

function esc(s) { return s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function toast(msg, tipo = 'success') {
    const el = $('toast'); el.textContent = msg; el.className = 'toast ' + tipo + ' show';
    setTimeout(() => el.classList.remove('show'), 3500);
}
function kb(n) { return n > 1024 * 1024 ? (n / 1024 / 1024).toFixed(1).replace('.', ',') + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }

// ---------------------------------------------------------------- datos de APAI
(async function cargarApai() {
    try {
        const a = await (await fetch('/api/publico/apai')).json();
        const fila = (t, v) => v ? `<div><span><dt>${t}</dt><dd>${esc(v)}</dd></span>
            <button type="button" class="btn btn-sm btn-ghost" onclick="copiarTexto('${esc(v).replace(/'/g, '&#39;')}','${t} copiado')" aria-label="Copiar ${t}"><svg class="ic"><use href="#i-copy"/></svg>Copiar</button></div>` : '';
        $('f-apai').innerHTML = fila('Razón social', a.razon_social) + fila('CUIT', a.cuit) + fila('Domicilio', a.domicilio) + fila('Condición frente al IVA', a.condicion_iva);
    } catch { $('f-apai').innerHTML = '<div class="muted">No se pudieron cargar los datos. Recargá la página.</div>'; }
})();

// ---------------------------------------------------------------- selección de archivos
function agregarArchivos(lista) {
    for (const f of lista) {
        const esPdf = f.type === 'application/pdf' || /\.pdf$/i.test(f.name);
        if (!esPdf) { toast(`«${f.name}» no es un PDF`, 'error'); continue; }
        if (f.size > MAX) { toast(`«${f.name}» pesa más de 4 MB`, 'error'); continue; }
        if (archivos.some(a => a.file.name === f.name && a.file.size === f.size)) continue;
        archivos.push({ file: f, estado: 'pendiente', texto: kb(f.size) });
    }
    $('f-archivos').value = '';
    pintar();
}

function quitar(i) { archivos.splice(i, 1); pintar(); }

function pintar() {
    const icono = { pendiente: 'i-file', enviando: 'i-upload', ok: 'i-check', mal: 'i-alert' };
    $('f-lista').innerHTML = archivos.map((a, i) => `<li class="${a.estado}">
        <svg class="ic"><use href="#${icono[a.estado]}"/></svg>
        <span class="f-nom"><b>${esc(a.file.name)}</b><small>${esc(a.texto)}</small></span>
        ${a.estado === 'pendiente' ? `<button type="button" class="f-quitar" onclick="quitar(${i})" aria-label="Quitar ${esc(a.file.name)}"><svg class="ic"><use href="#i-x"/></svg></button>` : ''}
    </li>`).join('');
    $('f-enviar').disabled = !archivos.some(a => a.estado === 'pendiente');
    const n = archivos.filter(a => a.estado === 'pendiente').length;
    $('f-enviar').textContent = n > 1 ? `Enviar ${n} facturas` : 'Enviar factura';
}

const zona = $('f-zona');
['dragenter', 'dragover'].forEach(ev => zona.addEventListener(ev, e => { e.preventDefault(); zona.classList.add('arrastrando'); }));
['dragleave', 'drop'].forEach(ev => zona.addEventListener(ev, e => { e.preventDefault(); zona.classList.remove('arrastrando'); }));
zona.addEventListener('drop', e => agregarArchivos(e.dataTransfer.files));

// ---------------------------------------------------------------- QR de AFIP (se lee en este dispositivo)
function _rgba(o) {
    const { width: w, height: h, kind, data } = o, out = new Uint8ClampedArray(w * h * 4);
    if (kind === 3) out.set(data.subarray(0, w * h * 4));
    else if (kind === 2) for (let i = 0, j = 0; i < w * h; i++, j += 3) { out[i * 4] = data[j]; out[i * 4 + 1] = data[j + 1]; out[i * 4 + 2] = data[j + 2]; out[i * 4 + 3] = 255; }
    else { const f = (w + 7) >> 3; for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const v = (data[y * f + (x >> 3)] >> (7 - (x & 7))) & 1 ? 255 : 0, k = (y * w + x) * 4; out[k] = out[k + 1] = out[k + 2] = v; out[k + 3] = 255; } }
    return { data: out, w, h };
}

function _qrDe(img) {  // agranda las imágenes chicas y agrega margen blanco
    const esc = Math.max(1, Math.ceil(300 / Math.min(img.w, img.h))), m = 20;
    const c = document.createElement('canvas');
    c.width = img.w * esc + 2 * m; c.height = img.h * esc + 2 * m;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    const t = document.createElement('canvas'); t.width = img.w; t.height = img.h;
    t.getContext('2d').putImageData(new ImageData(img.data, img.w, img.h), 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(t, m, m, img.w * esc, img.h * esc);
    const q = jsQR(ctx.getImageData(0, 0, c.width, c.height).data, c.width, c.height, { inversionAttempts: 'attemptBoth' });
    return q && q.data;
}

async function leerQR(file) {
    if (!window.pdfjsLib || !window.jsQR) return null;
    try {
        const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer(), isOffscreenCanvasSupported: false }).promise;
        const page = await pdf.getPage(1);
        const ops = await page.getOperatorList();
        for (let i = 0; i < ops.fnArray.length; i++) {
            if (ops.fnArray[i] !== pdfjsLib.OPS.paintImageXObject) continue;
            const id = ops.argsArray[i][0];
            const o = await new Promise(res => (id.startsWith('g_') ? page.commonObjs : page.objs).get(id, res));
            if (!o || !o.data || Math.abs(o.width - o.height) > o.width * 0.15) continue;  // los QR son cuadrados
            const t = _qrDe(_rgba(o));
            if (t && /afip|arca/i.test(t)) { pdf.destroy(); return t; }
        }
        // Factura escaneada: se dibuja la página y se busca el QR en la imagen completa
        if (document.visibilityState === 'visible') {
            const vp = page.getViewport({ scale: 2 });
            const c = document.createElement('canvas'); c.width = vp.width; c.height = vp.height;
            const ctx = c.getContext('2d', { willReadFrequently: true });
            await Promise.race([page.render({ canvasContext: ctx, viewport: vp }).promise, new Promise(r => setTimeout(r, 5000))]);
            const q = jsQR(ctx.getImageData(0, 0, c.width, c.height).data, c.width, c.height, { inversionAttempts: 'attemptBoth' });
            if (q && /afip|arca/i.test(q.data)) { pdf.destroy(); return q.data; }
        }
        pdf.destroy();
    } catch { /* si no se puede leer, el servidor usa el texto del PDF */ }
    return null;
}

// ---------------------------------------------------------------- envío
async function enviar(e) {
    e.preventDefault();
    const msg = $('f-msg'); msg.hidden = true;
    const email = $('f-email').value.trim();
    if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { msg.className = 'p-msg error'; msg.textContent = 'Revisá el correo.'; msg.hidden = false; return; }
    const envio = Array.from(crypto.getRandomValues(new Uint8Array(12)), b => b.toString(16).padStart(2, '0')).join('');
    $('f-enviar').disabled = true;
    let ok = 0, mal = 0;
    for (const a of archivos.filter(x => x.estado === 'pendiente')) {
        a.estado = 'enviando'; a.texto = 'Enviando…'; pintar();
        try {
            const fd = new FormData();
            fd.append('archivo', a.file);
            fd.append('envio', envio);
            fd.append('proveedor', $('f-proveedor').value.trim());
            fd.append('email', email);
            fd.append('comentario', $('f-comentario').value.trim());
            fd.append('web', $('f-web').value);
            const qr = await leerQR(a.file);
            if (qr) fd.append('qr', qr);
            const res = await fetch('/api/publico/facturas', { method: 'POST', body: fd, credentials: 'same-origin' });
            const r = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(r.detail || 'No se pudo enviar. Probá de nuevo.');
            a.estado = 'ok';
            const partes = [r.proveedor, r.numero ? 'N° ' + r.numero : '', r.importe != null ? fmtMoneda(r.importe) : '', r.fecha ? fmtFecha(r.fecha) : ''].filter(Boolean);
            a.texto = r.estado === 'duplicada' ? r.mensaje
                : (r.leida ? 'Recibida ✓ ' + partes.join(' · ') : 'Recibida ✓ La revisamos y la cargamos a mano.')
                  + (r.a_nombre_de_apai === false ? ' Atención: no parece estar a nombre de APAI.' : '');
            ok++;
        } catch (err) { a.estado = 'mal'; a.texto = err.message; mal++; }
        pintar();
    }
    if (ok) { msg.className = 'p-msg ok'; msg.textContent = ok === 1 ? '¡Listo! Recibimos tu factura.' : `¡Listo! Recibimos ${ok} facturas.`; msg.hidden = false; }
    if (mal) toast(mal === 1 ? 'Una factura no se pudo enviar' : `${mal} facturas no se pudieron enviar`, 'error');
}
