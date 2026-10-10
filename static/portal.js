// =====================================================================
//  Portal de familias APAI
// =====================================================================
const $ = id => document.getElementById(id);
let yo = null;            // {email, hijos, consultas_sin_leer}
let hijoId = null;        // alumno seleccionado
let datosHijo = null;     // resumen del alumno seleccionado
let tabActual = 'cuotas';
let categorias = [];
let resetToken = null;

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
function abrirModal(html) { $('modal-content').innerHTML = html; $('modal-overlay').style.display = 'flex'; }
function cerrarModal() { $('modal-overlay').style.display = 'none'; }
document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarModal(); });

async function api(url, opts = {}) {
    const res = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    let data = {};
    try { data = await res.json(); } catch {}
    if (res.status === 401 && !url.endsWith('/login')) { mostrarLogin(); throw new Error(data.detail || 'Sesión vencida'); }
    if (res.status === 403 && /contraseña personal/.test(data.detail || '')) { mostrarClave(false); throw new Error(''); }
    if (!res.ok) throw new Error(data.detail || 'No se pudo completar. Probá de nuevo.');
    return data;
}

function mostrar(id) {
    document.querySelectorAll('.p-vista').forEach(v => v.hidden = v.id !== id);
    $('p-usuario').hidden = id !== 'v-app';
    window.scrollTo({ top: 0 });
}
function mensaje(id, tipo, texto) { const m = $(id); m.className = 'p-msg ' + tipo; m.textContent = texto; m.hidden = !texto; }
function verClave(id, btn) { const i = $(id); const ver = i.type === 'password'; i.type = ver ? 'text' : 'password'; btn.textContent = ver ? 'Ocultar' : 'Ver'; }
function mostrarLogin() { mostrar('v-login'); setTimeout(() => $('l-email').focus(), 50); }

// ---------------------------------------------------------------- ingreso
async function ingresar(e) {
    e.preventDefault();
    mensaje('login-msg', '', '');
    const btn = e.submitter; btn.disabled = true;
    try {
        const r = await api('/api/portal/login', { method: 'POST', body: JSON.stringify({ email: $('l-email').value, password: $('l-pass').value }) });
        $('l-pass').value = '';
        if (r.debe_cambiar_password) mostrarClave(false);
        else await cargarApp();
    } catch (err) { mensaje('login-msg', 'error', err.message); }
    finally { btn.disabled = false; }
}

async function olvide(e) {
    e.preventDefault();
    try {
        const r = await api('/api/portal/olvide', { method: 'POST', body: JSON.stringify({ email: $('o-email').value }) });
        mensaje('olv-msg', 'ok', r.mensaje);
    } catch (err) { mensaje('olv-msg', 'error', err.message); }
}

function mostrarClave(esReset) {
    $('clave-actual-wrap').hidden = esReset;
    $('clave-titulo').textContent = esReset ? 'Crear una contraseña nueva' : 'Creá tu contraseña';
    $('clave-desc').textContent = esReset ? 'Elegí una contraseña nueva. Mínimo 8 caracteres, con letras y números.'
        : 'Por seguridad, reemplazá el DNI por una contraseña personal. Mínimo 8 caracteres, con letras y números.';
    mensaje('clave-msg', '', '');
    mostrar('v-clave');
}

