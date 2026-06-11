const API = '';
let alumnosCache = [];

// Escapa texto para insertarlo de forma segura en HTML (previene XSS)
function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// --- Navegacion ---
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('sec-' + btn.dataset.section).classList.add('active');
    });
});

// --- Toast ---
function toast(msg, tipo = 'success') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast ' + tipo + ' show';
    setTimeout(() => el.classList.remove('show'), 4000);
}

// --- Modal ---
function cerrarModal() {
    document.getElementById('modal-overlay').style.display = 'none';
}

// --- API helpers ---
async function api(url, opts = {}) {
    const res = await fetch(API + url, {
        headers: { 'Content-Type': 'application/json', ...opts.headers },
        credentials: 'same-origin',
        ...opts,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Error del servidor');
    return data;
}

// =========================================================
// --- BUSCADOR DE ALUMNOS (autocomplete reutilizable) ---
// =========================================================

const buscadores = {};

function crearBuscador(config) {
    // config: { inputId, hiddenId, dropId, wrapId, onSelect, mostrarSaldo }
    const input = document.getElementById(config.inputId);
    const hidden = document.getElementById(config.hiddenId);
    const drop = document.getElementById(config.dropId);
    const wrap = document.getElementById(config.wrapId);
    const clearBtn = wrap.querySelector('.buscador-clear');
    let indiceActivo = -1;

    const estado = { alumnoId: null };
    buscadores[config.hiddenId] = estado;

    function filtrar(texto) {
        if (!texto || texto.length < 1) return [];
        const t = texto.toLowerCase();
        return alumnosCache.filter(a =>
            a.apellido.toLowerCase().includes(t) ||
            a.nombre.toLowerCase().includes(t) ||
            a.legajo.toLowerCase().includes(t) ||
            a.dni.toLowerCase().includes(t)
        ).slice(0, 15);
    }

    function renderDrop(lista) {
        if (lista.length === 0) {
            drop.innerHTML = '<div class="buscador-vacio">Sin resultados</div>';
            drop.classList.add('visible');
            return;
        }
        drop.innerHTML = lista.map((a, i) => {
            const saldo = Number(a.saldo);
            const saldoColor = saldo > 0 ? '#16a34a' : '#ef4444';
            const saldoHtml = config.mostrarSaldo !== false
                ? `<span class="buscador-saldo" style="color:${saldoColor}">$${saldo.toLocaleString('es-AR', {minimumFractionDigits:2})}</span>`
                : '';
            return `<div class="buscador-item" data-index="${i}" data-id="${a.id}">
                <div>
                    <span class="buscador-nombre">${escapeHtml(a.apellido)}, ${escapeHtml(a.nombre)}</span>
                    <span class="buscador-detalle"> - ${escapeHtml(a.legajo)} - ${escapeHtml(a.curso)}</span>
                </div>
                ${saldoHtml}
            </div>`;
        }).join('');
        drop.classList.add('visible');
        indiceActivo = -1;
    }

    function seleccionar(alumno) {
        estado.alumnoId = alumno.id;
        hidden.value = alumno.id;
        input.value = `${alumno.apellido}, ${alumno.nombre} (${alumno.legajo})`;
        drop.classList.remove('visible');
        wrap.classList.add('seleccionado', 'tiene-valor');
        if (config.onSelect) config.onSelect(alumno);
    }

    function limpiar() {
        estado.alumnoId = null;
        hidden.value = '';
        input.value = '';
        drop.classList.remove('visible');
        wrap.classList.remove('seleccionado', 'tiene-valor');
        indiceActivo = -1;
        if (config.onClear) config.onClear();
    }

    input.addEventListener('input', function() {
        if (wrap.classList.contains('seleccionado')) {
            // El usuario esta editando despues de haber seleccionado -> limpiar seleccion
            estado.alumnoId = null;
            hidden.value = '';
            wrap.classList.remove('seleccionado');
            if (config.onClear) config.onClear();
        }
        const texto = this.value.trim();
        if (texto.length >= 1) {
            wrap.classList.add('tiene-valor');
            const resultados = filtrar(texto);
            renderDrop(resultados);
        } else {
            drop.classList.remove('visible');
            wrap.classList.remove('tiene-valor');
        }
    });

    input.addEventListener('keydown', function(e) {
        const items = drop.querySelectorAll('.buscador-item');
        if (!drop.classList.contains('visible') || items.length === 0) {
            if (e.key === 'Enter') e.preventDefault();
            return;
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            indiceActivo = Math.min(indiceActivo + 1, items.length - 1);
            items.forEach((it, i) => it.classList.toggle('activo', i === indiceActivo));
            items[indiceActivo].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            indiceActivo = Math.max(indiceActivo - 1, 0);
            items.forEach((it, i) => it.classList.toggle('activo', i === indiceActivo));
            items[indiceActivo].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (indiceActivo >= 0 && indiceActivo < items.length) {
                const id = parseInt(items[indiceActivo].dataset.id);
                const alumno = alumnosCache.find(a => a.id === id);
                if (alumno) seleccionar(alumno);
            }
        } else if (e.key === 'Escape') {
            drop.classList.remove('visible');
        }
    });

    drop.addEventListener('click', function(e) {
        const item = e.target.closest('.buscador-item');
        if (!item) return;
        const id = parseInt(item.dataset.id);
        const alumno = alumnosCache.find(a => a.id === id);
        if (alumno) seleccionar(alumno);
    });

    clearBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        limpiar();
        input.focus();
    });

    // Cerrar dropdown al hacer click fuera
    document.addEventListener('click', function(e) {
        if (!wrap.contains(e.target)) {
            drop.classList.remove('visible');
        }
    });

    return { seleccionar, limpiar, estado };
}

// --- ALUMNOS ---
async function cargarAlumnos() {
    alumnosCache = await api('/api/alumnos/');
    poblarFiltroCursos();
    poblarCursosCuota();
    filtrarAlumnos();
    if (typeof dashKPIs === 'function') dashKPIs();
}

function poblarFiltroCursos() {
    const cursos = [...new Set(alumnosCache.map(a => a.curso))].sort();
    const sel = document.getElementById('filtro-curso');
    sel.innerHTML = '<option value="">Todos los cursos</option>' +
        cursos.map(c => `<option value="${c}">${c}</option>`).join('');
}

function filtrarAlumnos() {
    const busq = document.getElementById('buscar-alumno').value.toLowerCase();
    const curso = document.getElementById('filtro-curso').value;
    const filtrados = alumnosCache.filter(a => {
        const matchBusq = !busq || [a.nombre, a.apellido, a.legajo, a.dni]
            .some(v => v.toLowerCase().includes(busq));
        const matchCurso = !curso || a.curso === curso;
        return matchBusq && matchCurso;
    });
    // Ordenar
    const campo = ordenActual.campo;
    const dir = ordenActual.asc ? 1 : -1;
    filtrados.sort((a, b) => {
        let va = a[campo];
        let vb = b[campo];
        if (campo === 'saldo') {
            return (Number(va) - Number(vb)) * dir;
        }
        va = String(va).toLowerCase();
        vb = String(vb).toLowerCase();
        return va.localeCompare(vb) * dir;
    });
    renderAlumnos(filtrados);
}

function renderAlumnos(lista) {
    document.getElementById('body-alumnos').innerHTML = lista.map(a => {
        const saldo = Number(a.saldo);
        const clsSaldo = saldo > 0 ? 'saldo-positivo' : 'saldo-cero';
        return `<tr>
            <td>${escapeHtml(a.legajo)}</td>
            <td>${escapeHtml(a.dni)}</td>
            <td>${escapeHtml(a.apellido)}</td>
            <td>${escapeHtml(a.nombre)}</td>
            <td>${escapeHtml(a.curso)}</td>
            <td>${escapeHtml(a.area || '-')}${a.cuota_excluir ? ' <span title="Excluido de la cuota">🚫</span>' : (a.cuota_personalizada ? ' <span title="Paga un monto de cuota distinto">💲</span>' : '')}</td>
            <td class="${clsSaldo}">$${saldo.toLocaleString('es-AR', {minimumFractionDigits: 2})}</td>
            <td>
                <button class="btn btn-sm" onclick="verAlumno(${a.id})">Ver</button>
                <button class="btn btn-sm" onclick="editarAlumno(${a.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="eliminarAlumno(${a.id})">Eliminar</button>
            </td>
        </tr>`;
    }).join('');
}

document.getElementById('buscar-alumno').addEventListener('input', filtrarAlumnos);
document.getElementById('filtro-curso').addEventListener('change', filtrarAlumnos);

// --- ORDENAR TABLA ALUMNOS ---
let ordenActual = { campo: 'apellido', asc: true };

function ordenarAlumnos(campo) {
    if (ordenActual.campo === campo) {
        ordenActual.asc = !ordenActual.asc;
    } else {
        ordenActual.campo = campo;
        ordenActual.asc = true;
    }
    // Actualizar indicadores en headers
    document.querySelectorAll('#tabla-alumnos th[data-campo]').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (th.dataset.campo === campo) {
            th.classList.add(ordenActual.asc ? 'sorted-asc' : 'sorted-desc');
        }
    });
    filtrarAlumnos();
}

function mostrarFormAlumno() {
    document.getElementById('form-alumno').style.display = 'block';
    document.getElementById('form-alumno-titulo').textContent = 'Nuevo Alumno';
    document.getElementById('alumno-edit-id').value = '';
    ['al-legajo', 'al-dni', 'al-nombre', 'al-apellido', 'al-curso', 'al-email', 'al-area', 'al-cuota-personalizada'].forEach(id =>
        document.getElementById(id).value = ''
    );
    document.getElementById('al-cuota-excluir').checked = false;
}

function cerrarFormAlumno() {
    document.getElementById('form-alumno').style.display = 'none';
}

function editarAlumno(id) {
    const a = alumnosCache.find(x => x.id === id);
    if (!a) return;
    document.getElementById('form-alumno').style.display = 'block';
    document.getElementById('form-alumno-titulo').textContent = 'Editar Alumno';
    document.getElementById('alumno-edit-id').value = id;
    document.getElementById('al-legajo').value = a.legajo;
    document.getElementById('al-dni').value = a.dni;
    document.getElementById('al-nombre').value = a.nombre;
    document.getElementById('al-apellido').value = a.apellido;
    document.getElementById('al-curso').value = a.curso;
    document.getElementById('al-email').value = a.email || '';
    document.getElementById('al-area').value = a.area || '';
    document.getElementById('al-cuota-personalizada').value = a.cuota_personalizada || '';
    document.getElementById('al-cuota-excluir').checked = !!a.cuota_excluir;
}

