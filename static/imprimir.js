// =====================================================================
//  Imprimir en APAI: portal de alumnos para mandar archivos a la fotocopiadora
// =====================================================================
const $ = id => document.getElementById(id);
let yo = null;
let claveIngreso = null;   // la clave con la que entró (el DNI) para el cambio obligatorio
let elegidos = [];         // File[]
let copias = 1;

function escapeHtml(s) {
    return s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function toast(msg, tipo = 'success') {
    if (!msg) return;
    const el = $('toast');
    el.textContent = msg;
    el.className = 'toast ' + tipo + ' show';
    setTimeout(() => el.classList.remove('show'), 4500);
}
function mostrar(id) {
    document.querySelectorAll('.p-vista').forEach(v => v.hidden = v.id !== id);
    $('p-usuario').hidden = id !== 'v-app';
    window.scrollTo({ top: 0 });
}
function mensaje(id, tipo, texto) { const m = $(id); m.className = 'p-msg ' + tipo; m.textContent = texto; m.hidden = !texto; }
function verClave(id, btn) { const i = $(id); const ver = i.type === 'password'; i.type = ver ? 'text' : 'password'; btn.textContent = ver ? 'Ocultar' : 'Ver'; }
function mostrarLogin() { mostrar('v-login'); }
const fmtMB = b => b == null ? '' : b < 1024 * 1024 ? Math.max(1, Math.round(b / 1024)) + ' KB' : (b / 1024 / 1024).toLocaleString('es-AR', { maximumFractionDigits: 1 }) + ' MB';
function fmtFecha(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const hoy = new Date(); const ayer = new Date(); ayer.setDate(hoy.getDate() - 1);
    const hora = d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    if (d.toDateString() === hoy.toDateString()) return 'hoy ' + hora;
    if (d.toDateString() === ayer.toDateString()) return 'ayer ' + hora;
    return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' }) + ' ' + hora;
}

async function api(url, opts = {}) {
    const res = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    let data = {};
    try { data = await res.json(); } catch {}
    if (res.status === 401 && !url.endsWith('/login')) { mostrarLogin(); throw new Error(data.detail || 'Tu sesión venció'); }
    if (res.status === 403 && /contraseña personal/.test(data.detail || '')) { mostrarClave(); throw new Error(''); }
    if (!res.ok) throw new Error(data.detail || 'No se pudo completar. Probá de nuevo.');
    return data;
}

// ---------------------------------------------------------------- ingreso
async function ingresar(e) {
    e.preventDefault();
    mensaje('login-msg', '', '');
    const btn = e.submitter; btn.disabled = true;
    try {
        const clave = $('l-pass').value;
        const r = await api('/api/imprimir/login', { method: 'POST', body: JSON.stringify({ dni: $('l-dni').value, password: clave }) });
        $('l-pass').value = '';
        if (r.debe_cambiar_password) { claveIngreso = clave; mostrarClave(); }
        else await cargarApp();
    } catch (err) { mensaje('login-msg', 'error', err.message); }
    finally { btn.disabled = false; }
}

function mostrarClave() {
    $('clave-actual-wrap').hidden = !!claveIngreso;
    mensaje('clave-msg', '', '');
    mostrar('v-clave');
}

async function guardarClave(e) {
    e.preventDefault();
    const nueva = $('c-nueva').value;
    if (nueva !== $('c-repetir').value) return mensaje('clave-msg', 'error', 'Las dos contraseñas no coinciden.');
    if (nueva.length < 8 || !/[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(nueva) || !/\d/.test(nueva))
        return mensaje('clave-msg', 'error', 'Usá al menos 8 caracteres combinando letras y números.');
    const btn = e.submitter; btn.disabled = true;
    try {
        await api('/api/imprimir/cambiar-password', { method: 'POST', body: JSON.stringify({
            password_actual: claveIngreso || $('c-actual').value, password_nueva: nueva }) });
        claveIngreso = null;
        ['c-actual', 'c-nueva', 'c-repetir'].forEach(i => $(i).value = '');
        toast('Contraseña guardada. ¡Listo para imprimir!');
        await cargarApp();
    } catch (err) { mensaje('clave-msg', 'error', err.message); }
    finally { btn.disabled = false; }
}

async function salir() {
    try { await fetch('/api/imprimir/logout', { method: 'POST', credentials: 'same-origin' }); } catch {}
    yo = null; elegidos = [];
    mostrarLogin();
}

async function cargarApp() {
    yo = await api('/api/imprimir/me');
    if (yo.debe_cambiar_password) return mostrarClave();
    $('im-ini').textContent = (yo.nombre || '?').trim()[0].toUpperCase();
    $('im-nombre').textContent = `${yo.nombre} ${yo.apellido}`;
    $('im-curso').textContent = yo.curso + ' · legajo ' + yo.legajo;
    mostrar('v-app');
    pintarElegidos();
    cargarPedidos();
}

// ---------------------------------------------------------------- nuevo envío
function extension(nombre) { return (nombre.includes('.') ? nombre.split('.').pop() : '').toLowerCase(); }

function elegirArchivos(files, esFoto = false) {
    const permitidas = new Set(yo.extensiones);
    for (const f of files) {
        let file = f;
        // las fotos de la cámara a veces llegan como "image.jpg" o sin extensión
        if (!extension(file.name) && file.type.startsWith('image/')) {
            file = new File([f], `foto.${file.type.split('/')[1] || 'jpg'}`, { type: f.type });
        }
        if (esFoto) {
            const n = elegidos.filter(x => x.name.startsWith('Foto ')).length + 1;
            file = new File([file], `Foto ${n}.${extension(file.name) || 'jpg'}`, { type: file.type });
        }
        if (!permitidas.has(extension(file.name))) { toast(`«${file.name}» no se puede imprimir. Mandá PDF, fotos o Word.`, 'error'); continue; }
        if (file.size > yo.max_mb * 1024 * 1024) { toast(`«${file.name}» pesa más de ${yo.max_mb} MB.`, 'error'); continue; }
        elegidos.push(file);
    }
    $('im-archivos').value = ''; $('im-camara').value = '';
    pintarElegidos();
}

function quitarElegido(i) { elegidos.splice(i, 1); pintarElegidos(); }

function pintarElegidos() {
    $('im-elegidos').innerHTML = elegidos.map((f, i) => `<li>
        <svg class="ic"><use href="#${f.type.startsWith('image/') ? 'i-camera' : 'i-file'}"/></svg>
        <div><b>${escapeHtml(f.name)}</b><small>${fmtMB(f.size)}</small></div>
        <button type="button" class="im-quitar" onclick="quitarElegido(${i})" aria-label="Quitar ${escapeHtml(f.name)}"><svg class="ic"><use href="#i-x"/></svg></button></li>`).join('');
    $('im-enviar').disabled = !elegidos.length;
    $('im-enviar').querySelector('span').textContent = elegidos.length > 1 ? `Enviar ${elegidos.length} archivos` : 'Enviar a imprimir';
}

function cambiarCopias(d) { copias = Math.max(1, Math.min(50, copias + d)); $('im-copias').textContent = copias; }

function subir(url, file, alAvanzar) {
    // XMLHttpRequest para poder mostrar el avance (con datos móviles tarda)
    return new Promise((ok, mal) => {
        const x = new XMLHttpRequest();
        x.open('PUT', url);
        x.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
        x.upload.onprogress = e => e.lengthComputable && alAvanzar(e.loaded / e.total);
        x.onload = () => x.status < 300 ? ok() : mal(new Error('No se pudo subir el archivo. Probá de nuevo.'));
        x.onerror = () => mal(new Error('Se cortó la conexión. Revisá internet y probá de nuevo.'));
        x.send(file);
    });
}

async function enviar(e) {
    e.preventDefault();
    if (!elegidos.length) return;
    const btn = $('im-enviar'); btn.disabled = true;
    const total = elegidos.reduce((s, f) => s + f.size, 0) || 1;
    let hechos = 0, enviados = 0;
    $('im-progreso').hidden = false;
    const avance = (parcial, i) => {
        $('im-barra').style.width = Math.round((hechos + parcial) / total * 100) + '%';
        $('im-progreso-txt').textContent = `Subiendo ${i + 1} de ${elegidos.length}…`;
    };
    const opciones = { copias, doble_faz: $('im-doble').checked, notas: $('im-notas').value };
    try {
        for (let i = 0; i < elegidos.length; i++) {
            const f = elegidos[i];
            const firma = await api('/api/imprimir/firma', { method: 'POST', body: JSON.stringify({ nombre: f.name, tamanio: f.size }) });
            await subir(firma.upload_url, f, p => avance(p * f.size, i));
            await api('/api/imprimir/pedidos', { method: 'POST', body: JSON.stringify({ ruta: firma.ruta, nombre: f.name, tamanio: f.size, ...opciones }) });
            hechos += f.size; enviados++;
        }
        toast(enviados > 1 ? `Listo: ${enviados} archivos enviados a la oficina.` : 'Listo: tu archivo llegó a la oficina.');
        elegidos = []; copias = 1; $('im-copias').textContent = 1; $('im-doble').checked = false; $('im-notas').value = '';
    } catch (err) {
        if (err.message) toast(err.message, 'error');
        elegidos = elegidos.slice(enviados);   // los que ya llegaron no se vuelven a mandar
    } finally {
        $('im-progreso').hidden = true; $('im-barra').style.width = '0';
        pintarElegidos();
        if (enviados) cargarPedidos();
    }
}

// ---------------------------------------------------------------- mis envíos
const ESTADOS = {
    pendiente: ['En espera', 'i-clock', 'aviso'],
    impreso: ['Impreso', 'i-check', 'ok'],
    descartado: ['Descartado', 'i-alert', 'mal'],
    cancelado: ['Cancelado', 'i-x', 'neutro'],
};

async function cargarPedidos() {
    try {
        const lista = await api('/api/imprimir/pedidos');
        $('im-lista').innerHTML = lista.length ? lista.map(p => {
            const [txt, ic, cls] = ESTADOS[p.estado] || [p.estado, 'i-file', 'neutro'];
            const detalle = [p.copias > 1 ? `${p.copias} copias` : '1 copia', p.doble_faz ? 'doble faz' : '', fmtMB(p.tamanio)].filter(Boolean).join(' · ');
            const cuando = p.estado === 'impreso' ? `Impreso ${fmtFecha(p.resuelto)} · retiralo en la oficina`
                : p.estado === 'descartado' ? `Descartado ${fmtFecha(p.resuelto)}`
                : p.estado === 'cancelado' ? `Cancelado ${fmtFecha(p.resuelto)}` : `Enviado ${fmtFecha(p.enviado)}`;
            return `<li class="im-item im-${p.estado}">
                <div class="im-item-top"><b class="im-nombre-arch">${escapeHtml(p.archivo)}</b>
                    <span class="p-estado ${cls}"><svg class="ic"><use href="#${ic}"/></svg>${txt}</span></div>
                <small>${escapeHtml(detalle)}${p.notas ? ' · ' + escapeHtml(p.notas) : ''}</small>
                <small class="im-cuando">${cuando}</small>
                ${p.estado === 'descartado' && p.motivo ? `<p class="im-motivo"><b>Motivo:</b> ${escapeHtml(p.motivo)}. Corregilo y mandalo de nuevo.</p>` : ''}
                ${p.estado === 'pendiente' ? `<button class="btn btn-ghost btn-sm im-cancelar" onclick="cancelarPedido(${p.id})">Cancelar envío</button>` : ''}
            </li>`;
        }).join('') : '<li class="p-vacio">Todavía no mandaste nada. Elegí un archivo arriba para empezar.</li>';
    } catch (err) { if (err.message) toast(err.message, 'error'); }
}

async function cancelarPedido(id) {
    if (!confirm('¿Cancelar este envío? La oficina ya no lo va a ver.')) return;
    try { await api(`/api/imprimir/pedidos/${id}/cancelar`, { method: 'POST' }); toast('Envío cancelado'); cargarPedidos(); }
    catch (err) { toast(err.message, 'error'); }
}

// Al volver a la pestaña (p. ej. después de un rato) se actualiza solo
document.addEventListener('visibilitychange', () => { if (!document.hidden && yo && !$('v-app').hidden) cargarPedidos(); });

(async function inicio() {
    try { await cargarApp(); } catch { mostrarLogin(); }
})();