async function guardarClave(e) {
    e.preventDefault();
    const nueva = $('c-nueva').value;
    if (nueva !== $('c-repetir').value) return mensaje('clave-msg', 'error', 'Las contraseñas no coinciden.');
    if (nueva.length < 8 || !/[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(nueva) || !/\d/.test(nueva))
        return mensaje('clave-msg', 'error', 'Usá al menos 8 caracteres combinando letras y números.');
    try {
        if (resetToken) {
            const r = await api('/api/portal/restablecer', { method: 'POST', body: JSON.stringify({ token: resetToken, password_nueva: nueva }) });
            resetToken = null;
            mostrarLogin();
            mensaje('login-msg', 'ok', r.mensaje);
        } else {
            await api('/api/portal/cambiar-password', { method: 'POST', body: JSON.stringify({ password_actual: $('c-actual').value, password_nueva: nueva }) });
            toast('Contraseña creada. ¡Bienvenido/a!');
            await cargarApp();
        }
        ['c-actual', 'c-nueva', 'c-repetir'].forEach(i => $(i).value = '');
    } catch (err) { mensaje('clave-msg', 'error', err.message); }
}

async function salir() {
    const eraVista = yo && yo.vista_admin;
    try { await fetch('/api/portal/logout', { method: 'POST', credentials: 'same-origin' }); } catch {}
    yo = null; hijoId = null;
    if (eraVista) { location.href = '/#alumnos'; return; }
    mostrarLogin();
}

function bandaVistaAdmin() {
    let b = $('p-vista-admin');
    if (!yo.vista_admin) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement('div'); b.id = 'p-vista-admin'; b.className = 'p-vista-admin'; $('contenido').prepend(b); }
    b.innerHTML = `<svg class="ic"><use href="#i-lock"/></svg>
        <div><b>Vista previa del administrador</b> · Estás viendo el portal tal cual lo ve la familia de <b>${escapeHtml(yo.email)}</b>.
        Es solo lectura: no se envían consultas ni se marcan mensajes como leídos. Vence en 30 minutos.</div>
        <button class="btn btn-sm btn-primary" onclick="salir()">Volver al sistema</button>`;
}