async function guardarAlumno(e) {
    e.preventDefault();
    const editId = document.getElementById('alumno-edit-id').value;
    const body = {
        legajo: document.getElementById('al-legajo').value,
        dni: document.getElementById('al-dni').value,
        nombre: document.getElementById('al-nombre').value,
        apellido: document.getElementById('al-apellido').value,
        curso: document.getElementById('al-curso').value,
        email: document.getElementById('al-email').value || null,
        area: document.getElementById('al-area').value || null,
        cuota_excluir: document.getElementById('al-cuota-excluir').checked,
        cuota_personalizada: document.getElementById('al-cuota-personalizada').value || null,
    };
    try {
        if (editId) {
            await api(`/api/alumnos/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
            toast('Alumno actualizado');
        } else {
            await api('/api/alumnos/', { method: 'POST', body: JSON.stringify(body) });
            toast('Alumno creado');
        }
        cerrarFormAlumno();
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarAlumno(id) {
    const a = alumnosCache.find(x => x.id === id);
    const nombre = a ? `${a.apellido}, ${a.nombre}` : 'este alumno';
    if (!confirm(`ATENCION: Vas a eliminar al alumno "${nombre}" y todos sus datos (tarjetas, saldo, movimientos).\n\nEsta accion no se puede deshacer. ¿Continuar?`)) return;
    if (!confirm(`¿Estas SEGURO de eliminar a "${nombre}"?`)) return;
    try {
        await api(`/api/alumnos/${id}`, { method: 'DELETE' });
        toast(`Alumno ${nombre} eliminado`);
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarPadronCompleto() {
    if (!confirm('⚠️ ATENCIÓN: vas a eliminar TODO el padrón de alumnos y TODOS sus datos (tarjetas, saldos y movimientos).\n\nEsta acción NO se puede deshacer. ¿Continuar?')) return;
    const r = prompt('Para confirmar, escribí exactamente: ELIMINAR TODO');
    if (r !== 'ELIMINAR TODO') return toast('Cancelado (texto no coincide)', 'error');
    try {
        const res = await api('/api/alumnos/eliminar-todos', { method: 'DELETE' });
        toast(res.mensaje);
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarMovimientosAlumno(id) {
    const a = alumnosCache.find(x => x.id === id);
    const nombre = a ? `${a.apellido}, ${a.nombre}` : 'este alumno';
    if (!confirm(`Vas a eliminar TODOS los movimientos de "${nombre}". El saldo actual no cambia.\n\nEsta acción no se puede deshacer. ¿Continuar?`)) return;
    try {
        const res = await api(`/api/operaciones/historial/${id}`, { method: 'DELETE' });
        toast(res.mensaje);
        verAlumno(id);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function verAlumno(id) {
    try {
        const a = await api(`/api/alumnos/${id}`);
        const movs = await api(`/api/operaciones/historial/${id}?limite=10`);
        const tarjetas = await api(`/api/tarjetas/alumno/${id}`);

        let html = `<h3>${escapeHtml(a.apellido)}, ${escapeHtml(a.nombre)}</h3>
            <p><strong>Legajo:</strong> ${escapeHtml(a.legajo)} | <strong>DNI:</strong> ${escapeHtml(a.dni)} | <strong>Curso:</strong> ${escapeHtml(a.curso)}</p>
            <p><strong>Área:</strong> ${escapeHtml(a.area || '-')} | <strong>Email:</strong> ${a.email ? escapeHtml(a.email) : '<span style="color:#94a3b8">sin email</span>'} | <strong>Cód. SIRO:</strong> ${escapeHtml(a.codigo_siro || '-')}</p>
            <p><strong>Cuota:</strong> ${a.cuota_excluir ? '<span style="color:#a01e22">excluido (no recibe cupón)</span>' : (a.cuota_personalizada ? 'monto personalizado $' + Number(a.cuota_personalizada).toLocaleString('es-AR') : 'normal')}</p>
            <p style="font-size:1.5rem;margin:1rem 0" class="saldo-positivo"><strong>Saldo: $${Number(a.saldo).toLocaleString('es-AR', {minimumFractionDigits:2})}</strong></p>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1rem">
                <button class="btn btn-red btn-sm" onclick="generarPDFAlumno(${a.id})">📄 PDF para padres</button>
                <button class="btn btn-success btn-sm" onclick="compartirWhatsAppAlumno(${a.id})">Compartir WhatsApp</button>
                <button class="btn btn-outline btn-sm" onclick="compartirEmailAlumno(${a.id})">Enviar por Email</button>
                <button class="btn btn-danger btn-sm" onclick="eliminarMovimientosAlumno(${a.id})">🗑 Eliminar movimientos</button>
            </div>`;

        html += '<h4>Tarjetas</h4>';
        if (tarjetas.length === 0) {
            html += '<p style="color:#94a3b8">Sin tarjetas asignadas</p>';
        } else {
            html += tarjetas.map(t =>
                `<span class="badge ${t.activa ? 'badge-activa' : 'badge-inactiva'}">${escapeHtml(t.uid)} — ${t.activa ? 'Activa' : 'Inactiva'}</span> `
            ).join('');
        }

        html += '<h4 style="margin-top:1rem">Ultimos movimientos</h4>';
        if (movs.length === 0) {
            html += '<p style="color:#94a3b8">Sin movimientos</p>';
        } else {
            html += '<table><thead><tr><th>Fecha</th><th>Tipo</th><th>Monto</th><th>Descripcion</th></tr></thead><tbody>';
            html += movs.map(m => {
                const fecha = new Date(m.created_at).toLocaleString('es-AR', {hour12: false});
                const monto = Number(m.monto);
                return `<tr>
                    <td>${fecha}</td>
                    <td class="tipo-${escapeHtml(m.tipo)}">${escapeHtml(m.tipo)}</td>
                    <td class="${monto >= 0 ? 'saldo-positivo' : ''}" style="${monto < 0 ? 'color:#ef4444' : ''}">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
                    <td>${escapeHtml(m.descripcion || '')}</td>
                </tr>`;
            }).join('');
            html += '</tbody></table>';
        }

        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

// --- OPERACIONES ---
async function ejecutarRecarga(e) {
    e.preventDefault();
    const alumnoId = document.getElementById('op-recarga-alumno').value;
    if (!alumnoId) return toast('Selecciona un alumno', 'error');
    try {
        const res = await api('/api/operaciones/recarga', {
            method: 'POST',
            body: JSON.stringify({
                alumno_id: parseInt(alumnoId),
                monto: parseFloat(document.getElementById('op-recarga-monto').value),
                descripcion: document.getElementById('op-recarga-desc').value,
            }),
        });
        toast(res.mensaje + ' — Saldo: $' + Number(res.saldo_actual).toLocaleString('es-AR'));
        document.getElementById('op-recarga-monto').value = '';
        buscadorRecarga.limpiar();
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function ejecutarReintegro(e) {
    e.preventDefault();
    const alumnoId = document.getElementById('op-reintegro-alumno').value;
    if (!alumnoId) return toast('Selecciona un alumno', 'error');
    try {
        const res = await api('/api/operaciones/reintegro', {
            method: 'POST',
            body: JSON.stringify({
                alumno_id: parseInt(alumnoId),
                monto: parseFloat(document.getElementById('op-reintegro-monto').value),
            }),
        });
        toast(res.mensaje + ' — Saldo: $' + Number(res.saldo_actual).toLocaleString('es-AR'));
        document.getElementById('op-reintegro-monto').value = '';
        buscadorReintegro.limpiar();
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

const MESES_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

let cuponTipoActual = 'cuota';

function cuponTab(tipo) {
    cuponTipoActual = tipo === 'cuota' ? 'cuota' : 'recarga';
    document.getElementById('cupon-cuota').style.display = tipo === 'cuota' ? 'grid' : 'none';
    document.getElementById('cupon-recarga').style.display = tipo === 'recarga' ? 'grid' : 'none';
    document.getElementById('cupon-recargalote').style.display = tipo === 'recargalote' ? 'grid' : 'none';
    document.getElementById('tab-cuota').className = 'btn btn-sm' + (tipo === 'cuota' ? ' btn-primary' : '');
    document.getElementById('tab-recarga').className = 'btn btn-sm' + (tipo === 'recarga' ? ' btn-primary' : '');
    document.getElementById('tab-recargalote').className = 'btn btn-sm' + (tipo === 'recargalote' ? ' btn-primary' : '');
}

function poblarCursosCuota() {
    const cursos = [...new Set(alumnosCache.map(a => a.curso))].sort();
    const opts = '<option value="">Todos los cursos</option>' +
        cursos.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    const sel = document.getElementById('cuota-curso');
    if (sel) sel.innerHTML = opts;
    const sel2 = document.getElementById('rlote-curso');
    if (sel2) sel2.innerHTML = opts;
    actualizarCuotaInfo();
}

async function enviarRecargaLote() {
    const curso = document.getElementById('rlote-curso').value;
    const area = document.getElementById('rlote-area').value;
    const monto = parseFloat(document.getElementById('rlote-monto').value);
    const div = document.getElementById('cupon-resultado');
    if (!monto || monto <= 0) return toast('Ingresá el monto a recargar', 'error');
    const dest = curso || area || 'TODAS las áreas';
    if (!confirm(`Vas a enviar un cupón de recarga de $${monto.toLocaleString('es-AR')} a ${dest}. ¿Continuar?`)) return;
    try {
        const res = await api('/api/cupones/recarga-masiva', {
            method: 'POST',
            body: JSON.stringify({ curso: curso || null, area: area || null, monto }),
        });
        div.className = 'resultado';
        div.style.display = 'block';
        div.innerHTML = `<strong>${res.mensaje}</strong>` +
            (res.errores && res.errores.length ? `<br><small>${res.errores.join('<br>')}</small>` : '');
        toast(res.mensaje);
    } catch (err) {
        div.className = 'resultado error';
        div.style.display = 'block';
        div.textContent = err.message;
        toast(err.message, 'error');
    }
}

function actualizarCuotaInfo() {
    const curso = document.getElementById('cuota-curso').value;
    const area = document.getElementById('cuota-area').value;
    const elegibles = alumnosCache.filter(a =>
        (!curso || a.curso === curso) && (!area || a.area === area) && a.email && !a.cuota_excluir
    ).length;
    const excluidos = alumnosCache.filter(a =>
        (!curso || a.curso === curso) && (!area || a.area === area) && a.cuota_excluir
    ).length;
    const mes = MESES_ES[new Date().getMonth()];
    const destino = area || 'todas las áreas';
    document.getElementById('cuota-info').innerHTML =
        `Cuota de <strong>${mes}</strong> · ${elegibles} con email${excluidos ? ` · ${excluidos} excluidos` : ''} en ${destino}`;
}

async function enviarCuotaMasiva() {
    const curso = document.getElementById('cuota-curso').value;
    const area = document.getElementById('cuota-area').value;
    const monto = parseFloat(document.getElementById('cuota-monto').value);
    const div = document.getElementById('cupon-resultado');
    const mes = MESES_ES[new Date().getMonth()];
    const dest = curso || area || 'TODAS las áreas';
    if (!confirm(`Vas a enviar el cupón de la cuota de ${mes} ($${monto.toLocaleString('es-AR')}) a ${dest}. Los alumnos excluidos no lo reciben, y los que tengan monto personalizado reciben el suyo. ¿Continuar?`)) return;
    try {
        const res = await api('/api/cupones/cuota-masiva', {
            method: 'POST',
            body: JSON.stringify({ curso: curso || null, area: area || null, monto }),
        });
        div.className = 'resultado';
        div.style.display = 'block';
        div.innerHTML = `<strong>${res.mensaje}</strong>` +
            (res.errores && res.errores.length ? `<br><small>${res.errores.join('<br>')}</small>` : '');
        toast(res.mensaje);
    } catch (err) {
        div.className = 'resultado error';
        div.style.display = 'block';
        div.textContent = err.message;
        toast(err.message, 'error');
    }
}

async function enviarRecarga() {
    const alumnoId = document.getElementById('cupon-alumno').value;
    const monto = parseFloat(document.getElementById('cupon-monto').value);
    const div = document.getElementById('cupon-resultado');
    if (!alumnoId) return toast('Seleccioná un alumno', 'error');
    if (!monto || monto <= 0) return toast('Ingresá un monto válido', 'error');
    try {
        const res = await api('/api/cupones/enviar', {
            method: 'POST',
            body: JSON.stringify({ tipo: 'recarga', alumno_id: parseInt(alumnoId), monto }),
        });
        div.className = 'resultado';
        div.style.display = 'block';
        div.innerHTML = `<strong>${res.mensaje}</strong>` +
            (res.url ? `<br><a href="${res.url}" target="_blank">Ver cupón de pago</a>` : '');
        toast(res.mensaje);
    } catch (err) {
        div.className = 'resultado error';
        div.style.display = 'block';
        div.textContent = err.message;
        toast(err.message, 'error');
    }
}

async function vistaPreviaEmail() {
    const monto = cuponTipoActual === 'cuota'
        ? parseFloat(document.getElementById('cuota-monto').value)
        : parseFloat(document.getElementById('cupon-monto').value) || null;
    try {
        const res = await api('/api/cupones/preview', {
            method: 'POST',
            body: JSON.stringify({ tipo: cuponTipoActual, monto }),
        });
        const html = `
            <h3>Vista previa del email</h3>
            <p style="color:#5b6b80;font-size:0.85rem"><strong>Asunto:</strong> ${res.asunto}</p>
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:0.5rem;background:#f7f9fc">${res.html}</div>
            <p style="color:#94a3b8;font-size:0.8rem;margin-top:0.5rem">Datos de ejemplo. El cupón de pago real se adjunta cuando SIRO esté conectado.</p>`;
        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function abrirPlantillas() {
    try {
        const cfg = await api('/api/config/plantillas');
        const lbl = 'display:block;margin:0.6rem 0 0.25rem;font-size:0.85rem;color:#5b6b80;font-weight:600';
        const inp = 'width:100%;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px';
        const esc = s => (s || '').replace(/"/g, '&quot;');
        const html = `
            <h3>Plantillas de email</h3>
            <p style="color:#5b6b80;font-size:0.83rem;margin-bottom:0.5rem">
                Comodines: <code>{alumno}</code> <code>{nombre}</code> <code>{apellido}</code>
                <code>{monto}</code> <code>{legajo}</code> <code>{curso}</code>
                <code>{mes}</code> <code>{anio}</code>
            </p>
            <div style="background:#f7f9fc;border-radius:10px;padding:1rem;margin-bottom:1rem">
                <p style="font-weight:600;color:#a01e22">Cuota mensual</p>
                <label style="${lbl}">Monto de la cuota ($)</label>
                <input type="number" id="pl-cuota-monto" style="${inp}" value="${esc(cfg.cuota_monto)}">
                <label style="${lbl}">Asunto</label>
                <input type="text" id="pl-cuota-asunto" style="${inp}" value="${esc(cfg.cuota_asunto)}">
                <label style="${lbl}">Mensaje</label>
                <textarea id="pl-cuota-mensaje" style="${inp};min-height:150px;font-family:inherit;resize:vertical">${cfg.cuota_mensaje || ''}</textarea>
            </div>
            <div style="background:#f7f9fc;border-radius:10px;padding:1rem;margin-bottom:1rem">
                <p style="font-weight:600;color:#a01e22">Recarga ApaiCard</p>
                <label style="${lbl}">Asunto</label>
                <input type="text" id="pl-recarga-asunto" style="${inp}" value="${esc(cfg.recarga_asunto)}">
                <label style="${lbl}">Mensaje</label>
                <textarea id="pl-recarga-mensaje" style="${inp};min-height:150px;font-family:inherit;resize:vertical">${cfg.recarga_mensaje || ''}</textarea>
            </div>
            <button class="btn btn-primary" style="width:100%" onclick="guardarPlantillas()">Guardar plantillas</button>`;
        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function guardarPlantillas() {
    const body = {
        cuota_monto: document.getElementById('pl-cuota-monto').value,
        cuota_asunto: document.getElementById('pl-cuota-asunto').value,
        cuota_mensaje: document.getElementById('pl-cuota-mensaje').value,
        recarga_asunto: document.getElementById('pl-recarga-asunto').value,
        recarga_mensaje: document.getElementById('pl-recarga-mensaje').value,
    };
    try {
        const res = await api('/api/config/plantillas', { method: 'POST', body: JSON.stringify(body) });
        toast(res.mensaje);
        document.getElementById('cuota-monto').value = body.cuota_monto;
        cerrarModal();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function ejecutarTransferencia(e) {
    e.preventDefault();
    try {
        const res = await api('/api/operaciones/transferencia', {
            method: 'POST',
            body: JSON.stringify({
                uid_origen: document.getElementById('op-transf-origen').value,
                uid_destino: document.getElementById('op-transf-destino').value,
                monto: parseFloat(document.getElementById('op-transf-monto').value),
            }),
        });
        toast(res.mensaje);
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// Render generico de movimientos (incluye datos del alumno)
function renderMovimientos(movs) {
    document.getElementById('body-historial').innerHTML = movs.map(m => {
        const fecha = new Date(m.created_at).toLocaleString('es-AR', {hour12: false});
        const monto = Number(m.monto);
        const alumno = m.apellido ? `${escapeHtml(m.apellido)}, ${escapeHtml(m.nombre)}` : '';
        return `<tr>
            <td>${fecha}</td>
            <td>${alumno}</td>
            <td>${escapeHtml(m.curso || '')}</td>
            <td class="tipo-${escapeHtml(m.tipo)}">${escapeHtml(m.tipo)}</td>
            <td style="color:${monto >= 0 ? '#16a34a' : '#a01e22'};font-weight:600">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
            <td>${escapeHtml(m.descripcion || '')}</td>
            <td>${escapeHtml(m.operador || '')}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" style="text-align:center;color:#94a3b8">Sin movimientos</td></tr>';
}

// Por defecto: ultimos 10 movimientos del sistema
async function cargarMovimientosGenerales() {
    try {
        const movs = await api('/api/operaciones/recientes?limite=10');
        document.getElementById('hist-indicador').textContent = 'Últimos 10 movimientos del sistema';
        renderMovimientos(movs);
    } catch (err) {
        toast(err.message, 'error');
    }
}

// Todos los movimientos del dia de hoy
async function cargarHistorialDia() {
    try {
        const movs = await api('/api/operaciones/diario');
        const hoy = new Date().toLocaleDateString('es-AR');
        document.getElementById('hist-indicador').textContent =
            `Movimientos del día ${hoy} — ${movs.length} operación(es)`;
        renderMovimientos(movs);
    } catch (err) {
        toast(err.message, 'error');
    }
}

// Historial completo de un alumno (todos sus movimientos historicos)
async function cargarHistorialAlumno(alumno) {
    try {
        const movs = await api(`/api/operaciones/historial/${alumno.id}?limite=1000`);
        const enriquecidos = movs.map(m => ({
            ...m, apellido: alumno.apellido, nombre: alumno.nombre, curso: alumno.curso,
        }));
        document.getElementById('hist-indicador').textContent =
            `Historial completo de ${alumno.apellido}, ${alumno.nombre} — ${movs.length} movimiento(s)`;
        renderMovimientos(enriquecidos);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function limpiarHistorial() {
    const alumnoId = document.getElementById('hist-alumno').value;
    if (!alumnoId) return toast('Selecciona un alumno primero', 'error');
    const alumno = alumnosCache.find(a => a.id === parseInt(alumnoId));
    const nombre = alumno ? `${alumno.apellido}, ${alumno.nombre}` : 'este alumno';
    if (!confirm(`Vas a eliminar TODOS los movimientos de "${nombre}".\n\nEsta accion no se puede deshacer. ¿Continuar?`)) return;
    try {
        const res = await api(`/api/operaciones/historial/${alumnoId}`, { method: 'DELETE' });
        toast(res.mensaje);
        buscadorHist.limpiar();
        cargarMovimientosGenerales();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// --- TARJETAS ---
async function emitirTarjeta(e) {
    e.preventDefault();
    const alumnoId = document.getElementById('tj-alumno').value;
    if (!alumnoId) return toast('Selecciona un alumno', 'error');
    try {
        await api('/api/tarjetas/emitir', {
            method: 'POST',
            body: JSON.stringify({
                uid: document.getElementById('tj-uid').value,
                alumno_id: parseInt(alumnoId),
            }),
        });
        toast('Tarjeta emitida correctamente');
        document.getElementById('tj-uid').value = '';
        buscadorTjAlumno.limpiar();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function consultarTarjeta(e) {
    e.preventDefault();
    const div = document.getElementById('tj-resultado');
    try {
        const res = await api('/api/tarjetas/leer', {
            method: 'POST',
            body: JSON.stringify({ uid: document.getElementById('tj-consulta-uid').value }),
        });
        div.className = 'resultado';
        div.style.display = 'block';
        div.innerHTML = `
            <strong>${res.apellido}, ${res.nombre}</strong> — ${res.curso}<br>
            Legajo: ${res.legajo}<br>
            <span style="font-size:1.2rem" class="saldo-positivo">Saldo: $${Number(res.saldo).toLocaleString('es-AR', {minimumFractionDigits:2})}</span>
        `;
    } catch (err) {
        div.className = 'resultado error';
        div.style.display = 'block';
        div.textContent = err.message;
    }
}

async function cargarTarjetasDesactivar(alumnoId) {
    const div = document.getElementById('tj-lista-tarjetas');
    if (!alumnoId) { div.innerHTML = ''; return; }
    try {
        const tarjetas = await api(`/api/tarjetas/alumno/${alumnoId}`);
        if (tarjetas.length === 0) {
            div.innerHTML = '<p style="margin-top:1rem;color:#94a3b8">Sin tarjetas</p>';
            return;
        }
        div.innerHTML = tarjetas.map(t =>
            `<div style="display:flex;align-items:center;gap:0.5rem;margin-top:0.5rem">
                <span class="badge ${t.activa ? 'badge-activa' : 'badge-inactiva'}">${t.uid}</span>
                <span>${t.activa ? 'Activa' : 'Inactiva'}</span>
                ${t.activa ? `<button class="btn btn-danger" onclick="confirmarDesactivar(${t.id}, '${t.uid}')">Desactivar</button>` : ''}
            </div>`
        ).join('');
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function confirmarDesactivar(tarjetaId, uid) {
    if (!confirm(`Desactivar tarjeta ${uid}? El saldo del alumno no se pierde.`)) return;
    try {
        await api(`/api/tarjetas/${tarjetaId}/desactivar`, { method: 'PUT' });
        toast('Tarjeta desactivada');
        // Recargar tarjetas del alumno seleccionado
        const alumnoId = document.getElementById('tj-desact-alumno').value;
        if (alumnoId) cargarTarjetasDesactivar(alumnoId);
    } catch (err) {
        toast(err.message, 'error');
    }
}

// --- IMPORTAR EXCEL ---
async function importarExcel(e) {
    e.preventDefault();
    const file = document.getElementById('archivo-excel').files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('archivo', file);

    try {
        const res = await fetch(API + '/api/alumnos/importar', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        const div = document.getElementById('resultado-import');
        div.style.display = 'block';
        div.innerHTML = `
            <p><strong>Alumnos creados:</strong> ${data.creados}</p>
            <p><strong>Emails actualizados:</strong> ${data.actualizados || 0}</p>
            ${data.errores.length > 0 ? `<p><strong>Avisos (${data.errores.length}):</strong></p><ul>${data.errores.slice(0, 30).map(e => `<li>${e}</li>`).join('')}</ul>` : ''}
        `;
        toast(`Importación: ${data.creados} creados, ${data.actualizados || 0} emails actualizados`);
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// --- COBRAR ---
let cobroAlumnoActual = null;

async function cobroBuscar() {
    const uid = document.getElementById('cobro-uid').value.trim();
    if (!uid) return toast('Ingresa el UID de la tarjeta', 'error');
    try {
        const res = await api('/api/tarjetas/leer', {
            method: 'POST',
            body: JSON.stringify({ uid }),
        });
        cobroMostrarAlumno(res, uid);
    } catch (err) {
        toast(err.message, 'error');
        cobroOcultar();
    }
}

async function cobroSeleccionarAlumno(alumno) {
    if (!alumno) { cobroOcultar(); return; }
    try {
        const tarjetas = await api(`/api/tarjetas/alumno/${alumno.id}`);
        const activa = tarjetas.find(t => t.activa);
        const uid = activa ? activa.uid : null;
        if (!uid) {
            toast('Este alumno no tiene tarjeta activa. Emiti una desde la seccion Tarjetas.', 'error');
        }
        cobroMostrarAlumno({
            alumno_id: alumno.id,
            nombre: alumno.nombre,
            apellido: alumno.apellido,
            curso: alumno.curso,
            legajo: alumno.legajo,
            saldo: alumno.saldo,
        }, uid);
    } catch (err) {
        toast(err.message, 'error');
    }
}

function cobroMostrarAlumno(info, uid) {
    cobroAlumnoActual = info;
    document.getElementById('cobro-nombre').textContent = info.apellido + ', ' + info.nombre;
    document.getElementById('cobro-curso').textContent = info.curso;
    document.getElementById('cobro-legajo').textContent = 'Legajo: ' + info.legajo;
    const saldo = Number(info.saldo);
    document.getElementById('cobro-saldo').textContent = '$' + saldo.toLocaleString('es-AR', {minimumFractionDigits: 2});
    document.getElementById('cobro-saldo').style.color = saldo > 0 ? '#16a34a' : '#ef4444';
    document.getElementById('cobro-info').style.display = 'block';

    document.getElementById('cobro-uid-actual').value = uid || '';
    document.getElementById('cobro-alumno-id-actual').value = info.alumno_id;
    document.getElementById('cobro-monto').value = '';
    document.getElementById('cobro-desc').value = '';
    limpiarConceptos();
    document.getElementById('cobro-form-monto').style.display = 'block';
    document.getElementById('cobro-resultado').style.display = 'none';
    document.getElementById('cobro-monto').focus();
}

function cobroOcultar() {
    document.getElementById('cobro-info').style.display = 'none';
    document.getElementById('cobro-form-monto').style.display = 'none';
    document.getElementById('cobro-resultado').style.display = 'none';
    cobroAlumnoActual = null;
}

function cobroMontoRapido(monto) {
    document.getElementById('cobro-monto').value = monto;
    document.getElementById('cobro-monto').focus();
}

// --- Conceptos (etiquetas multiseleccion) ---
function toggleConcepto(btn) {
    btn.classList.toggle('chip-activo');
}
function conceptosSeleccionados() {
    return Array.from(document.querySelectorAll('#cobro-conceptos .chip-activo'))
        .map(b => b.dataset.concepto);
}
function limpiarConceptos() {
    document.querySelectorAll('#cobro-conceptos .chip-activo').forEach(b => b.classList.remove('chip-activo'));
}

async function cobroEjecutar() {
    const uid = document.getElementById('cobro-uid-actual').value;
    const monto = parseFloat(document.getElementById('cobro-monto').value);
    const descLibre = document.getElementById('cobro-desc').value.trim();
    const conceptos = conceptosSeleccionados();

    if (!monto || monto <= 0) return toast('Ingresá un monto válido', 'error');

    // Descripcion = conceptos elegidos + texto libre
    let desc = conceptos.join(' + ');
    if (descLibre) desc = desc ? `${desc} - ${descLibre}` : descLibre;
    if (!desc) desc = 'Consumo';

    if (!uid) {
        toast('Este alumno no tiene tarjeta asociada. Usa la seccion Tarjetas para emitir una.', 'error');
        return;
    }

    try {
        const res = await api('/api/operaciones/cobro', {
            method: 'POST',
            body: JSON.stringify({ uid, monto, descripcion: desc }),
        });

        document.getElementById('cobro-form-monto').style.display = 'none';
        document.getElementById('cobro-resultado').style.display = 'block';
        document.getElementById('cobro-resultado-msg').textContent = res.mensaje;
        document.getElementById('cobro-resultado-saldo').textContent =
            'Saldo restante: $' + Number(res.saldo_actual).toLocaleString('es-AR', {minimumFractionDigits: 2});

        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

function cobroNuevo() {
    cobroOcultar();
    document.getElementById('cobro-uid').value = '';
    buscadorCobro.limpiar();
    document.getElementById('cobro-uid').focus();
}

// Detecta entrada del lector RFID (HID teclado)
let cobroUidBuffer = '';
let cobroUidTimer = null;

document.getElementById('cobro-uid').addEventListener('input', function() {
    clearTimeout(cobroUidTimer);
    cobroUidBuffer = this.value.trim();
    cobroUidTimer = setTimeout(() => {
        if (cobroUidBuffer.length >= 4) {
            cobroBuscar();
        }
    }, 150);
});

document.getElementById('cobro-uid').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(cobroUidTimer);
        cobroBuscar();
    }
});

// =========================================================
// --- INICIALIZAR BUSCADORES ---
// =========================================================

const buscadorCobro = crearBuscador({
    inputId: 'cobro-alumno-buscar',
    hiddenId: 'cobro-alumno-id',
    dropId: 'drop-cobro-alumno',
    wrapId: 'wrap-cobro-alumno',
    mostrarSaldo: true,
    onSelect: (alumno) => cobroSeleccionarAlumno(alumno),
    onClear: () => cobroOcultar(),
});

const buscadorRecarga = crearBuscador({
    inputId: 'op-recarga-buscar',
    hiddenId: 'op-recarga-alumno',
    dropId: 'drop-op-recarga',
    wrapId: 'wrap-op-recarga',
    mostrarSaldo: true,
});

const buscadorReintegro = crearBuscador({
    inputId: 'op-reintegro-buscar',
    hiddenId: 'op-reintegro-alumno',
    dropId: 'drop-op-reintegro',
    wrapId: 'wrap-op-reintegro',
    mostrarSaldo: true,
});

const buscadorHist = crearBuscador({
    inputId: 'hist-buscar',
    hiddenId: 'hist-alumno',
    dropId: 'drop-hist',
    wrapId: 'wrap-hist',
    mostrarSaldo: true,
    onSelect: (alumno) => cargarHistorialAlumno(alumno),
    onClear: () => cargarMovimientosGenerales(),
});

const buscadorTjAlumno = crearBuscador({
    inputId: 'tj-alumno-buscar',
    hiddenId: 'tj-alumno',
    dropId: 'drop-tj-alumno',
    wrapId: 'wrap-tj-alumno',
    mostrarSaldo: false,
});

const buscadorTjDesact = crearBuscador({
    inputId: 'tj-desact-buscar',
    hiddenId: 'tj-desact-alumno',
    dropId: 'drop-tj-desact',
    wrapId: 'wrap-tj-desact',
    mostrarSaldo: false,
    onSelect: (alumno) => cargarTarjetasDesactivar(alumno.id),
    onClear: () => { document.getElementById('tj-lista-tarjetas').innerHTML = ''; },
});

const buscadorCupon = crearBuscador({
    inputId: 'cupon-buscar',
    hiddenId: 'cupon-alumno',
    dropId: 'drop-cupon',
    wrapId: 'wrap-cupon',
    mostrarSaldo: true,
    onSelect: (alumno) => {
        const info = document.getElementById('cupon-info');
        const email = alumno.email
            ? alumno.email
            : '<span style="color:#a01e22">sin email cargado</span>';
        info.innerHTML = `Email: <strong>${email}</strong> &nbsp;·&nbsp; Cód. SIRO: <strong>${alumno.codigo_siro || '-'}</strong>`;
    },
    onClear: () => { document.getElementById('cupon-info').innerHTML = ''; },
});

// --- SESION ---
let usuarioActual = { username: '', nombre: '' };

async function cargarUsuario() {
    try {
        const user = await api('/api/auth/me');
        usuarioActual = user;
        document.getElementById('user-nombre').textContent = user.nombre;
        if (typeof dashSaludoYFecha === 'function') dashSaludoYFecha();
    } catch {
        document.cookie = 'token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT';
        window.location.href = '/login';
    }
}

async function cerrarSesion() {
    try { await fetch('/api/auth/logout', { method: 'POST' }); } catch {}
    document.cookie = 'token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT';
    window.location.href = '/login';
}

function abrirMiCuenta() {
    const u = usuarioActual || {};
    const inicial = ((u.nombre || u.username || 'U').trim().charAt(0) || 'U').toUpperCase();
    const html = `
        <div class="mc-banner">
            <div class="mc-avatar">${escapeHtml(inicial)}</div>
            <div>
                <div class="mc-nombre">${escapeHtml(u.nombre || '')}</div>
                <div class="mc-user">@${escapeHtml(u.username || '')}</div>
            </div>
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">👤 Datos de la cuenta</div>
            <label class="mc-lbl">Nombre para mostrar</label>
            <input type="text" id="mc-nombre" class="mc-inp" value="${escapeHtml(u.nombre || '')}">
            <label class="mc-lbl">Nombre de usuario (para iniciar sesión)</label>
            <input type="text" id="mc-username" class="mc-inp" value="${escapeHtml(u.username || '')}" autocomplete="off">
            <small style="color:#94a3b8">Con este usuario vas a entrar la próxima vez.</small>
            <button class="btn btn-primary btn-3d" style="width:100%;margin-top:0.75rem" onclick="guardarCuenta()">Guardar datos</button>
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">🔒 Cambiar contraseña</div>
            <label class="mc-lbl">Contraseña actual</label>
            <input type="password" id="cp-actual" class="mc-inp" autocomplete="off">
            <label class="mc-lbl">Contraseña nueva</label>
            <input type="password" id="cp-nueva" class="mc-inp" autocomplete="off">
            <label class="mc-lbl">Repetir contraseña nueva</label>
            <input type="password" id="cp-repetir" class="mc-inp" autocomplete="off">
            <button class="btn btn-primary btn-3d" style="width:100%" onclick="guardarPassword()">Cambiar contraseña</button>
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">📧 Probar envío de email</div>
            <label class="mc-lbl">Enviar un email de prueba a</label>
            <input type="email" id="te-destino" class="mc-inp" placeholder="tucorreo@ejemplo.com" autocomplete="off">
            <button class="btn btn-outline" style="width:100%" onclick="probarEmail()">Enviar email de prueba</button>
        </div>`;
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').style.display = 'flex';
}

async function probarEmail() {
    const destino = document.getElementById('te-destino').value.trim();
    try {
        const res = await api('/api/admin/test-email', {
            method: 'POST',
            body: JSON.stringify({ destino: destino || null }),
        });
        toast(res.mensaje);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function guardarCuenta() {
    const nombre = document.getElementById('mc-nombre').value.trim();
    const username = document.getElementById('mc-username').value.trim();
    if (!nombre) return toast('El nombre para mostrar no puede estar vacío', 'error');
    if (!username || username.length < 3) return toast('El usuario debe tener al menos 3 caracteres', 'error');
    try {
        const res = await api('/api/auth/actualizar-cuenta', {
            method: 'POST',
            body: JSON.stringify({ username, nombre }),
        });
        usuarioActual = { username: res.username, nombre: res.nombre };
        document.getElementById('user-nombre').textContent = res.nombre;
        toast('Cuenta actualizada correctamente');
        cerrarModal();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function guardarPassword() {
    const actual = document.getElementById('cp-actual').value;
    const nueva = document.getElementById('cp-nueva').value;
    const repetir = document.getElementById('cp-repetir').value;
    if (!actual || !nueva) return toast('Completá todos los campos', 'error');
    if (nueva.length < 6) return toast('La nueva clave debe tener al menos 6 caracteres', 'error');
    if (nueva !== repetir) return toast('Las contraseñas nuevas no coinciden', 'error');
    try {
        await api('/api/auth/cambiar-password', {
            method: 'POST',
            body: JSON.stringify({ password_actual: actual, password_nueva: nueva }),
        });
        toast('Contraseña actualizada correctamente');
        cerrarModal();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =========================================================
// --- DASHBOARD DE INICIO ---
// =========================================================
function dashIr(seccion, callback) {
    const btn = document.querySelector(`.nav-btn[data-section="${seccion}"]`);
    if (btn) btn.click();
    if (callback === true && seccion === 'reportes' && typeof cargarReportes === 'function') {
        cargarReportes();
    }
}

function dashProx(nombre) {
    toast(`"${nombre}" estará disponible próximamente. Lo activamos en la siguiente fase.`, 'success');
}

function dashSaludoYFecha() {
    const u = usuarioActual || {};
    const nombre = (u.nombre || 'Hola').split(' ')[0];
    const hora = new Date().getHours();
    const saludo = hora < 13 ? 'Buen día' : (hora < 20 ? 'Buenas tardes' : 'Buenas noches');
    const sal = document.getElementById('dash-saludo');
    if (sal) sal.textContent = `${saludo}, ${nombre} 👋`;
    const fecha = document.getElementById('dash-fecha');
    if (fecha) {
        fecha.textContent = new Date().toLocaleDateString('es-AR', {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
        });
    }
}

async function dashKPIs() {
    const grid = document.getElementById('dash-kpis');
    if (!grid) return;
    const total = alumnosCache.length;
    const conSaldo = alumnosCache.filter(a => Number(a.saldo) > 0).length;
    const saldoTotal = alumnosCache.reduce((s, a) => s + Number(a.saldo || 0), 0);
    let movsHoy = 0;
    try {
        const hoy = await api('/api/operaciones/diario');
        movsHoy = hoy.length;
    } catch (e) { /* sin sesion o sin datos */ }
    const fmt = n => Number(n).toLocaleString('es-AR', { maximumFractionDigits: 0 });
    grid.innerHTML = `
        <div class="dash-kpi"><div class="dash-kpi-label">Saldo total en tarjetas</div>
            <div class="dash-kpi-valor">$${fmt(saldoTotal)}</div>
            <div class="dash-kpi-sub">${conSaldo} alumnos con saldo</div></div>
        <div class="dash-kpi"><div class="dash-kpi-label">Alumnos registrados</div>
            <div class="dash-kpi-valor">${fmt(total)}</div>
            <div class="dash-kpi-sub">en el padrón</div></div>
        <div class="dash-kpi"><div class="dash-kpi-label">Movimientos de hoy</div>
            <div class="dash-kpi-valor">${fmt(movsHoy)}</div>
            <div class="dash-kpi-sub">operaciones</div></div>
        <div class="dash-kpi"><div class="dash-kpi-label">Estado del sistema</div>
            <div class="dash-kpi-valor" style="color:var(--green)">●  En línea</div>
            <div class="dash-kpi-sub">conectado a la base</div></div>`;
}

function dashBuscador() {
    const inp = document.getElementById('dash-buscar');
    if (!inp) return;
    inp.addEventListener('input', () => {
        const q = inp.value.trim().toLowerCase();
        document.querySelectorAll('.dash-card').forEach(c => {
            const txt = ((c.dataset.tags || '') + ' ' + c.innerText).toLowerCase();
            c.classList.toggle('dash-oculta', q && !txt.includes(q));
        });
    });
}

// =========================================================
// --- PROVEEDORES ---
// =========================================================
let proveedoresCache = [];

async function cargarProveedores() {
    try {
        proveedoresCache = await api('/api/proveedores/');
        filtrarProveedores();
    } catch (err) {
        toast(err.message, 'error');
    }
}

function filtrarProveedores() {
    const q = (document.getElementById('buscar-proveedor').value || '').toLowerCase();
    const lista = proveedoresCache.filter(p => !q ||
        [p.razon_social, p.nombre_fantasia, p.cuit, p.rubro].some(v => (v || '').toLowerCase().includes(q)));
    renderProveedores(lista);
}

function renderProveedores(lista) {
    document.getElementById('body-proveedores').innerHTML = lista.map(p => `
        <tr>
            <td>${escapeHtml(p.cuit)}</td>
            <td>${escapeHtml(p.razon_social)}</td>
            <td>${escapeHtml(p.nombre_fantasia || '-')}</td>
            <td>${escapeHtml(p.rubro || '-')}</td>
            <td>${escapeHtml(p.contacto || p.telefono || '-')}</td>
            <td>
                <button class="btn btn-sm" onclick="editarProveedor(${p.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="eliminarProveedor(${p.id})">Eliminar</button>
            </td>
        </tr>`).join('') ||
        '<tr><td colspan="6" style="text-align:center;color:#94a3b8">Sin proveedores</td></tr>';
}

function mostrarFormProveedor() {
    document.getElementById('form-proveedor').style.display = 'block';
    document.getElementById('form-proveedor-titulo').textContent = 'Nuevo Proveedor';
    document.getElementById('prov-edit-id').value = '';
    ['prov-cuit', 'prov-razon', 'prov-fantasia', 'prov-rubro', 'prov-contacto',
        'prov-telefono', 'prov-email', 'prov-cbu', 'prov-notas'].forEach(id =>
        document.getElementById(id).value = '');
}

function cerrarFormProveedor() {
    document.getElementById('form-proveedor').style.display = 'none';
}

function editarProveedor(id) {
    const p = proveedoresCache.find(x => x.id === id);
    if (!p) return;
    document.getElementById('form-proveedor').style.display = 'block';
    document.getElementById('form-proveedor-titulo').textContent = 'Editar Proveedor';
    document.getElementById('prov-edit-id').value = id;
    document.getElementById('prov-cuit').value = p.cuit || '';
    document.getElementById('prov-razon').value = p.razon_social || '';
    document.getElementById('prov-fantasia').value = p.nombre_fantasia || '';
    document.getElementById('prov-rubro').value = p.rubro || '';
    document.getElementById('prov-contacto').value = p.contacto || '';
    document.getElementById('prov-telefono').value = p.telefono || '';
    document.getElementById('prov-email').value = p.email || '';
    document.getElementById('prov-cbu').value = p.cbu || '';
    document.getElementById('prov-notas').value = p.notas || '';
}

async function guardarProveedor(e) {
    e.preventDefault();
    const editId = document.getElementById('prov-edit-id').value;
    const body = {
        cuit: document.getElementById('prov-cuit').value,
        razon_social: document.getElementById('prov-razon').value,
        nombre_fantasia: document.getElementById('prov-fantasia').value || null,
        rubro: document.getElementById('prov-rubro').value || null,
        contacto: document.getElementById('prov-contacto').value || null,
        telefono: document.getElementById('prov-telefono').value || null,
        email: document.getElementById('prov-email').value || null,
        cbu: document.getElementById('prov-cbu').value || null,
        notas: document.getElementById('prov-notas').value || null,
    };
    try {
        if (editId) {
            await api(`/api/proveedores/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
            toast('Proveedor actualizado');
        } else {
            await api('/api/proveedores/', { method: 'POST', body: JSON.stringify(body) });
            toast('Proveedor creado');
        }
        cerrarFormProveedor();
        cargarProveedores();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarProveedor(id) {
    const p = proveedoresCache.find(x => x.id === id);
    if (!confirm(`¿Eliminar al proveedor "${p ? p.razon_social : ''}"?`)) return;
    try {
        const res = await api(`/api/proveedores/${id}`, { method: 'DELETE' });
        toast(res.mensaje);
        cargarProveedores();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =========================================================
// --- GASTOS ---
// =========================================================
let gastosCache = [];
let gastosMeta = null;
const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

function gastoFmt(n) {
    return Number(n || 0).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function gastoOpts(sel, valores, conVacio) {
    const el = document.getElementById(sel);
    if (!el) return;
    const previo = el.value;
    el.innerHTML = (conVacio ? `<option value="">${conVacio}</option>` : '') +
        valores.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('');
    if (previo) el.value = previo;
}

async function cargarGastosMeta() {
    if (gastosMeta) return;
    gastosMeta = await api('/api/gastos/meta');
    // Filtros
    gastoOpts('gasto-f-categoria', gastosMeta.categorias, 'Todas las categorías');
    // Formulario
    gastoOpts('gasto-tipo', gastosMeta.tipos_comprobante, '— tipo —');
    gastoOpts('gasto-categoria', gastosMeta.categorias, '— elegir —');
    gastoOpts('gasto-forma', gastosMeta.formas_pago, '— elegir —');
    // Filtro de mes
    const fmes = document.getElementById('gasto-f-mes');
    fmes.innerHTML = '<option value="">Todo el año</option>' +
        MESES.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('');
    // Filtro de año (año actual y 3 anteriores)
    const hoy = new Date().getFullYear();
    const fanio = document.getElementById('gasto-f-anio');
    fanio.innerHTML = '<option value="">Todos los años</option>' +
        [0, 1, 2, 3].map(d => `<option value="${hoy - d}">${hoy - d}</option>`).join('');
    fanio.value = String(hoy);
}

async function cargarGastos() {
    try {
        await cargarGastosMeta();
        if (!proveedoresCache.length) { try { proveedoresCache = await api('/api/proveedores/'); } catch (e) {} }
        const cat = document.getElementById('gasto-f-categoria').value;
        const mes = document.getElementById('gasto-f-mes').value;
        const anio = document.getElementById('gasto-f-anio').value;
        const p = new URLSearchParams();
        if (cat) p.set('categoria', cat);
        if (mes) p.set('mes', mes);
        if (anio) p.set('anio', anio);
        gastosCache = await api('/api/gastos/?' + p.toString());
        filtrarGastos();
        cargarResumenGastos(mes, anio);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function cargarResumenGastos(mes, anio) {
    try {
        const p = new URLSearchParams();
        if (mes) p.set('mes', mes);
        if (anio) p.set('anio', anio);
        const r = await api('/api/gastos/resumen?' + p.toString());
        const cont = document.getElementById('gasto-resumen');
        const cats = (r.por_categoria || []).map(c =>
            `<div class="gasto-kpi"><div class="gasto-kpi-label">${escapeHtml(c.categoria)}</div>
                <div class="gasto-kpi-valor">$${gastoFmt(c.total)}</div>
                <div class="gasto-kpi-sub">${c.cantidad} comprob.</div></div>`).join('');
        cont.innerHTML =
            `<div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Total del período</div>
                <div class="gasto-kpi-valor">$${gastoFmt(r.total)}</div>
                <div class="gasto-kpi-sub">${r.cantidad} comprobantes</div></div>` + cats;
    } catch (err) { /* sin datos */ }
}

function filtrarGastos() {
    const q = (document.getElementById('buscar-gasto').value || '').toLowerCase();
    const lista = gastosCache.filter(g => !q ||
        [g.razon_social, g.cuit, g.concepto, g.rubro, g.destino, g.numero]
            .some(v => (v || '').toLowerCase().includes(q)));
    renderGastos(lista);
}

function renderGastos(lista) {
    document.getElementById('body-gastos').innerHTML = lista.map(g => {
        const neg = Number(g.importe) < 0;
        const fecha = g.fecha ? g.fecha.split('-').reverse().join('/') : '-';
        const nc = g.nc_de_id ? ' <span class="tag-nc">NC</span>' : '';
        return `<tr>
            <td>${fecha}</td>
            <td>${escapeHtml(g.razon_social || '-')}${nc}</td>
            <td>${escapeHtml(g.concepto || '-')}</td>
            <td>${escapeHtml(g.categoria || '-')}</td>
            <td>${escapeHtml(g.forma_pago || '-')}</td>
            <td style="text-align:right;${neg ? 'color:var(--red)' : ''}">$${gastoFmt(g.importe)}</td>
            <td>
                <button class="btn btn-sm" onclick="editarGasto(${g.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="eliminarGasto(${g.id})">Eliminar</button>
            </td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:#94a3b8">Sin gastos en este período</td></tr>';
}

function gastoLlenarProveedores() {
    const sel = document.getElementById('gasto-proveedor');
    const previo = sel.value;
    const lista = (proveedoresCache || []).slice().sort((a, b) =>
        (a.razon_social || '').localeCompare(b.razon_social || ''));
    sel.innerHTML = '<option value="">— sin proveedor / cargar a mano —</option>' +
        lista.map(p => `<option value="${p.id}">${escapeHtml(p.razon_social)}${p.cuit ? ' (' + escapeHtml(p.cuit) + ')' : ''}</option>`).join('');
    if (previo) sel.value = previo;
}

function gastoProveedorElegido() {
    const id = Number(document.getElementById('gasto-proveedor').value);
    const p = (proveedoresCache || []).find(x => x.id === id);
    if (p) {
        document.getElementById('gasto-razon').value = p.razon_social || '';
        document.getElementById('gasto-cuit').value = p.cuit || '';
    }
    gastoLlenarNCde();
}

function gastoToggleNC() {
    const on = document.getElementById('gasto-es-nc').checked;
    document.getElementById('gasto-nc-wrap').style.display = on ? 'block' : 'none';
    if (on) {
        document.getElementById('gasto-tipo').value = 'Nota de Crédito';
        gastoLlenarNCde();
    }
}

function gastoLlenarNCde() {
    const sel = document.getElementById('gasto-nc-de');
    if (!sel) return;
    const cuit = (document.getElementById('gasto-cuit').value || '').replace(/\D/g, '');
    const editId = Number(document.getElementById('gasto-edit-id').value) || 0;
    const facturas = gastosCache.filter(g =>
        g.id !== editId && Number(g.importe) >= 0 &&
        (!cuit || (g.cuit || '').replace(/\D/g, '') === cuit));
    sel.innerHTML = '<option value="">— seleccionar factura del proveedor —</option>' +
        facturas.map(g => {
            const f = g.fecha ? g.fecha.split('-').reverse().join('/') : '';
            const nro = [g.punto_venta, g.numero].filter(Boolean).join('-');
            return `<option value="${g.id}">${f} · ${nro || 's/n'} · $${gastoFmt(g.importe)} · ${escapeHtml(g.concepto || '')}</option>`;
        }).join('');
}

function mostrarFormGasto() {
    document.getElementById('form-gasto').style.display = 'block';
    document.getElementById('form-gasto-titulo').textContent = 'Nuevo Gasto';
    document.getElementById('gasto-edit-id').value = '';
    ['gasto-pv', 'gasto-numero', 'gasto-razon', 'gasto-cuit', 'gasto-importe',
        'gasto-rubro', 'gasto-concepto', 'gasto-destino', 'gasto-adjunto',
        'gasto-fecha-pago', 'gasto-notas'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('gasto-fecha').value = new Date().toISOString().slice(0, 10);
    document.getElementById('gasto-tipo').value = '';
    document.getElementById('gasto-categoria').value = '';
    document.getElementById('gasto-forma').value = '';
    document.getElementById('gasto-proveedor').value = '';
    document.getElementById('gasto-es-nc').checked = false;
    document.getElementById('gasto-nc-wrap').style.display = 'none';
    gastoLlenarProveedores();
    document.getElementById('form-gasto').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cerrarFormGasto() {
    document.getElementById('form-gasto').style.display = 'none';
}

function editarGasto(id) {
    const g = gastosCache.find(x => x.id === id);
    if (!g) return;
    gastoLlenarProveedores();
    document.getElementById('form-gasto').style.display = 'block';
    document.getElementById('form-gasto-titulo').textContent = 'Editar Gasto';
    document.getElementById('gasto-edit-id').value = id;
    document.getElementById('gasto-fecha').value = g.fecha || '';
    document.getElementById('gasto-tipo').value = g.tipo_comprobante || '';
    document.getElementById('gasto-pv').value = g.punto_venta || '';
    document.getElementById('gasto-numero').value = g.numero || '';
    document.getElementById('gasto-proveedor').value = g.proveedor_id || '';
    document.getElementById('gasto-razon').value = g.razon_social || '';
    document.getElementById('gasto-cuit').value = g.cuit || '';
    document.getElementById('gasto-importe').value = g.importe;
    document.getElementById('gasto-categoria').value = g.categoria || '';
    document.getElementById('gasto-rubro').value = g.rubro || '';
    document.getElementById('gasto-forma').value = g.forma_pago || '';
    document.getElementById('gasto-fecha-pago').value = g.fecha_pago || '';
    document.getElementById('gasto-concepto').value = g.concepto || '';
    document.getElementById('gasto-destino').value = g.destino || '';
    document.getElementById('gasto-adjunto').value = g.adjunto_url || '';
    document.getElementById('gasto-notas').value = g.notas || '';
    const esNC = !!g.nc_de_id;
    document.getElementById('gasto-es-nc').checked = esNC;
    document.getElementById('gasto-nc-wrap').style.display = esNC ? 'block' : 'none';
    if (esNC) { gastoLlenarNCde(); document.getElementById('gasto-nc-de').value = g.nc_de_id; }
    document.getElementById('form-gasto').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function guardarGasto(e) {
    e.preventDefault();
    const editId = document.getElementById('gasto-edit-id').value;
    const esNC = document.getElementById('gasto-es-nc').checked;
    let importe = parseFloat(document.getElementById('gasto-importe').value);
    if (isNaN(importe)) { toast('Ingresá el importe', 'error'); return; }
    // Una nota de crédito siempre se guarda en negativo
    if (esNC) importe = -Math.abs(importe);
    const ncDe = document.getElementById('gasto-nc-de').value;
    const provId = document.getElementById('gasto-proveedor').value;
    const body = {
        fecha: document.getElementById('gasto-fecha').value,
        tipo_comprobante: document.getElementById('gasto-tipo').value || null,
        punto_venta: document.getElementById('gasto-pv').value || null,
        numero: document.getElementById('gasto-numero').value || null,
        proveedor_id: provId ? Number(provId) : null,
        razon_social: document.getElementById('gasto-razon').value || null,
        cuit: document.getElementById('gasto-cuit').value || null,
        importe: importe,
        concepto: document.getElementById('gasto-concepto').value || null,
        rubro: document.getElementById('gasto-rubro').value || null,
        categoria: document.getElementById('gasto-categoria').value || null,
        destino: document.getElementById('gasto-destino').value || null,
        forma_pago: document.getElementById('gasto-forma').value || null,
        fecha_pago: document.getElementById('gasto-fecha-pago').value || null,
        adjunto_url: document.getElementById('gasto-adjunto').value || null,
        nc_de_id: (esNC && ncDe) ? Number(ncDe) : null,
        notas: document.getElementById('gasto-notas').value || null,
    };
    try {
        if (editId) {
            await api(`/api/gastos/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
            toast('Gasto actualizado');
        } else {
            await api('/api/gastos/', { method: 'POST', body: JSON.stringify(body) });
            toast('Gasto registrado');
        }
        cerrarFormGasto();
        cargarGastos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarGasto(id) {
    const g = gastosCache.find(x => x.id === id);
    if (!confirm(`¿Eliminar este gasto${g && g.razon_social ? ' de ' + g.razon_social : ''}?`)) return;
    try {
        const res = await api(`/api/gastos/${id}`, { method: 'DELETE' });
        toast(res.mensaje);
        cargarGastos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =========================================================
// --- LIBRO DE CAJA ---
// =========================================================
let cajaCache = [];
let cajaMeta = null;

async function cargarCajaMeta() {
    if (cajaMeta) return;
    cajaMeta = await api('/api/caja/meta');
    gastoOpts('caja-tipomov', cajaMeta.tipos_movimiento, '— elegir —');
    cajaLlenarMasGastos();
    // Filtros mes/año
    const fmes = document.getElementById('caja-f-mes');
    fmes.innerHTML = '<option value="">Todo el año</option>' +
        MESES.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('');
    const hoy = new Date().getFullYear();
    const fanio = document.getElementById('caja-f-anio');
    fanio.innerHTML = '<option value="">Todos los años</option>' +
        [0, 1, 2, 3].map(d => `<option value="${hoy - d}">${hoy - d}</option>`).join('');
    fanio.value = String(hoy);
}

async function cargarCaja() {
    try {
        await cargarCajaMeta();
        const tipo = document.getElementById('caja-f-tipo').value;
        const mes = document.getElementById('caja-f-mes').value;
        const anio = document.getElementById('caja-f-anio').value;
        const p = new URLSearchParams();
        if (tipo) p.set('tipo', tipo);
        if (mes) p.set('mes', mes);
        if (anio) p.set('anio', anio);
        cajaCache = await api('/api/caja/?' + p.toString());
        filtrarCaja();
        cargarResumenCaja(mes, anio);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function cargarResumenCaja(mes, anio) {
    try {
        const p = new URLSearchParams();
        if (mes) p.set('mes', mes);
        if (anio) p.set('anio', anio);
        const r = await api('/api/caja/resumen?' + p.toString());
        document.getElementById('caja-resumen').innerHTML = `
            <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Saldo actual en caja</div>
                <div class="gasto-kpi-valor">$${gastoFmt(r.saldo_actual)}</div>
                <div class="gasto-kpi-sub">inicial: $${gastoFmt(r.saldo_inicial)}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Ingresos del período</div>
                <div class="gasto-kpi-valor" style="color:var(--green)">$${gastoFmt(r.ingresos_periodo)}</div>
                <div class="gasto-kpi-sub">${r.cantidad} movimientos</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Egresos del período</div>
                <div class="gasto-kpi-valor" style="color:var(--red)">$${gastoFmt(r.egresos_periodo)}</div>
                <div class="gasto-kpi-sub">&nbsp;</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Neto del período</div>
                <div class="gasto-kpi-valor" style="color:${r.neto_periodo < 0 ? 'var(--red)' : 'var(--green)'}">$${gastoFmt(r.neto_periodo)}</div>
                <div class="gasto-kpi-sub">ingresos − egresos</div></div>`;
    } catch (err) { /* sin datos */ }
}

function filtrarCaja() {
    const q = (document.getElementById('buscar-caja').value || '').toLowerCase();
    const lista = cajaCache.filter(m => !q ||
        [m.concepto, m.tipo_movimiento, m.notas].some(v => (v || '').toLowerCase().includes(q)));
    renderCaja(lista);
}

function renderCaja(lista) {
    document.getElementById('body-caja').innerHTML = lista.map(m => {
        const fecha = m.fecha ? m.fecha.split('-').reverse().join('/') : '-';
        const esIng = m.tipo === 'ingreso';
        return `<tr>
            <td>${fecha}</td>
            <td>${escapeHtml(m.concepto)}</td>
            <td>${escapeHtml(m.tipo_movimiento || '-')}</td>
            <td style="text-align:right;color:var(--green)">${esIng ? '$' + gastoFmt(m.monto) : ''}</td>
            <td style="text-align:right;color:var(--red)">${esIng ? '' : '$' + gastoFmt(m.monto)}</td>
            <td style="text-align:right;font-weight:700">$${gastoFmt(m.saldo)}</td>
            <td>
                <button class="btn btn-sm" onclick="editarCaja(${m.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="eliminarCaja(${m.id})">Eliminar</button>
            </td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:#94a3b8">Sin movimientos en este período</td></tr>';
}

function mostrarFormCaja(tipo) {
    document.getElementById('form-caja').style.display = 'block';
    document.getElementById('form-caja-titulo').textContent =
        tipo === 'egreso' ? 'Nuevo egreso (salida de efectivo)' : 'Nuevo ingreso (entrada de efectivo)';
    document.getElementById('caja-edit-id').value = '';
    document.getElementById('caja-tipo').value = tipo;
    ['caja-monto', 'caja-concepto', 'caja-notas'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('caja-fecha').value = new Date().toISOString().slice(0, 10);
    document.getElementById('caja-tipomov').value = '';
    document.getElementById('form-caja').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cerrarFormCaja() {
    document.getElementById('form-caja').style.display = 'none';
}

function editarCaja(id) {
    const m = cajaCache.find(x => x.id === id);
    if (!m) return;
    document.getElementById('form-caja').style.display = 'block';
    document.getElementById('form-caja-titulo').textContent =
        'Editar ' + (m.tipo === 'egreso' ? 'egreso' : 'ingreso');
    document.getElementById('caja-edit-id').value = id;
    document.getElementById('caja-tipo').value = m.tipo;
    document.getElementById('caja-fecha').value = m.fecha || '';
    document.getElementById('caja-tipomov').value = m.tipo_movimiento || '';
    document.getElementById('caja-monto').value = m.monto;
    document.getElementById('caja-concepto').value = m.concepto || '';
    document.getElementById('caja-notas').value = m.notas || '';
    document.getElementById('form-caja').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function guardarCaja(e) {
    e.preventDefault();
    const editId = document.getElementById('caja-edit-id').value;
    const monto = parseFloat(document.getElementById('caja-monto').value);
    if (isNaN(monto) || monto <= 0) { toast('Ingresá un importe válido', 'error'); return; }
    const body = {
        fecha: document.getElementById('caja-fecha').value,
        concepto: document.getElementById('caja-concepto').value,
        tipo_movimiento: document.getElementById('caja-tipomov').value || null,
        tipo: document.getElementById('caja-tipo').value,
        monto: monto,
        notas: document.getElementById('caja-notas').value || null,
    };
    try {
        if (editId) {
            await api(`/api/caja/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
            toast('Movimiento actualizado');
        } else {
            await api('/api/caja/', { method: 'POST', body: JSON.stringify(body) });
            toast('Movimiento registrado');
        }
        cerrarFormCaja();
        cargarCaja();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarCaja(id) {
    if (!confirm('¿Eliminar este movimiento de caja?')) return;
    try {
        const res = await api(`/api/caja/${id}`, { method: 'DELETE' });
        toast(res.mensaje);
        cargarCaja();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// Gastos frecuentes extra para el desplegable "+ Más gastos…"
const CAJA_EGRESO_MAS = [
    'Pago proveedor', 'Compra de materiales', 'Herramientas', 'Limpieza',
    'Servicios (luz/agua/internet)', 'Mantenimiento', 'Papelería', 'Honorarios',
    'Sueldos', 'Impuestos', 'Retiro de efectivo', 'Otro egreso',
];

function cajaLlenarMasGastos() {
    const sel = document.getElementById('caja-rap-out-mas');
    if (!sel || sel.dataset.lleno) return;
    sel.innerHTML = '<option value="">+ Más gastos…</option>' +
        CAJA_EGRESO_MAS.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
    sel.dataset.lleno = '1';
}

function cajaPreset(lado, btn, concepto) {
    document.querySelectorAll(`#caja-rap-${lado}-chips .chip`).forEach(c => c.classList.remove('chip-activo'));
    if (btn) btn.classList.add('chip-activo');
    document.getElementById(`caja-rap-${lado}-concepto`).value = concepto;
    const monto = document.getElementById(`caja-rap-${lado}-monto`);
    monto.focus();
    // Resetear el desplegable de "más gastos" si veníamos de un chip
    if (lado === 'out') document.getElementById('caja-rap-out-mas').value = '';
}

function cajaPresetSelect(sel) {
    if (!sel.value) return;
    document.querySelectorAll('#caja-rap-out-chips .chip').forEach(c => c.classList.remove('chip-activo'));
    document.getElementById('caja-rap-out-concepto').value = sel.value;
    document.getElementById('caja-rap-out-monto').focus();
}

async function cajaRapida(tipo) {
    const lado = tipo === 'ingreso' ? 'in' : 'out';
    const concepto = (document.getElementById(`caja-rap-${lado}-concepto`).value || '').trim();
    const montoEl = document.getElementById(`caja-rap-${lado}-monto`);
    const monto = parseFloat(montoEl.value);
    if (!concepto) { toast('Elegí o escribí un concepto', 'error'); return; }
    if (isNaN(monto) || monto <= 0) { toast('Ingresá un importe válido', 'error'); montoEl.focus(); return; }
    const body = {
        fecha: new Date().toISOString().slice(0, 10),
        concepto: concepto,
        tipo_movimiento: tipo === 'ingreso' ? 'Venta' : concepto,
        tipo: tipo,
        monto: monto,
    };
    try {
        await api('/api/caja/', { method: 'POST', body: JSON.stringify(body) });
        toast(`${tipo === 'ingreso' ? 'Ingreso' : 'Egreso'} de $${gastoFmt(monto)} registrado`);
        montoEl.value = '';          // se limpia el importe pero se mantiene el concepto
        montoEl.focus();             // listo para cargar el siguiente al instante
        cargarCaja();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function editarSaldoInicial() {
    try {
        const actual = await api('/api/caja/saldo-inicial');
        const v = prompt('Saldo inicial de la caja (el efectivo con el que arranca el libro):', actual.valor);
        if (v === null) return;
        const num = parseFloat(v);
        if (isNaN(num)) { toast('Importe inválido', 'error'); return; }
        await api('/api/caja/saldo-inicial', { method: 'PUT', body: JSON.stringify({ valor: num }) });
        toast('Saldo inicial actualizado');
        cargarCaja();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =========================================================
// --- CONCILIACION BANCARIA ---
// =========================================================
let concCache = [];

async function cargarConciliacion() {
    try {
        const estado = document.getElementById('conc-f-estado').value;
        const p = new URLSearchParams();
        if (estado) p.set('estado', estado);
        concCache = await api('/api/conciliacion/?' + p.toString());
        filtrarConciliacion();
        cargarResumenConc();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function cargarResumenConc() {
    try {
        const r = await api('/api/conciliacion/resumen');
        document.getElementById('conc-resumen').innerHTML = `
            <div class="gasto-kpi"><div class="gasto-kpi-label">Movimientos del banco</div>
                <div class="gasto-kpi-valor">${r.total}</div>
                <div class="gasto-kpi-sub">$${gastoFmt(r.monto_total)}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Conciliados</div>
                <div class="gasto-kpi-valor" style="color:var(--green)">${r.conciliados}</div>
                <div class="gasto-kpi-sub">cruzados con factura</div></div>
            <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Pendientes</div>
                <div class="gasto-kpi-valor">${r.pendientes}</div>
                <div class="gasto-kpi-sub">$${gastoFmt(r.monto_pendiente)} sin factura</div></div>`;
    } catch (err) { /* sin datos */ }
}

function filtrarConciliacion() {
    const q = (document.getElementById('buscar-conc').value || '').toLowerCase();
    const lista = concCache.filter(m => !q ||
        [m.cuit, m.razon_social, m.descripcion].some(v => (v || '').toLowerCase().includes(q)));
    renderConciliacion(lista);
}

function renderConciliacion(lista) {
    document.getElementById('body-conc').innerHTML = lista.map(m => {
        const fecha = m.fecha ? m.fecha.split('-').reverse().join('/') : '-';
        const tipo = m.concepto === 'F30' ? 'DEBIN' : 'Transf.';
        let estado, acciones;
        if (m.conciliado && m.gasto) {
            const g = m.gasto;
            const fg = g.fecha ? g.fecha.split('-').reverse().join('/') : '';
            const badge = m.conciliado_manual ? 'manual' : 'auto';
            estado = `<span class="conc-ok">✓ ${badge}</span> ${escapeHtml(g.razon_social || '')}
                <span style="color:var(--text-muted)">· ${escapeHtml(g.concepto || '')} · ${fg}</span>`;
            acciones = `<button class="btn btn-sm" onclick="desconciliar(${m.id})">Deshacer</button>`;
        } else {
            estado = '<span class="conc-pend">● pendiente</span>';
            acciones = `<button class="btn btn-sm btn-primary" onclick="abrirCandidatos(${m.id})">Vincular factura</button>`;
        }
        return `<tr>
            <td>${fecha}</td>
            <td>${tipo}</td>
            <td>${escapeHtml(m.cuit || '-')}</td>
            <td>${escapeHtml(m.razon_social || '—')}</td>
            <td style="text-align:right">$${gastoFmt(Math.abs(m.importe))}</td>
            <td>${estado}</td>
            <td>${acciones}</td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:#94a3b8">No hay movimientos. Subí un extracto para empezar.</td></tr>';
}

async function importarExtracto(input) {
    const file = input.files[0];
    if (!file) return;
    toast('Procesando extracto...', 'success');
    try {
        const fd = new FormData();
        fd.append('archivo', file);
        const res = await fetch(API + '/api/conciliacion/importar', {
            method: 'POST', credentials: 'same-origin', body: fd,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al importar');
        toast(`Listo: ${data.nuevos} nuevos, ${data.conciliados_automaticamente} conciliados solos, ${data.pendientes} pendientes` +
            (data.duplicados ? ` (${data.duplicados} ya estaban)` : ''), 'success');
        cargarConciliacion();
    } catch (err) {
        toast(err.message, 'error');
    } finally {
        input.value = '';  // permite volver a subir el mismo archivo
    }
}

async function reconciliarAuto() {
    try {
        const r = await api('/api/conciliacion/auto', { method: 'POST' });
        toast(`Se conciliaron ${r.conciliados} más. Quedan ${r.pendientes} pendientes.`);
        cargarConciliacion();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function abrirCandidatos(movId) {
    const mov = concCache.find(m => m.id === movId);
    try {
        const cands = await api(`/api/conciliacion/${movId}/candidatos`);
        const filas = cands.map(c => {
            const f = c.fecha ? c.fecha.split('-').reverse().join('/') : '';
            const tags = [c.coincide_cuit ? '<span class="conc-tag-ok">CUIT ✓</span>' : '',
                c.coincide_monto ? '<span class="conc-tag-ok">Importe ✓</span>' : ''].join(' ');
            return `<tr>
                <td>${f}</td>
                <td>${escapeHtml(c.razon_social || '-')}<br><small style="color:var(--text-muted)">${escapeHtml(c.concepto || '')}</small></td>
                <td>${escapeHtml(c.cuit || '-')}</td>
                <td style="text-align:right">$${gastoFmt(c.importe)}</td>
                <td>${tags}</td>
                <td><button class="btn btn-sm btn-primary" onclick="matchManual(${movId},${c.id})">Vincular</button></td>
            </tr>`;
        }).join('') ||
            '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No hay facturas con ese CUIT ni ese importe. Cargá la factura en Gastos primero.</td></tr>';
        const html = `
            <h2 style="margin-top:0">Vincular movimiento con una factura</h2>
            <p style="color:var(--text-muted);margin-top:-0.4rem">
                ${mov ? `${escapeHtml(mov.razon_social || mov.descripcion || '')} · CUIT ${escapeHtml(mov.cuit || '-')} · $${gastoFmt(Math.abs(mov.importe))}` : ''}
            </p>
            <div style="max-height:50vh;overflow:auto">
            <table><thead><tr><th>Fecha</th><th>Factura</th><th>CUIT</th><th style="text-align:right">Importe</th><th>Coincide</th><th></th></tr></thead>
            <tbody>${filas}</tbody></table>
            </div>
            <div style="margin-top:1rem;text-align:right"><button class="btn" onclick="cerrarModal()">Cerrar</button></div>`;
        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function matchManual(movId, gastoId) {
    try {
        await api(`/api/conciliacion/${movId}/match/${gastoId}`, { method: 'POST' });
        toast('Movimiento conciliado');
        cerrarModal();
        cargarConciliacion();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function desconciliar(movId) {
    if (!confirm('¿Deshacer la conciliación de este movimiento?')) return;
    try {
        await api(`/api/conciliacion/${movId}/unmatch`, { method: 'POST' });
        toast('Conciliación deshecha');
        cargarConciliacion();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// --- TEMA CLARO / OSCURO ---
function aplicarTema(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('tema', t); } catch (e) {}
    const b = document.getElementById('btn-tema');
    if (b) b.textContent = t === 'dark' ? '☀️' : '🌙';
}
function toggleTema() {
    const actual = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    aplicarTema(actual === 'dark' ? 'light' : 'dark');
    // Si estamos en Reportes, redibujar los graficos con los colores del tema
    if (document.getElementById('sec-reportes').classList.contains('active') &&
        typeof cargarReportes === 'function') {
        cargarReportes();
    }
}

// --- INIT ---
aplicarTema(localStorage.getItem('tema') || 'light');
dashSaludoYFecha();
dashBuscador();
const _bp = document.getElementById('buscar-proveedor');
if (_bp) _bp.addEventListener('input', filtrarProveedores);
const _bg = document.getElementById('buscar-gasto');
if (_bg) _bg.addEventListener('input', filtrarGastos);
const _bc = document.getElementById('buscar-caja');
if (_bc) _bc.addEventListener('input', filtrarCaja);
const _bco = document.getElementById('buscar-conc');
if (_bco) _bco.addEventListener('input', filtrarConciliacion);
cargarUsuario();
cargarAlumnos();
cargarMovimientosGenerales();