// ---------------------------------------------------------------- aplicación
async function cargarApp() {
    yo = await api('/api/portal/me');
    if (yo.debe_cambiar_password) return mostrarClave(false);
    $('p-email').textContent = yo.email;
    mostrar('v-app');
    bandaVistaAdmin();
    if (!yo.hijos.length) {
        $('p-hijos').innerHTML = '';
        $('p-tab').innerHTML = '<div class="card p-vacio">No encontramos alumnos activos con este correo. Escribinos a la Asociación.</div>';
        return;
    }
    $('p-hijos').innerHTML = yo.hijos.map(h => `
        <button class="p-hijo" role="tab" data-id="${h.id}" onclick="elegirHijo(${h.id})">
            <span class="p-ini">${escapeHtml((h.nombre || '?')[0])}</span>
            <span><b>${escapeHtml(h.nombre)} ${escapeHtml(h.apellido)}</b><small>${escapeHtml(h.curso || '')} · Legajo ${escapeHtml(h.legajo)}</small></span>
        </button>`).join('');
    actualizarBadge(yo.consultas_sin_leer);
    if (!categorias.length) categorias = await api('/api/portal/ayuda');
    await elegirHijo(hijoId && yo.hijos.some(h => h.id === hijoId) ? hijoId : yo.hijos[0].id);
    const m = location.hash.match(/^#consulta-(\d+)/);
    if (m) { irTab('consultas'); abrirConsulta(Number(m[1])); history.replaceState(null, '', '/portal'); }
}

function actualizarBadge(n) { const b = $('p-badge'); b.textContent = n; b.hidden = !n; }

async function elegirHijo(id) {
    hijoId = id;
    document.querySelectorAll('.p-hijo').forEach(b => b.setAttribute('aria-selected', String(Number(b.dataset.id) === id)));
    try {
        datosHijo = await api(`/api/portal/alumno/${id}`);
        renderKpis();
        irTab(tabActual);
    } catch (err) { toast(err.message, 'error'); }
}

function claseEstado(e) { return /al día/i.test(e) ? 'ok' : /moroso|sin pagos/i.test(e) ? 'mal' : 'neutro'; }

function renderKpis() {
    const c = datosHijo.cuotas, t = datosHijo.tarjeta;
    $('p-kpis').innerHTML = `
        <div class="gasto-kpi"><div class="gasto-kpi-label">Estado de la cuota</div>
            <div class="gasto-kpi-valor"><span class="p-estado ${claseEstado(c.estado)}">${escapeHtml(c.estado)}</span></div>
            <div class="gasto-kpi-sub">año ${c.anio}</div></div>
        <div class="gasto-kpi ${c.deuda_total > 0 ? 'gasto-kpi-total' : ''}"><div class="gasto-kpi-label">Deuda a la fecha</div>
            <div class="gasto-kpi-valor" style="color:var(--${c.deuda_total > 0 ? 'danger' : 'success'})">${fmtMoneda(c.deuda_total)}</div>
            <div class="gasto-kpi-sub">${c.deuda_anterior > 0 ? 'incluye ' + fmtMoneda(c.deuda_anterior) + ' de años anteriores' : 'cuotas vencidas sin pagar'}</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Pagado en ${c.anio}</div>
            <div class="gasto-kpi-valor">${fmtMoneda(c.pagado)}</div><div class="gasto-kpi-sub">${c.pagos.length} pago(s) registrados</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Saldo de la tarjeta</div>
            <div class="gasto-kpi-valor">${fmtMoneda(t.saldo)}</div><div class="gasto-kpi-sub">para fotocopias y compras</div></div>`;
}

function irTab(tab) {
    tabActual = tab;
    document.querySelectorAll('.p-tabs .cuota-tab').forEach(b => b.classList.toggle('activo', b.dataset.tab === tab));
    if (!datosHijo) return;
    ({ cuotas: tabCuotas, tarjeta: tabTarjeta, cupones: tabCupones, datos: tabDatos, consultas: tabConsultas })[tab]();
}

// Medios de pago del reporte de cobranzas SIRO, con nombres que entiendan las familias
const CANALES = { LK: 'Red Link', PF: 'Pago Fácil', RP: 'Rapipago', TQR: 'Pago con QR', BPC: 'Pago Mis Cuentas (Banelco)',
    PC: 'Pago Mis Cuentas', PMC: 'Pago Mis Cuentas', CE: 'Cobro Express', BP: 'Bapro Pagos', DEB: 'Débito automático' };
function nombreCanal(p) {
    if (p.via === 'efectivo') return 'Efectivo en la Asociación';
    return CANALES[(p.canal || '').toUpperCase()] || (p.canal ? 'Pago SIRO (' + p.canal + ')' : 'Pago registrado');
}

function tabCuotas() {
    const c = datosHijo.cuotas, a = datosHijo.alumno;
    const pagos = c.pagos.map(p => `<li><div><b>${fmtFecha(p.fecha)}</b><div class="p-sec">${escapeHtml(nombreCanal(p))}</div></div>
        <span class="p-monto pos">${fmtMoneda(p.importe)}</span></li>`).join('');
    $('p-tab').innerHTML = `
        <div class="card p-codigo">
            <div><div class="gasto-kpi-label">Código de pago del alumno (SIRO)</div>
                <div class="p-codigo-num" id="cod-pago">${escapeHtml(a.codigo_pago)}</div>
                <div class="muted">Usalo en Pago Mis Cuentas, Link, Pago Fácil o Rapipago si no tenés el cupón.</div></div>
            <button class="btn btn-outline" onclick="copiar('${escapeHtml(a.codigo_pago)}')"><svg class="ic"><use href="#i-copy"/></svg>Copiar código</button>
        </div>
        ${c.curso ? `<div class="card"><h3>Valores ${c.anio} · ${escapeHtml(c.curso.nombre)}</h3>
            <dl class="p-datos">
                <div><dt>Cuota mensual</dt><dd>${fmtMoneda(c.curso.cuota)}</dd></div>
                <div><dt>Cantidad de cuotas</dt><dd>${c.curso.n_cuotas}</dd></div>
                <div><dt>Matrícula</dt><dd>${c.curso.matricula ? fmtMoneda(c.curso.matricula) : '—'}</dd></div>
                <div><dt>Vencido a la fecha</dt><dd>${fmtMoneda(c.esperado)}</dd></div>
            </dl>
            <p class="muted" style="margin-top:0.75rem">La deuda es lo vencido (matrícula + cuotas hasta el mes anterior) menos lo pagado.
            Los pagos pueden demorar 48 a 72 horas hábiles en aparecer.</p></div>` : ''}
        <div class="card"><h3>Pagos registrados en ${c.anio}</h3>
            ${pagos ? `<ul class="p-lista">${pagos}</ul>` : '<p class="p-vacio">Todavía no hay pagos registrados este año.</p>'}
            <button class="btn btn-ghost" onclick="nuevaConsulta('pago_no_registrado')">¿Falta un pago? Avisanos</button></div>`;
}

function tabTarjeta() {
    const t = datosHijo.tarjeta;
    const etiqueta = { recarga: 'Recarga', consumo: 'Consumo', reintegro: 'Reintegro', transferencia_in: 'Transferencia recibida', transferencia_out: 'Transferencia enviada' };
    const filas = t.movimientos.map(m => `<li><div><b>${escapeHtml(etiqueta[m.tipo] || m.tipo)}</b>
        <div class="p-sec">${fmtFechaHora(m.fecha)}${m.descripcion ? ' · ' + escapeHtml(m.descripcion) : ''}</div></div>
        <span class="p-monto ${m.monto >= 0 ? 'pos' : 'neg'}">${fmtMoneda(m.monto)}</span></li>`).join('');
    $('p-tab').innerHTML = `<div class="card"><h3>Saldo actual: ${fmtMoneda(t.saldo)}</h3>
        <p class="muted">Últimos movimientos de la tarjeta APAI (fecha y hora de Argentina).</p>
        ${filas ? `<ul class="p-lista">${filas}</ul>` : '<p class="p-vacio">Todavía no hay movimientos.</p>'}
        <button class="btn btn-ghost" onclick="nuevaConsulta('tarjeta')">¿Perdiste la tarjeta o ves algo raro? Avisanos</button></div>`;
}

function tabCupones() {
    const lista = datosHijo.cupones.map(c => `<li><div><b>${escapeHtml(c.concepto || (c.tipo === 'cuota' ? 'Cuota' : 'Recarga'))}</b>
        <div class="p-sec">Generado el ${fmtFechaHora(c.fecha)}</div></div>
        <div style="display:flex;align-items:center;gap:0.6rem"><span class="p-monto">${fmtMoneda(c.monto)}</span>
        ${c.url ? `<a class="btn btn-primary btn-sm" href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer">Abrir cupón</a>` : ''}</div></li>`).join('');
    $('p-tab').innerHTML = `<div class="card"><h3>Cupones de pago</h3>
        <p class="muted">Acá quedan todos los cupones que te enviamos por correo, por si no te llegó o lo perdiste.</p>
        ${lista ? `<ul class="p-lista">${lista}</ul>` : `<p class="p-vacio">Todavía no hay cupones generados para este alumno.<br>
            Podés pagar con el código <b>${escapeHtml(datosHijo.alumno.codigo_pago)}</b> (pestaña «Cuotas y pagos»).</p>`}
        <button class="btn btn-ghost" onclick="nuevaConsulta('reenvio_cupon')">Necesito un cupón</button></div>`;
}

function tabDatos() {
    const a = datosHijo.alumno;
    const d = (t, v) => `<div><dt>${t}</dt><dd>${escapeHtml(v || '—')}</dd></div>`;
    $('p-tab').innerHTML = `<div class="card"><h3>${escapeHtml(a.apellido)}, ${escapeHtml(a.nombre)}</h3>
        <dl class="p-datos">${d('Legajo', a.legajo)}${d('DNI', a.dni)}${d('Curso', a.curso)}${d('División', a.division)}
            ${d('Área', a.area)}${d('Condición', a.condicion)}${d('Modalidad', a.modalidad)}
            ${d('Fecha de nacimiento', a.fecha_nacimiento ? fmtFecha(a.fecha_nacimiento) : '')}${d('Correo de la familia', a.email)}${d('Teléfono', a.telefono)}</dl>
        <button class="btn btn-outline" style="margin-top:1rem" onclick="nuevaConsulta('datos')">Pedir una corrección de datos</button></div>
        <div class="card"><h3>Tu cuenta</h3><p class="muted">Ingresás con <b>${escapeHtml(yo.email)}</b>.</p>
        <button class="btn btn-ghost" onclick="cambiarMiClave()"><svg class="ic"><use href="#i-lock"/></svg>Cambiar mi contraseña</button></div>`;
}

function cambiarMiClave() {
    abrirModal(`<h3>Cambiar contraseña</h3>
        <label class="mc-lbl" for="m-act">Contraseña actual</label><input type="password" id="m-act" class="mc-inp" autocomplete="current-password">
        <label class="mc-lbl" for="m-nue">Contraseña nueva (8+ caracteres, letras y números)</label><input type="password" id="m-nue" class="mc-inp" autocomplete="new-password">
        <div class="form-actions"><button class="btn btn-primary" onclick="confirmarMiClave()">Guardar</button>
        <button class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button></div>`);
}
async function confirmarMiClave() {
    try {
        await api('/api/portal/cambiar-password', { method: 'POST', body: JSON.stringify({ password_actual: $('m-act').value, password_nueva: $('m-nue').value }) });
        cerrarModal(); toast('Contraseña actualizada');
    } catch (err) { toast(err.message, 'error'); }
}

function copiar(t) { navigator.clipboard.writeText(t).then(() => toast('Código copiado')); }

// ---------------------------------------------------------------- consultas
async function tabConsultas() {
    $('p-tab').innerHTML = `<div class="card"><h3>¿En qué te podemos ayudar?</h3>
        <p class="muted">Elegí un tema: primero te mostramos las respuestas a las dudas más comunes.</p>
        <div class="p-cats">${categorias.map(c => `<button class="p-cat" onclick="nuevaConsulta('${c.id}')"><b>${escapeHtml(c.titulo)}</b><span>${escapeHtml(c.desc)}</span></button>`).join('')}</div></div>
        <div class="card"><h3>Mis consultas</h3><div id="p-mis-consultas"><p class="muted">Cargando…</p></div></div>`;
    try {
        const lista = await api('/api/portal/consultas');
        const etq = { abierta: '<span class="badge">Esperando respuesta</span>', respondida: '<span class="badge badge-activa">Respondida</span>', cerrada: '<span class="badge">Cerrada</span>' };
        $('p-mis-consultas').innerHTML = lista.length ? `<ul class="p-lista">${lista.map(x => `
            <li class="p-consulta" onclick="abrirConsulta(${x.id})" tabindex="0" role="button">
                <div><b>${x.sin_leer ? '● ' : ''}${escapeHtml(x.asunto)}</b>
                <div class="p-sec">${escapeHtml(x.categoria_titulo)}${x.alumno ? ' · ' + escapeHtml(x.alumno) : ''} · ${fmtFechaHora(x.actualizada)}</div></div>
                ${etq[x.estado] || ''}</li>`).join('')}</ul>` : '<p class="p-vacio">Todavía no hiciste consultas.</p>';
    } catch (err) { toast(err.message, 'error'); }
}

function nuevaConsulta(catId) {
    const c = categorias.find(x => x.id === catId);
    if (!c) return;
    abrirModal(`<h3>${escapeHtml(c.titulo)}</h3>
        ${c.ayuda.length ? `<p class="muted">Antes de escribir, fijate si esto resuelve tu duda:</p>
        <ul class="p-sugerencias">${c.ayuda.map(t => `<li><svg class="ic"><use href="#i-check"/></svg><span>${escapeHtml(t)}</span></li>`).join('')}</ul>
        <div class="form-actions" id="cq-preg">
            <button class="btn btn-ghost" onclick="cerrarModal();toast('¡Genial! Cualquier cosa, escribinos.')">Listo, se resolvió</button>
            <button class="btn btn-primary" onclick="formConsulta('${c.id}')">No, quiero escribir</button></div>` : ''}
        <div id="cq-form"></div>`);
    if (!c.ayuda.length) formConsulta(c.id);
}

function formConsulta(catId) {
    const c = categorias.find(x => x.id === catId);
    const preg = $('cq-preg'); if (preg) preg.remove();
    const opciones = yo.hijos.map(h => `<option value="${h.id}" ${h.id === hijoId ? 'selected' : ''}>${escapeHtml(h.apellido)}, ${escapeHtml(h.nombre)}</option>`).join('');
    const sugerencia = { informar_pago: 'Ej: pagué $45.000 por transferencia el 05/10 (cuota de octubre).',
        pago_no_registrado: 'Indicá fecha, importe y medio de pago.', datos: 'Indicá qué dato está mal y cuál es el correcto.' }[catId] || '';
    $('cq-form').innerHTML = `
        <label class="mc-lbl" for="cq-alumno">Alumno</label>
        <select id="cq-alumno" class="mc-inp">${opciones}<option value="">(no es sobre un alumno en particular)</option></select>
        <label class="mc-lbl" for="cq-asunto">Asunto</label>
        <input id="cq-asunto" class="mc-inp" maxlength="150" value="${escapeHtml(c.titulo)}">
        <label class="mc-lbl" for="cq-texto">Mensaje</label>
        <textarea id="cq-texto" class="mc-inp" rows="5" maxlength="4000" placeholder="${escapeHtml(sugerencia)}"></textarea>
        ${c.comprobante ? `<label class="mc-lbl" for="cq-archivo">Comprobante (foto o PDF, opcional)</label>
            <input type="file" id="cq-archivo" accept="image/*,.pdf">` : ''}
        <div class="form-actions"><button class="btn btn-primary" id="cq-enviar" onclick="enviarConsulta('${catId}')">Enviar consulta</button>
            <button class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button></div>`;
    $('cq-texto').focus();
}

async function subirAdjunto(file) {
    const firma = await api('/api/portal/adjunto-firma', { method: 'POST', body: JSON.stringify({ nombre: file.name, tamanio: file.size }) });
    const up = await fetch(firma.upload_url, { method: 'PUT', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file });
    if (!up.ok) throw new Error('No se pudo subir el comprobante. Probá con una foto más liviana.');
    return firma.public_url;
}

async function enviarConsulta(catId) {
    const btn = $('cq-enviar'); btn.disabled = true; btn.textContent = 'Enviando…';
    try {
        let adjunto = null;
        const f = $('cq-archivo') && $('cq-archivo').files[0];
        if (f) adjunto = await subirAdjunto(f);
        const alumno = $('cq-alumno').value;
        const r = await api('/api/portal/consultas', { method: 'POST', body: JSON.stringify({
            categoria: catId, alumno_id: alumno ? Number(alumno) : null, asunto: $('cq-asunto').value, texto: $('cq-texto').value, adjunto_url: adjunto }) });
        cerrarModal(); toast(r.mensaje);
        irTab('consultas');
    } catch (err) { toast(err.message, 'error'); btn.disabled = false; btn.textContent = 'Enviar consulta'; }
}

async function abrirConsulta(id) {
    try {
        const x = await api(`/api/portal/consultas/${id}`);
        abrirModal(`<h3>${escapeHtml(x.asunto)}</h3>
            <p class="muted" style="margin-top:-0.4rem">${escapeHtml(x.categoria_titulo)}${x.alumno ? ' · ' + escapeHtml(x.alumno) : ''}</p>
            <div class="p-hilo">${x.mensajes.map(m => `<div class="p-msj ${m.autor === 'padre' ? 'yo' : 'ellos'}"><div class="cq-txt">${escapeHtml(m.texto)}</div>
                ${m.adjunto_url ? `<br><a href="${escapeHtml(m.adjunto_url)}" target="_blank" rel="noopener noreferrer">Ver comprobante</a>` : ''}
                <small>${m.autor === 'padre' ? 'Vos' : escapeHtml(m.autor_nombre)} · ${fmtFechaHora(m.fecha)}</small></div>`).join('')}</div>
            ${x.estado === 'cerrada' ? '<p class="muted">Esta consulta está cerrada. Si necesitás algo más, podés escribir igual y se vuelve a abrir.</p>' : ''}
            <label class="mc-lbl" for="cr-texto">Responder</label>
            <textarea id="cr-texto" class="mc-inp" rows="3" maxlength="4000"></textarea>
            <div class="form-actions"><button class="btn btn-primary" onclick="responderConsulta(${x.id})">Enviar</button>
                <button class="btn btn-ghost" onclick="cerrarModal()">Cerrar</button></div>`);
        const me = await api('/api/portal/me'); actualizarBadge(me.consultas_sin_leer);
    } catch (err) { toast(err.message, 'error'); }
}

async function responderConsulta(id) {
    const texto = $('cr-texto').value.trim();
    if (!texto) return toast('Escribí un mensaje', 'error');
    try {
        await api(`/api/portal/consultas/${id}/mensajes`, { method: 'POST', body: JSON.stringify({ texto }) });
        toast('Mensaje enviado'); abrirConsulta(id);
    } catch (err) { toast(err.message, 'error'); }
}

// ---------------------------------------------------------------- inicio
(async function iniciar() {
    const params = new URLSearchParams(location.search);
    resetToken = params.get('reset');
    if (resetToken) { history.replaceState(null, '', '/portal'); return mostrarClave(true); }
    try { await cargarApp(); } catch { /* sin sesión: queda el login */ }
})();
