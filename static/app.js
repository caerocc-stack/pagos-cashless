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
// Encabezado de cada pantalla: [grupo del menú, título, para qué sirve]
const PAGINAS = {
    cuotas: ['Cobranzas y alumnos', 'Cuotas y estado de cuenta', 'Pagos recibidos por SIRO, deuda de cada alumno, estadísticas y valores de cada curso.'],
    alumnos: ['Cobranzas y alumnos', 'Alumnos', 'Padrón completo: datos personales, curso, condición y saldo de la tarjeta.'],
    importar: ['Cobranzas y alumnos', 'Importar padrón', 'Cargá o actualizá alumnos desde una planilla de Excel.'],
    'cupones-siro': ['Cobranzas y alumnos', 'Cupones de pago', 'Enviá el cupón de la cuota por correo y publicá en el portal los cupones que descargás de SIRO.'],
    consultas: ['Cobranzas y alumnos', 'Consultas de familias', 'Mensajes del portal de familias y problemas reportados por el personal. Respondé desde acá.'],
    cobrar: ['Tarjeta APAI', 'Cobrar con tarjeta', 'Pasá la tarjeta por el lector o buscá al alumno por nombre, elegí el monto y cobrá.'],
    operaciones: ['Tarjeta APAI', 'Recargas y cupones', 'Recargas, reintegros, transferencias entre alumnos y envío de cupones de pago.'],
    tarjetas: ['Tarjeta APAI', 'Tarjetas', 'Emitir tarjetas nuevas, consultar una tarjeta o darla de baja.'],
    reportes: ['Tarjeta APAI', 'Consumos y reportes', 'Uso de la tarjeta por curso y por día, ranking de consumo y exportación a Excel o PDF.'],
    gastos: ['Finanzas', 'Gastos y facturas', 'Facturas de proveedores. Con una foto del QR de AFIP los datos se completan solos.'],
    proveedores: ['Finanzas', 'Proveedores', 'CUIT, rubro y datos de contacto de cada proveedor.'],
    pedidos: ['Finanzas', 'Pedidos de materiales', 'Lo que piden profesores y personal desde el formulario. Gestioná cada pedido y armá el PDF para pedir presupuestos.'],
    caja: ['Finanzas', 'Libro de caja', 'Ingresos y egresos en efectivo con el saldo siempre al día.'],
    conciliacion: ['Finanzas', 'Conciliación bancaria', 'Cruzá los pagos del extracto del banco con las facturas cargadas.'],
    horario: ['Personal', 'Control horario', 'Entradas, salidas, horas extras y liquidación mensual del personal.'],
    usuarios: ['Administración', 'Usuarios y seguridad', 'Quién puede entrar al sistema, con qué permisos, y el registro de actividad.'],
};

function mostrarSeccion(seccion) {
    const sec = document.getElementById('sec-' + seccion);
    if (!sec) return;
    document.querySelectorAll('.nav-btn').forEach(b => {
        const activo = b.dataset.section === seccion;
        b.classList.toggle('active', activo);
        if (activo) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    sec.classList.add('active');
    const info = PAGINAS[seccion];
    const head = document.getElementById('page-head');
    head.hidden = !info;
    if (info) {
        document.getElementById('page-miga').textContent = info[0];
        document.getElementById('page-titulo').textContent = info[1];
        document.getElementById('page-desc').textContent = info[2];
        document.title = `${info[1]} · APAI Pay`;
    } else {
        document.title = 'APAI Pay';
    }
    // Enlace directo (se puede guardar en favoritos y el botón "Atrás" funciona)
    const hash = seccion === 'inicio' ? '' : '#' + seccion;
    if (location.hash !== hash) history.pushState(null, '', hash || location.pathname);
    window.scrollTo({ top: 0 });
}

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => mostrarSeccion(btn.dataset.section));
});

// Abrir la sección del enlace (#gastos, #caja, ...) y responder al botón Atrás/Adelante
function irAlHash() {
    const s = location.hash.slice(1) || 'inicio';
    const btn = document.querySelector(`.nav-btn[data-section="${s}"]`);
    if (btn && !btn.classList.contains('active') && btn.style.display !== 'none') btn.click();
    else if (!btn) mostrarSeccion('inicio');
}
window.addEventListener('popstate', irAlHash);

// Esc cierra el modal abierto
document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('modal-overlay').style.display !== 'none') cerrarModal();
});

// Normaliza texto para búsquedas: minúsculas y sin acentos
function normTxt(s) {
    return (s == null ? '' : String(s)).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

const _reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// --- Config global profesional de Chart.js (aplica a TODOS los gráficos) ---
function configurarChartsGlobal() {
    if (typeof Chart === 'undefined' || Chart.__apaiConfig) return;
    Chart.__apaiConfig = true;
    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue('--text-muted').trim() || '#5b6b80';
    const border = css.getPropertyValue('--border').trim() || 'rgba(21,35,59,0.08)';
    Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = muted;
    // Ajustar propiedades sueltas: reemplazar el objeto 'animation' entero borra la configuración interna
    // de Chart.js y cada gráfico animado falla ("this._fn is not a function"), dejando TODOS en blanco.
    Chart.defaults.animation.duration = _reduceMotion ? 0 : 900;
    Chart.defaults.animation.easing = 'easeOutQuart';
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
    Chart.defaults.plugins.legend.labels.padding = 14;
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(21,35,59,0.95)';
    Chart.defaults.plugins.tooltip.padding = 11;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.plugins.tooltip.titleFont = { weight: '700', size: 12 };
    Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
    Chart.defaults.plugins.tooltip.boxPadding = 6;
    Chart.defaults.plugins.tooltip.usePointStyle = true;
    Chart.defaults.elements.bar.borderRadius = 7;
    Chart.defaults.elements.bar.borderSkipped = false;
    Chart.defaults.elements.line.tension = 0.38;
    Chart.defaults.elements.line.borderWidth = 3;
    Chart.defaults.elements.point.radius = 0;
    Chart.defaults.elements.point.hoverRadius = 6;
    Chart.defaults.elements.point.hitRadius = 12;
    Chart.defaults.elements.arc.borderWidth = 0;
    // (No se tocan los defaults de 'scale': en Chart.js v4 reemplazarlos rompe el layout de los gráficos)
}
configurarChartsGlobal();

// Crea un gradiente vertical para rellenos de gráficos
function chartGradient(ctx, area, hex, opTop = 0.85, opBot = 0.12) {
    // En el primer render el área aún no está calculada (top/bottom no-finitos): usar color sólido
    if (!area || !isFinite(area.top) || !isFinite(area.bottom)) return hex;
    const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    const h = hex.replace('#', '');
    const r = parseInt(h.slice(0, 2), 16), gg = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
    g.addColorStop(0, `rgba(${r},${gg},${b},${opTop})`);
    g.addColorStop(1, `rgba(${r},${gg},${b},${opBot})`);
    return g;
}

// Anima un número de 0 al valor final (cuenta regresiva ascendente)
function animarNumero(el, destino, { prefijo = '', sufijo = '', dec = 0, dur = 900 } = {}) {
    if (_reduceMotion) { el.textContent = prefijo + Number(destino).toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + sufijo; return; }
    const t0 = performance.now();
    function paso(t) {
        const p = Math.min(1, (t - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);  // easeOutCubic
        const val = destino * e;
        el.textContent = prefijo + val.toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + sufijo;
        if (p < 1) requestAnimationFrame(paso);
    }
    requestAnimationFrame(paso);
}

// --- Menu lateral ---
function toggleGrupo(head) {
    head.parentElement.classList.toggle('collapsed');
}
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('abierta');
    document.getElementById('side-backdrop').classList.toggle('visible');
}
function cerrarSidebarMobile() {
    document.getElementById('sidebar').classList.remove('abierta');
    document.getElementById('side-backdrop').classList.remove('visible');
}

// --- Toast ---
function toast(msg, tipo = 'success') {
    if (!msg) return;
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast ' + tipo + ' show';
    setTimeout(() => el.classList.remove('show'), 4000);
}

// --- Modal ---
function cerrarModal() {
    const ov = document.getElementById('modal-overlay');
    if (ov.dataset.bloqueado) return;
    ov.style.display = 'none';
    ov.querySelector('.modal').classList.remove('modal-ancho');
}

// --- API helpers ---
async function api(url, opts = {}) {
    const res = await fetch(API + url, {
        headers: { 'Content-Type': 'application/json', ...opts.headers },
        credentials: 'same-origin',
        ...opts,
    });
    let data = {};
    try { data = await res.json(); } catch {}
    if (res.status === 401 && !url.startsWith('/api/auth/')) {
        // Sesión vencida o cerrada desde otro lado: volver al login
        window.location.href = '/login';
        throw new Error('Sesión vencida');
    }
    if (res.status === 403 && /cambiar tu contraseña/.test(data.detail || '')) {
        abrirCambioObligatorio();
        throw new Error('');  // silencioso: el modal ya lo explica
    }
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
            const saldoColor = saldo > 0 ? 'var(--success)' : 'var(--danger)';
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
    const busq = normTxt(document.getElementById('buscar-alumno').value.trim());
    const curso = document.getElementById('filtro-curso').value;
    const terminos = busq.split(/\s+/).filter(Boolean);  // cada palabra debe aparecer
    const filtrados = alumnosCache.filter(a => {
        const texto = normTxt(`${a.apellido} ${a.nombre} ${a.legajo} ${a.dni || ''} ${a.curso || ''}`);
        const matchBusq = terminos.every(t => texto.includes(t));
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
                <button class="btn btn-sm btn-outline solo-admin" ${usuarioActual.rol === 'admin' ? '' : 'style="display:none"'} onclick="verComoFamilia(${a.id})" title="Ver como familia: abrir el portal tal cual lo ve la familia">Familia</button>
                <button class="btn btn-sm btn-danger btn-ico" onclick="eliminarAlumno(${a.id})" title="Eliminar" aria-label="Eliminar"><svg class="ic"><use href="#i-trash"/></svg></button>
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
    ['al-legajo', 'al-dni', 'al-nombre', 'al-apellido', 'al-curso', 'al-division',
        'al-email', 'al-area', 'al-telefono', 'al-fecha-nac', 'al-modalidad',
        'al-deuda-ant', 'al-cuota-personalizada'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('al-condicion').value = 'Regular';
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
    document.getElementById('al-division').value = a.division || '';
    document.getElementById('al-email').value = a.email || '';
    document.getElementById('al-area').value = a.area || '';
    document.getElementById('al-condicion').value = a.condicion || 'Regular';
    document.getElementById('al-modalidad').value = a.modalidad || '';
    document.getElementById('al-telefono').value = a.telefono || '';
    document.getElementById('al-fecha-nac').value = a.fecha_nacimiento || '';
    document.getElementById('al-deuda-ant').value = a.deuda_anio_anterior || '';
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
        division: document.getElementById('al-division').value || null,
        email: document.getElementById('al-email').value || null,
        area: document.getElementById('al-area').value || null,
        condicion: document.getElementById('al-condicion').value || null,
        modalidad: document.getElementById('al-modalidad').value || null,
        telefono: document.getElementById('al-telefono').value || null,
        fecha_nacimiento: document.getElementById('al-fecha-nac').value || null,
        deuda_anio_anterior: document.getElementById('al-deuda-ant').value || null,
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
        const [a, movs, tarjetas, cuenta, cupones] = await Promise.all([
            api(`/api/alumnos/${id}`), api(`/api/operaciones/historial/${id}?limite=10`), api(`/api/tarjetas/alumno/${id}`),
            api(`/api/cuotas/estado/${id}`).catch(() => null), api(`/api/cupones-siro/alumno/${id}`).catch(() => [])]);

        let html = `<h3>${escapeHtml(a.apellido)}, ${escapeHtml(a.nombre)}</h3>
            <p><strong>Legajo:</strong> ${escapeHtml(a.legajo)} | <strong>DNI:</strong> ${escapeHtml(a.dni)} | <strong>Curso:</strong> ${escapeHtml(a.curso)}</p>
            <p><strong>Área:</strong> ${escapeHtml(a.area || '-')} | <strong>Email:</strong> ${a.email ? escapeHtml(a.email) : '<span style="color:var(--text-muted)">sin email</span>'} | <strong>Cód. SIRO:</strong> ${escapeHtml(a.codigo_siro || '-')}</p>
            <p><strong>Cuota:</strong> ${a.cuota_excluir ? '<span style="color:var(--danger)">excluido (no recibe cupón)</span>' : (a.cuota_personalizada ? 'monto personalizado $' + Number(a.cuota_personalizada).toLocaleString('es-AR') : 'normal')}</p>
            <p style="font-size:1.5rem;margin:1rem 0" class="saldo-positivo modulo-tarjeta"><strong>Saldo: $${Number(a.saldo).toLocaleString('es-AR', {minimumFractionDigits:2})}</strong></p>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1rem">
                <button class="btn btn-red btn-sm" onclick="generarPDFAlumno(${a.id})">📄 PDF para padres</button>
                <button class="btn btn-success btn-sm" onclick="compartirWhatsAppAlumno(${a.id})">Compartir WhatsApp</button>
                <button class="btn btn-outline btn-sm" onclick="compartirEmailAlumno(${a.id})">Enviar por Email</button>
                ${usuarioActual.rol === 'admin' ? `<button class="btn btn-primary btn-sm" onclick="verComoFamilia(${a.id})">Ver como familia (portal)</button>` : ''}
                <button class="btn btn-danger btn-sm" onclick="eliminarMovimientosAlumno(${a.id})">🗑 Eliminar movimientos</button>
            </div>`;

        if (cuenta) html += htmlCuentaAlumno(cuenta, cupones);
        setTimeout(() => cargarCursosAlumno(id), 0);

        html += '<div class="modulo-tarjeta"><h4 style="margin-top:1rem">Tarjetas</h4>';
        if (tarjetas.length === 0) {
            html += '<p style="color:var(--text-muted)">Sin tarjetas asignadas</p>';
        } else {
            html += tarjetas.map(t =>
                `<span class="badge ${t.activa ? 'badge-activa' : 'badge-inactiva'}">${escapeHtml(t.uid)} — ${t.activa ? 'Activa' : 'Inactiva'}</span> `
            ).join('');
        }

        html += '<h4 style="margin-top:1rem">Ultimos movimientos</h4>';
        if (movs.length === 0) {
            html += '<p style="color:var(--text-muted)">Sin movimientos</p>';
        } else {
            html += '<table><thead><tr><th>Fecha</th><th>Tipo</th><th>Monto</th><th>Descripcion</th></tr></thead><tbody>';
            html += movs.map(m => {
                const fecha = fmtFechaHora(m.created_at);
                const monto = Number(m.monto);
                return `<tr>
                    <td>${fecha}</td>
                    <td class="tipo-${escapeHtml(m.tipo)}">${escapeHtml(m.tipo)}</td>
                    <td class="${monto >= 0 ? 'saldo-positivo' : ''}" style="${monto < 0 ? 'color:var(--danger)' : ''}">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
                    <td>${escapeHtml(m.descripcion || '')}</td>
                </tr>`;
            }).join('');
            html += '</tbody></table>';
        }
        html += '</div>';

        document.getElementById('modal-content').innerHTML = html;
        const ov = document.getElementById('modal-overlay');
        ov.querySelector('.modal').classList.add('modal-ancho');
        ov.style.display = 'flex';
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

let cuponTipoActual = 'recarga';

function cuponTab(tipo) {
    cuponTipoActual = 'recarga';
    document.getElementById('cupon-recarga').style.display = tipo === 'recarga' ? 'grid' : 'none';
    document.getElementById('cupon-recargalote').style.display = tipo === 'recargalote' ? 'grid' : 'none';
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
    const div = document.getElementById('cuota-resultado');
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
            <p style="color:var(--text-muted);font-size:0.85rem"><strong>Asunto:</strong> ${res.asunto}</p>
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:0.5rem;background:#f7f9fc">${res.html}</div>
            <p style="color:var(--text-muted);font-size:0.8rem;margin-top:0.5rem">Datos de ejemplo. El cupón de pago real se adjunta cuando SIRO esté conectado.</p>`;
        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function abrirPlantillas() {
    try {
        const cfg = await api('/api/config/plantillas');
        const lbl = 'display:block;margin:0.6rem 0 0.25rem;font-size:0.85rem;color:var(--text-muted);font-weight:600';
        const inp = 'width:100%;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px';
        const esc = s => (s || '').replace(/"/g, '&quot;');
        const html = `
            <h3>Plantillas de email</h3>
            <p style="color:var(--text-muted);font-size:0.83rem;margin-bottom:0.5rem">
                Comodines: <code>{alumno}</code> <code>{nombre}</code> <code>{apellido}</code>
                <code>{monto}</code> <code>{legajo}</code> <code>{curso}</code>
                <code>{mes}</code> <code>{anio}</code>
            </p>
            <div style="background:#f7f9fc;border-radius:10px;padding:1rem;margin-bottom:1rem">
                <p style="font-weight:600;color:var(--danger)">Cuota mensual</p>
                <label style="${lbl}">Monto de la cuota ($)</label>
                <input type="number" id="pl-cuota-monto" style="${inp}" value="${esc(cfg.cuota_monto)}">
                <label style="${lbl}">Asunto</label>
                <input type="text" id="pl-cuota-asunto" style="${inp}" value="${esc(cfg.cuota_asunto)}">
                <label style="${lbl}">Mensaje</label>
                <textarea id="pl-cuota-mensaje" style="${inp};min-height:150px;font-family:inherit;resize:vertical">${cfg.cuota_mensaje || ''}</textarea>
            </div>
            <div style="background:#f7f9fc;border-radius:10px;padding:1rem;margin-bottom:1rem">
                <p style="font-weight:600;color:var(--danger)">Recarga ApaiCard</p>
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
        const fecha = fmtFechaHora(m.created_at);
        const monto = Number(m.monto);
        const alumno = m.apellido ? `${escapeHtml(m.apellido)}, ${escapeHtml(m.nombre)}` : '';
        return `<tr>
            <td>${fecha}</td>
            <td>${alumno}</td>
            <td>${escapeHtml(m.curso || '')}</td>
            <td class="tipo-${escapeHtml(m.tipo)}">${escapeHtml(m.tipo)}</td>
            <td style="color:${monto >= 0 ? 'var(--success)' : 'var(--danger)'};font-weight:600">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
            <td>${escapeHtml(m.descripcion || '')}</td>
            <td>${escapeHtml(m.operador || '')}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">Sin movimientos</td></tr>';
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
        const hoy = fmtFecha(hoyISO());
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
            div.innerHTML = '<p style="margin-top:1rem;color:var(--text-muted)">Sin tarjetas</p>';
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

// --- IMPORTAR ALUMNOS (padrón u otros listados) ---
// El servidor reconoce las columnas y normaliza los datos; primero se muestra la vista previa y
// recién con "Importar" se guarda.
const IMP_COLUMNAS = { legajo: 'Legajo', dni: 'DNI', apellido: 'Apellido', nombre: 'Nombre', completo: 'Apellido y nombre',
    completo_nombre_primero: 'Nombre y apellido', curso: 'Curso', area: 'Área', email: 'Correo', telefono: 'Teléfono' };
const IMP_ACCIONES = { nuevo: ['Nuevo', 'badge-activa'], actualiza: ['Actualiza', 'badge-beca'], igual: ['Sin cambios', ''], error: ['No se importa', 'badge-sin'] };
let impUltima = null;

function impFormData() {
    const file = document.getElementById('archivo-excel').files[0];
    if (!file) return null;
    const fd = new FormData();
    fd.append('archivo', file);
    const curso = document.getElementById('imp-curso').value.trim();
    if (curso) fd.append('curso', curso);
    return fd;
}

async function impPost(url, fd) {
    const res = await fetch(API + url, { method: 'POST', body: fd, credentials: 'same-origin' });
    let data = {};
    try { data = await res.json(); } catch {}
    if (!res.ok) throw new Error(data.detail || 'No se pudo leer el archivo');
    return data;
}

async function impLeer() {
    const fd = impFormData();
    const vista = document.getElementById('imp-vista');
    document.getElementById('resultado-import').style.display = 'none';
    if (!fd) { vista.hidden = true; return; }
    document.getElementById('imp-zona-txt').textContent = fd.get('archivo').name;
    vista.hidden = false;
    vista.innerHTML = '<p class="muted" style="margin-top:1rem">Leyendo el listado…</p>';
    try {
        impUltima = await impPost('/api/alumnos/importar/vista', fd);
    } catch (e) {
        vista.innerHTML = `<div class="ps-aviso" style="margin-top:1rem">${escapeHtml(e.message)}</div>`;
        return;
    }
    const r = impUltima;
    document.getElementById('imp-curso-box').hidden = r.trae_curso;
    document.getElementById('imp-cursos-lista').innerHTML = r.cursos_existentes.map(c => `<option value="${escapeHtml(c)}">`).join('');
    const faltaCurso = !r.trae_curso && !document.getElementById('imp-curso').value.trim();
    const importables = r.creados + r.actualizados;
    const cols = Object.entries(r.columnas).filter(([k]) => IMP_COLUMNAS[k])
        .map(([k, v]) => `<span class="imp-col"><b>${IMP_COLUMNAS[k]}</b> ← ${escapeHtml(v)}</span>`).join('');
    vista.innerHTML = `
        <div class="imp-cols"><span class="muted">Columnas reconocidas:</span> ${cols}</div>
        ${faltaCurso ? '<div class="ps-aviso">Escribí o elegí el curso de estos alumnos para poder importarlos.</div>' : ''}
        <div class="imp-resumen">
            <div><b>${r.creados}</b><span>nuevos</span></div>
            <div><b>${r.actualizados}</b><span>se actualizan</span></div>
            <div><b>${r.sin_cambios}</b><span>sin cambios</span></div>
            <div class="${r.errores.length ? 'alerta' : ''}"><b>${r.filas.filter(f => f.accion === 'error').length}</b><span>no se importan</span></div>
        </div>
        <div class="ps-tabla"><table>
            <thead><tr><th>Fila</th><th>DNI</th><th>Apellido</th><th>Nombre</th><th>Curso</th><th>Correo</th><th>Qué pasa</th></tr></thead>
            <tbody>${r.filas.map(f => {
                const [txt, cls] = IMP_ACCIONES[f.accion] || ['', ''];
                return `<tr class="${f.accion === 'error' ? 'imp-err' : ''}">
                    <td class="num muted">${f.fila}</td><td class="num">${escapeHtml(f.dni || '—')}</td>
                    <td><b>${escapeHtml(f.apellido || '')}</b></td><td>${escapeHtml(f.nombre || '')}</td>
                    <td>${escapeHtml(f.curso || '—')}</td><td class="imp-mail">${escapeHtml(f.email || '')}</td>
                    <td><span class="badge ${cls}">${txt}</span> <small class="muted">${escapeHtml(f.detalle || '')}${f.existente ? ` · ${escapeHtml(f.existente)}` : ''}</small></td></tr>`;
            }).join('')}</tbody>
        </table></div>
        <div class="imp-acciones">
            <span class="muted">${importables ? 'Revisá la lista y confirmá.' : 'No hay cambios para importar.'}</span>
            <button type="button" class="btn btn-primary btn-3d" id="imp-confirmar" onclick="importarExcel()" ${importables && !faltaCurso ? '' : 'disabled'}>
                <svg class="ic"><use href="#i-upload"/></svg>Importar ${importables} alumno${importables === 1 ? '' : 's'}</button>
        </div>`;
    if (faltaCurso) document.getElementById('imp-curso').focus();
}

async function importarExcel() {
    const fd = impFormData();
    if (!fd) return;
    const btn = document.getElementById('imp-confirmar');
    if (btn) btn.disabled = true;
    try {
        const data = await impPost('/api/alumnos/importar', fd);
        const div = document.getElementById('resultado-import');
        div.style.display = 'block';
        div.className = 'resultado';
        div.innerHTML = `
            <p style="margin:0"><strong>${data.creados}</strong> alumno${data.creados === 1 ? '' : 's'} nuevo${data.creados === 1 ? '' : 's'} ·
            <strong>${data.actualizados}</strong> actualizado${data.actualizados === 1 ? '' : 's'}${data.cursos_sumados ? ` (${data.cursos_sumados} con un curso más)` : ''} ·
            ${data.sin_cambios} sin cambios</p>
            ${data.errores.length ? `<p style="margin:0.5rem 0 0"><strong>No se importaron (${data.errores.length}):</strong></p><ul>${data.errores.slice(0, 30).map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>` : ''}`;
        document.getElementById('imp-vista').hidden = true;
        document.getElementById('archivo-excel').value = '';
        document.getElementById('imp-zona-txt').textContent = 'Elegí otro archivo';
        document.getElementById('imp-curso-box').hidden = true;
        document.getElementById('imp-curso').value = '';
        toast(`Importación: ${data.creados} nuevos, ${data.actualizados} actualizados`);
        cargarAlumnos();
    } catch (err) {
        toast(err.message, 'error');
        if (btn) btn.disabled = false;
    }
}

(function impArrastrar() {
    const zona = document.getElementById('imp-zona');
    if (!zona) return;
    ['dragenter', 'dragover'].forEach(ev => zona.addEventListener(ev, e => { e.preventDefault(); zona.classList.add('sobre'); }));
    ['dragleave', 'drop'].forEach(ev => zona.addEventListener(ev, () => zona.classList.remove('sobre')));
    zona.addEventListener('drop', e => {
        e.preventDefault();
        if (!e.dataTransfer.files.length) return;
        const input = document.getElementById('archivo-excel');
        input.files = e.dataTransfer.files;
        impLeer();
    });
})();

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
    document.getElementById('cobro-saldo').style.color = saldo > 0 ? 'var(--success)' : 'var(--danger)';
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
            : '<span style="color:var(--danger)">sin email cargado</span>';
        info.innerHTML = `Email: <strong>${email}</strong> &nbsp;·&nbsp; Cód. SIRO: <strong>${alumno.codigo_siro || '-'}</strong>`;
    },
    onClear: () => { document.getElementById('cupon-info').innerHTML = ''; },
});

// --- SESION ---
let usuarioActual = { username: '', nombre: '', rol: '' };

async function cargarUsuario() {
    try {
        const user = await api('/api/auth/me');
        usuarioActual = user;
        document.getElementById('user-nombre').textContent = user.nombre;
        document.getElementById('user-rol').textContent = user.rol_nombre || '';
        document.getElementById('user-avatar').textContent = ((user.nombre || 'U').trim()[0] || 'U').toUpperCase();
        const esAdmin = user.rol === 'admin';
        document.body.classList.toggle('rol-lectura', !esAdmin);
        document.querySelectorAll('.solo-admin').forEach(el => el.style.display = esAdmin ? '' : 'none');
        if (!esAdmin) mostrarAvisoLectura();
        if (typeof dashSaludoYFecha === 'function') dashSaludoYFecha();
        if (user.debe_cambiar_password) abrirCambioObligatorio();
        else if (esAdmin && !user.totp_activo) avisoActivar2FA();
        await cargarSistema();
        irAlHash();  // con los permisos ya aplicados, abrir la sección del enlace
        actualizarContadorConsultas();
        setInterval(actualizarContadorConsultas, 120000);
    } catch {
        window.location.href = '/login';
    }
}

function mostrarAvisoLectura() {
    if (document.getElementById('aviso-lectura')) return;
    const div = document.createElement('div');
    div.id = 'aviso-lectura';
    div.className = 'aviso-banda';
    div.textContent = '👁 Estás en modo solo lectura: podés consultar todo, pero no modificar datos.';
    document.querySelector('main').prepend(div);
}

function avisoActivar2FA() {
    try { if (sessionStorage.getItem('aviso2fa')) return; sessionStorage.setItem('aviso2fa', '1'); } catch {}
    setTimeout(() => toast('🔐 Recomendado: activá la verificación en 2 pasos desde "Mi cuenta y seguridad".', 'warning'), 1500);
}

// Primer ingreso / clave temporal: no se puede usar el sistema hasta cambiarla
function abrirCambioObligatorio() {
    if (document.getElementById('cp-obligatorio')) return;
    document.getElementById('modal-content').innerHTML = `
        <div id="cp-obligatorio">
            <div class="mc-card-tit" style="font-size:1.15rem">🔒 Creá tu contraseña personal</div>
            <p class="muted" style="margin:0.4rem 0 1rem">Por seguridad, antes de continuar tenés que reemplazar la contraseña temporal.
            Mínimo 10 caracteres, con letras y números.</p>
            <label class="mc-lbl">Contraseña actual (temporal)</label>
            <input type="password" id="cp-actual" class="mc-inp" autocomplete="current-password">
            <label class="mc-lbl">Contraseña nueva</label>
            <input type="password" id="cp-nueva" class="mc-inp" autocomplete="new-password">
            <label class="mc-lbl">Repetir contraseña nueva</label>
            <input type="password" id="cp-repetir" class="mc-inp" autocomplete="new-password">
            <button class="btn btn-primary btn-3d" style="width:100%" onclick="guardarPassword(true)">Guardar y continuar</button>
        </div>`;
    const ov = document.getElementById('modal-overlay');
    ov.style.display = 'flex';
    ov.dataset.bloqueado = '1';  // no se cierra tocando afuera
    ov.querySelector('.btn-cerrar-modal').style.display = 'none';
    ov.querySelector('.modal-x').style.display = 'none';
}

async function cerrarSesion() {
    try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch {}
    window.location.href = '/login';
}

async function abrirMiCuenta() {
    try { usuarioActual = await api('/api/auth/me'); } catch {}
    const u = usuarioActual || {};
    const inicial = ((u.nombre || u.username || 'U').trim().charAt(0) || 'U').toUpperCase();
    const bloque2fa = u.totp_activo
        ? `<p class="mc-ok">✅ Activada. Al ingresar se te pide el código de tu app de autenticación.</p>
           <p class="muted">Códigos de respaldo disponibles: <b>${u.codigos_respaldo_restantes}</b> de 8.</p>
           <label class="mc-lbl">Código actual de la app (para regenerar códigos o desactivar)</label>
           <input type="text" id="tf-codigo" class="mc-inp" inputmode="numeric" maxlength="9" autocomplete="one-time-code">
           <label class="mc-lbl">Contraseña (solo para desactivar)</label>
           <input type="password" id="tf-pass" class="mc-inp" autocomplete="current-password">
           <div style="display:flex;gap:0.5rem">
             <button class="btn btn-outline" style="flex:1" onclick="regenerarCodigos2FA()">Nuevos códigos de respaldo</button>
             <button class="btn btn-red" style="flex:1" onclick="desactivar2FA()">Desactivar</button>
           </div>`
        : `<p class="muted">Agrega una segunda llave: aunque alguien sepa tu contraseña, no puede entrar sin el código
           que genera tu celular. Necesitás <b>Google Authenticator</b> o <b>Microsoft Authenticator</b> (gratis).</p>
           <div id="tf-paso"></div>
           <button class="btn btn-primary btn-3d" style="width:100%" id="tf-iniciar" onclick="iniciar2FA()">Activar verificación en 2 pasos</button>`;
    const html = `
        <div class="mc-banner">
            <div class="mc-avatar">${escapeHtml(inicial)}</div>
            <div>
                <div class="mc-nombre">${escapeHtml(u.nombre || '')}</div>
                <div class="mc-user">@${escapeHtml(u.username || '')} · ${escapeHtml(u.rol_nombre || '')}</div>
                ${u.ultimo_ingreso ? `<div class="mc-user">Último ingreso: ${escapeHtml(u.ultimo_ingreso)}</div>` : ''}
            </div>
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">🛡️ Verificación en 2 pasos (2FA)</div>
            ${bloque2fa}
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">👤 Datos de la cuenta</div>
            <label class="mc-lbl">Nombre para mostrar</label>
            <input type="text" id="mc-nombre" class="mc-inp" value="${escapeHtml(u.nombre || '')}">
            <label class="mc-lbl">Usuario (para iniciar sesión)</label>
            <input type="text" id="mc-username" class="mc-inp" value="${escapeHtml(u.username || '')}" autocomplete="off">
            <label class="mc-lbl">Correo (también sirve para ingresar y recuperar la contraseña)</label>
            <input type="email" id="mc-email" class="mc-inp" value="${escapeHtml(u.email || '')}" autocomplete="email">
            <button class="btn btn-primary btn-3d" style="width:100%;margin-top:0.5rem" onclick="guardarCuenta()">Guardar datos</button>
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">🔒 Cambiar contraseña</div>
            <label class="mc-lbl">Contraseña actual</label>
            <input type="password" id="cp-actual" class="mc-inp" autocomplete="current-password">
            <label class="mc-lbl">Contraseña nueva (mínimo 10 caracteres, letras y números)</label>
            <input type="password" id="cp-nueva" class="mc-inp" autocomplete="new-password">
            <label class="mc-lbl">Repetir contraseña nueva</label>
            <input type="password" id="cp-repetir" class="mc-inp" autocomplete="new-password">
            <button class="btn btn-primary btn-3d" style="width:100%" onclick="guardarPassword()">Cambiar contraseña</button>
        </div>

        <div class="mc-card">
            <div class="mc-card-tit">📱 Sesiones</div>
            <p class="muted">¿Dejaste la sesión abierta en otra computadora? Cerrala en todos lados.</p>
            <button class="btn btn-outline" style="width:100%" onclick="cerrarTodasSesiones()">Cerrar sesión en todos los dispositivos</button>
        </div>

        <div class="mc-card solo-admin" ${u.rol === 'admin' ? '' : 'style="display:none"'}>
            <div class="mc-card-tit">📧 Probar envío de email</div>
            <label class="mc-lbl">Enviar un email de prueba a</label>
            <input type="email" id="te-destino" class="mc-inp" placeholder="tucorreo@ejemplo.com" autocomplete="off">
            <button class="btn btn-outline" style="width:100%" onclick="probarEmail()">Enviar email de prueba</button>
        </div>`;
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').style.display = 'flex';
}

async function iniciar2FA() {
    try {
        const r = await api('/api/auth/2fa/iniciar', { method: 'POST' });
        document.getElementById('tf-iniciar').style.display = 'none';
        document.getElementById('tf-paso').innerHTML = `
            <ol class="tf-pasos">
              <li>Abrí la app de autenticación y tocá <b>+</b> → <b>Escanear código QR</b>.</li>
              <li>Escaneá este código:</li>
            </ol>
            <img src="${r.qr}" alt="Código QR para la app de autenticación" class="tf-qr">
            <p class="muted" style="text-align:center">¿No podés escanear? Ingresá esta clave a mano:<br>
              <code class="tf-secreto">${escapeHtml(r.secreto)}</code></p>
            <ol class="tf-pasos" start="3"><li>Escribí el código de 6 dígitos que muestra la app:</li></ol>
            <input type="text" id="tf-confirmar" class="mc-inp input-codigo" inputmode="numeric" maxlength="7" placeholder="000000" autocomplete="one-time-code">
            <button class="btn btn-primary btn-3d" style="width:100%" onclick="activar2FA()">Confirmar y activar</button>`;
        document.getElementById('tf-confirmar').focus();
    } catch (err) { toast(err.message, 'error'); }
}

function mostrarCodigosRespaldo(codigos) {
    const lista = codigos.map(c => `<li><code>${escapeHtml(c)}</code></li>`).join('');
    document.getElementById('modal-content').innerHTML = `
        <div class="mc-card-tit" style="font-size:1.15rem">🔑 Guardá tus códigos de respaldo</div>
        <p class="muted" style="margin:0.5rem 0">Si perdés el celular, cada código sirve <b>una sola vez</b> para entrar.
        Guardalos en un lugar seguro (impresos o en un gestor de contraseñas). <b>No se vuelven a mostrar.</b></p>
        <ul class="tf-codigos">${lista}</ul>
        <div style="display:flex;gap:0.5rem">
          <button class="btn btn-outline" style="flex:1" onclick="copiarCodigos(this)" data-codigos="${escapeHtml(codigos.join('\n'))}">Copiar</button>
          <button class="btn btn-outline" style="flex:1" onclick="window.print()">Imprimir</button>
          <button class="btn btn-primary btn-3d" style="flex:1" onclick="cerrarModal()">Ya los guardé</button>
        </div>`;
}

function copiarCodigos(btn) {
    navigator.clipboard.writeText(btn.dataset.codigos).then(() => toast('Códigos copiados'));
}

async function activar2FA() {
    try {
        const codigo = document.getElementById('tf-confirmar').value;
        const r = await api('/api/auth/2fa/activar', { method: 'POST', body: JSON.stringify({ codigo }) });
        toast('Verificación en 2 pasos activada');
        mostrarCodigosRespaldo(r.codigos_respaldo);
    } catch (err) { toast(err.message, 'error'); }
}

async function regenerarCodigos2FA() {
    try {
        const codigo = document.getElementById('tf-codigo').value;
        const r = await api('/api/auth/2fa/codigos-respaldo', { method: 'POST', body: JSON.stringify({ codigo }) });
        mostrarCodigosRespaldo(r.codigos_respaldo);
    } catch (err) { toast(err.message, 'error'); }
}

async function desactivar2FA() {
    if (!confirm('¿Desactivar la verificación en 2 pasos? Tu cuenta quedará protegida solo por la contraseña.')) return;
    try {
        await api('/api/auth/2fa/desactivar', {
            method: 'POST',
            body: JSON.stringify({ codigo: document.getElementById('tf-codigo').value,
                                   password: document.getElementById('tf-pass').value }),
        });
        toast('Verificación en 2 pasos desactivada', 'warning');
        abrirMiCuenta();
    } catch (err) { toast(err.message, 'error'); }
}

async function cerrarTodasSesiones() {
    if (!confirm('Se cerrará la sesión en todas las computadoras y celulares, incluida esta. ¿Continuar?')) return;
    try { await api('/api/auth/cerrar-sesiones', { method: 'POST' }); } catch {}
    window.location.href = '/login';
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
    const email = document.getElementById('mc-email').value.trim();
    if (!nombre) return toast('El nombre para mostrar no puede estar vacío', 'error');
    if (!username || username.length < 3) return toast('El usuario debe tener al menos 3 caracteres', 'error');
    try {
        const res = await api('/api/auth/actualizar-cuenta', {
            method: 'POST',
            body: JSON.stringify({ username, nombre, email }),
        });
        usuarioActual = { ...usuarioActual, username: res.username, nombre: res.nombre, email: res.email };
        document.getElementById('user-nombre').textContent = res.nombre;
        toast('Cuenta actualizada correctamente');
        cerrarModal();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function guardarPassword(obligatorio = false) {
    const actual = document.getElementById('cp-actual').value;
    const nueva = document.getElementById('cp-nueva').value;
    const repetir = document.getElementById('cp-repetir').value;
    if (!actual || !nueva) return toast('Completá todos los campos', 'error');
    if (nueva.length < 10) return toast('La nueva clave debe tener al menos 10 caracteres', 'error');
    if (!/[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(nueva) || !/\d/.test(nueva)) return toast('La nueva clave debe combinar letras y números', 'error');
    if (nueva !== repetir) return toast('Las contraseñas nuevas no coinciden', 'error');
    try {
        await api('/api/auth/cambiar-password', {
            method: 'POST',
            body: JSON.stringify({ password_actual: actual, password_nueva: nueva }),
        });
        toast('Contraseña actualizada correctamente');
        if (obligatorio) { window.location.reload(); return; }
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

// Atajo del inicio: ir a Gastos y abrir directo el formulario para cargar una factura
async function dashNuevaFactura() {
    dashIr('gastos');
    try { await cargarGastos(); } catch (e) {}
    if (typeof mostrarFormGasto === 'function') mostrarFormGasto();
}

function dashSaludoYFecha() {
    const u = usuarioActual || {};
    const nombre = (u.nombre || 'Hola').split(' ')[0];
    const hora = Number(new Intl.DateTimeFormat('es-AR', { timeZone: TZ_AR, hour: 'numeric', hourCycle: 'h23' }).format(new Date()));
    const saludo = hora < 13 ? 'Buen día' : (hora < 20 ? 'Buenas tardes' : 'Buenas noches');
    const sal = document.getElementById('dash-saludo');
    if (sal) sal.textContent = `${saludo}, ${nombre}`;
    const fecha = document.getElementById('dash-fecha');
    if (fecha) {
        fecha.textContent = new Date().toLocaleDateString('es-AR', {
            timeZone: TZ_AR, weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
        });
    }
}

async function dashKPIs() {
    const grid = document.getElementById('dash-kpis');
    if (!grid) return;
    const total = alumnosCache.length;
    const kpi = (label, valor, sub, prefijo = '') => `<div class="dash-kpi"><div class="dash-kpi-label">${label}</div>
        <div class="dash-kpi-valor" data-num="${valor}" data-prefijo="${prefijo}">${prefijo}0</div><div class="dash-kpi-sub">${sub}</div></div>`;
    let html = kpi('Alumnos registrados', total, 'en el padrón');
    if (sistemaCfg.tarjeta_activa) {
        const conSaldo = alumnosCache.filter(a => Number(a.saldo) > 0).length;
        const saldoTotal = alumnosCache.reduce((s, a) => s + Number(a.saldo || 0), 0);
        let movsHoy = 0;
        try { movsHoy = (await api('/api/operaciones/diario')).length; } catch { /* sin datos */ }
        html = kpi('Saldo total en tarjetas', saldoTotal, `${conSaldo} alumnos con saldo`, '$') + html + kpi('Movimientos de hoy', movsHoy, 'operaciones');
    } else {
        let porRevisar = 0, consultas = 0, pedidos = 0;
        try { porRevisar = (await api('/api/facturas-recibidas/contador')).por_revisar; } catch {}
        try { consultas = (await api('/api/consultas/contador')).sin_leer; } catch {}
        try { pedidos = (await api('/api/pedidos/contador')).nuevos; } catch {}
        html += kpi('Facturas por revisar', porRevisar, 'recibidas de proveedores') + kpi('Consultas sin leer', consultas, 'de familias y del personal')
            + kpi('Pedidos nuevos', pedidos, 'de materiales y servicios');
    }
    grid.innerHTML = html + `<div class="dash-kpi"><div class="dash-kpi-label">Estado del sistema</div>
            <div class="dash-kpi-valor" style="color:var(--green)"><span class="dash-online-dot"></span> En línea</div>
            <div class="dash-kpi-sub">conectado a la base</div></div>`;
    grid.querySelectorAll('.dash-kpi-valor[data-num]').forEach(el =>
        animarNumero(el, Number(el.dataset.num), { prefijo: el.dataset.prefijo || '' }));
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
let totalesProveedores = {};

async function cargarProveedores() {
    try {
        [proveedoresCache, totalesProveedores] = await Promise.all([
            api('/api/proveedores/'), api('/api/gastos/totales-proveedores').catch(() => ({}))]);
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
    document.getElementById('body-proveedores').innerHTML = lista.map(p => {
        const t = totalesProveedores[p.id] || { total: 0, cantidad: 0, ultima: null };
        return `<tr>
            <td>${escapeHtml(p.cuit)}</td>
            <td>${escapeHtml(p.razon_social)}${p.contacto || p.telefono ? `<br><small class="muted">${escapeHtml([p.contacto, p.telefono].filter(Boolean).join(' · '))}</small>` : ''}</td>
            <td>${escapeHtml(p.nombre_fantasia || '—')}</td>
            <td>${escapeHtml(p.rubro || '—')}</td>
            <td class="num">${t.cantidad || '—'}</td>
            <td class="num">${t.cantidad ? `<b>${fmtMoneda(t.total)}</b>` : '—'}</td>
            <td>${t.ultima ? fmtFecha(t.ultima) : '—'}</td>
            <td>
                ${t.cantidad ? `<button class="btn btn-sm btn-primary" onclick="verFacturasProveedor(${p.id})">Facturas</button>` : ''}
                <button class="btn btn-sm" onclick="editarProveedor(${p.id})">Editar</button>
                <button class="btn btn-sm btn-danger btn-ico" onclick="eliminarProveedor(${p.id})" title="Eliminar" aria-label="Eliminar"><svg class="ic"><use href="#i-trash"/></svg></button>
            </td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="8">Sin proveedores</td></tr>';
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
        if (/factura/.test(err.message)) {  // tiene facturas: se ofrece borrar todo junto
            if (!confirm(err.message + ' ¿Eliminar el proveedor y TODAS sus facturas? Los pagos en efectivo que el sistema anotó en el libro de caja también se borran. No se puede deshacer.')) return;
            try {
                const res = await api(`/api/proveedores/${id}?con_facturas=true`, { method: 'DELETE' });
                toast(res.mensaje);
                proveedoresCache = [];
                cargarProveedores();
            } catch (e2) { toast(e2.message, 'error'); }
            return;
        }
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
        // siempre fresca: los proveedores nuevos llegan también por el portal
        try { proveedoresCache = await api('/api/proveedores/'); } catch (e) {}
        const cat = document.getElementById('gasto-f-categoria').value;
        const mes = document.getElementById('gasto-f-mes').value;
        const anio = document.getElementById('gasto-f-anio').value;
        const p = new URLSearchParams();
        if (cat) p.set('categoria', cat);
        if (gastoEstado) p.set('estado', gastoEstado);
        else {  // los filtros de estado muestran todo lo pendiente, sin importar el mes
            if (mes) p.set('mes', mes);
            if (anio) p.set('anio', anio);
        }
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
                <div class="gasto-kpi-valor">${fmtMoneda(c.total)}</div>
                <div class="gasto-kpi-sub">${c.cantidad} comprob.</div></div>`).join('');
        const ap = r.a_pagar || {};
        cont.innerHTML =
            `<div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Total del período</div>
                <div class="gasto-kpi-valor">${fmtMoneda(r.total)}</div>
                <div class="gasto-kpi-sub">${r.cantidad} comprobantes</div></div>
             <div class="gasto-kpi"><div class="gasto-kpi-label">A pagar (todas)</div>
                <div class="gasto-kpi-valor">${fmtMoneda(ap.total || 0)}</div>
                <div class="gasto-kpi-sub">${ap.cantidad || 0} facturas impagas</div></div>
             <div class="gasto-kpi"><div class="gasto-kpi-label">Vencido</div>
                <div class="gasto-kpi-valor" style="color:var(--${ap.vencido ? 'danger' : 'text-muted'})">${fmtMoneda(ap.vencido || 0)}</div>
                <div class="gasto-kpi-sub">${ap.vencidas || 0} facturas · vence esta semana ${fmtMoneda(ap.esta_semana || 0)}</div></div>` + cats;
        const b = document.getElementById('badge-por-revisar');
        if (b) { b.textContent = r.por_revisar || 0; b.hidden = !r.por_revisar; }
    } catch (err) { /* sin datos */ }
}

function filtrarGastos() {
    const q = (document.getElementById('buscar-gasto').value || '').toLowerCase();
    const lista = gastosCache.filter(g => !q ||
        [g.razon_social, g.cuit, g.concepto, g.rubro, g.destino, g.numero]
            .some(v => (v || '').toLowerCase().includes(q)));
    renderGastos(lista);
}

const CATEGORIAS_GASTO = ['Oficina', 'Infraestructura', 'Escuela', 'Honorarios'];

let gastoEstado = '';

function filtrarEstadoGasto(btn) {
    document.querySelectorAll('#gasto-estados .chip').forEach(b => b.classList.toggle('chip-activo', b === btn));
    gastoEstado = btn.dataset.estado;
    cargarGastos();
}

function renderGastos(lista) {
    document.getElementById('body-gastos').innerHTML = lista.map(g => {
        const neg = Number(g.importe) < 0;
        const fecha = g.fecha ? g.fecha.split('-').reverse().join('/') : '-';
        const nc = g.nc_de_id ? ' <span class="tag-nc">NC</span>' : '';
        const adj = g.adjunto_url
            ? ` <a href="${escapeHtml(g.adjunto_url)}" target="_blank" rel="noopener" title="Ver comprobante" style="text-decoration:none">📎</a>` : '';
        // Selector de categoría en la fila
        const opts = ['<option value="">— categoría —</option>']
            .concat(CATEGORIAS_GASTO.map(c => `<option value="${c}"${g.categoria === c ? ' selected' : ''}>${c}</option>`))
            .join('');
        const selCat = `<select class="cat-select${g.categoria ? '' : ' cat-vacia'}" onchange="cambiarCategoriaGasto(${g.id}, this.value)">${opts}</select>`;
        // Estado de pago
        let pago;
        const hoy = hoyISO();
        const vence = g.vencimiento ? `<div class="gasto-vence${!g.forma_pago && g.vencimiento < hoy ? ' vencida' : ''}">vence ${fmtFecha(g.vencimiento)}</div>` : '';
        if (g.revisado === false) {
            pago = `<span class="badge badge-revisar">Por revisar</span> <button class="btn btn-sm btn-primary" onclick="editarGasto(${g.id})">Revisar</button>${vence}`;
        } else if (g.forma_pago) {
            const fp = g.fecha_pago ? g.fecha_pago.split('-').reverse().join('/') : '';
            const icono = g.forma_pago === 'Efectivo' ? '💵' : '🏦';
            pago = `<span class="pago-ok">${icono} ${escapeHtml(g.forma_pago)}</span>
                <button class="btn btn-sm" title="Deshacer el pago" aria-label="Deshacer el pago" onclick="desvincularPagoGasto(${g.id})">✕</button>
                <div class="pago-det">${[fp, g.pagado_por ? 'vía ' + escapeHtml(g.pagado_por) : ''].filter(Boolean).join(' · ')}</div>`;
        } else {
            pago = `<button class="btn btn-sm btn-primary" onclick="abrirVincularPago(${g.id})">Vincular pago</button>${vence}`;
        }
        return `<tr>
            <td>${fecha}</td>
            <td>${escapeHtml(g.razon_social || '-')}${nc}${adj}</td>
            <td>${escapeHtml(g.concepto || '-')}</td>
            <td>${selCat}</td>
            <td>${pago}</td>
            <td style="text-align:right;${neg ? 'color:var(--red)' : ''}">${fmtMoneda(g.importe)}</td>
            <td>
                <button class="btn btn-sm" onclick="editarGasto(${g.id})">Editar</button>
                <button class="btn btn-sm btn-danger btn-ico" onclick="eliminarGasto(${g.id})" title="Eliminar" aria-label="Eliminar"><svg class="ic"><use href="#i-trash"/></svg></button>
            </td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">Sin gastos en este período</td></tr>';
}

async function cambiarCategoriaGasto(id, valor) {
    try {
        await api(`/api/gastos/${id}`, { method: 'PUT', body: JSON.stringify({ categoria: valor || null }) });
        const g = gastosCache.find(x => x.id === id);
        if (g) g.categoria = valor || null;
        filtrarGastos();
        cargarGastos();  // refresca el resumen por categoría
    } catch (err) {
        toast(err.message, 'error');
    }
}

// --- Vincular pago (banco o caja efectivo) ---
async function abrirVincularPago(id) {
    const g = gastosCache.find(x => x.id === id);
    try {
        const [c, rend] = await Promise.all([api(`/api/gastos/${id}/candidatos-pago`), api('/api/conciliacion/encargados/pendientes').catch(() => [])]);
        const fRend = rend.map(r => `<tr><td>${fmtFecha(r.fecha)}</td><td><b>${escapeHtml(r.encargado ? r.encargado.nombre : '')}</b>
                <br><small class="muted">transferido ${fmtMoneda(r.transferido)} · falta rendir ${fmtMoneda(r.saldo)}</small></td>
                <td>${g && Math.abs(Number(g.importe) - r.saldo) <= 1 ? '<span class="conc-tag-ok">Importe ✓</span>' : ''}</td>
                <td><button class="btn btn-sm btn-primary" onclick="pagoPorEncargado(${id}, ${r.id}, ${r.encargado ? r.encargado.id : 'null'})">Vincular</button></td></tr>`).join('')
            || '<tr><td colspan="4" style="color:var(--text-muted)">No hay transferencias a encargados pendientes de rendir. Cargá los encargados en Conciliación bancaria.</td></tr>';
        const tag = (m, mo, no) => [m ? '<span class="conc-tag-ok">CUIT ✓</span>' : '',
            no ? '<span class="conc-tag-ok">Razón social ✓</span>' : '',
            mo ? '<span class="conc-tag-ok">Importe ✓</span>' : ''].join(' ');
        const fBanco = (c.banco || []).map(b => {
            const f = b.fecha ? b.fecha.split('-').reverse().join('/') : '';
            return `<tr><td>${f}</td><td>${escapeHtml(b.razon_social || b.descripcion || '')}</td>
                <td style="text-align:right">${fmtMoneda(b.importe)}</td>
                <td>${tag(b.coincide_cuit, b.coincide_monto, b.coincide_nombre)}${b.coincide_monto ? '' : ` <span class="conc-tag-dif">Dif. ${fmtMoneda(Math.abs(b.importe - Math.abs(g ? g.importe : 0)))}</span>`}</td>
                <td><button class="btn btn-sm btn-primary" onclick="pagoBanco(${id},${b.id},${b.coincide_monto ? 0 : b.importe},${g ? Math.abs(g.importe) : 0})">Vincular</button></td></tr>`;
        }).join('') || '<tr><td colspan="5" style="color:var(--text-muted)">Sin movimientos de banco que coincidan.</td></tr>';
        const fCaja = (c.caja || []).map(k => {
            const f = k.fecha ? k.fecha.split('-').reverse().join('/') : '';
            return `<tr><td>${f}</td><td>${escapeHtml(k.concepto || '')}</td>
                <td style="text-align:right">${fmtMoneda(k.importe)}</td>
                <td><button class="btn btn-sm btn-primary" onclick="pagoCaja(${id},${k.id})">Vincular</button></td></tr>`;
        }).join('') || '<tr><td colspan="4" style="color:var(--text-muted)">Sin egresos de caja que coincidan.</td></tr>';
        const html = `
            <h2 style="margin-top:0">Vincular el pago</h2>
            <p style="color:var(--text-muted);margin-top:-0.4rem">
                ${g ? `${escapeHtml(g.razon_social || '')} · ${fmtMoneda(g.importe)}` : ''}</p>
            <h3 style="margin-bottom:.4rem">🏦 Transferencia (extracto del banco)</h3>
            <table><thead><tr><th>Fecha</th><th>Destinatario</th><th style="text-align:right">Importe</th><th>Coincide</th><th></th></tr></thead>
            <tbody>${fBanco}</tbody></table>
            <h3 style="margin:1rem 0 .4rem">👤 Transferencia a un encargado que hizo la compra</h3>
            <table><thead><tr><th>Fecha</th><th>Encargado</th><th>Coincide</th><th></th></tr></thead>
            <tbody>${fRend}</tbody></table>
            <h3 style="margin:1rem 0 .4rem">💵 Efectivo (movimiento de caja)</h3>
            <table><thead><tr><th>Fecha</th><th>Concepto</th><th style="text-align:right">Importe</th><th></th></tr></thead>
            <tbody>${fCaja}</tbody></table>
            <div style="margin-top:1rem;display:flex;gap:.5rem;justify-content:space-between">
                <span class="pago-efectivo-box"><label for="pago-ef-fecha">Pagada en efectivo el</label>
                    <input type="date" id="pago-ef-fecha" value="${hoyISO()}" max="${hoyISO()}">
                    <button class="btn btn-success" onclick="pagoEfectivoNuevo(${id})">+ Registrar pago en efectivo (crea el egreso de caja)</button></span>
            </div>`;
        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function pagoBanco(id, bancoId, importeBanco, importeFactura) {
    let nota = null;
    if (importeBanco) {
        nota = motivoDiferencia(importeBanco, importeFactura);
        if (nota === null) return;
        if (!nota) { toast('Anotá el motivo de la diferencia', 'error'); return; }
    }
    try { await api(`/api/gastos/${id}/pago/banco/${bancoId}`, { method: 'POST', body: JSON.stringify({ nota }) });
        toast('Pago vinculado (transferencia)'); cerrarModal(); cargarGastos();
    } catch (err) { toast(err.message, 'error'); }
}
async function pagoCaja(id, cajaId) {
    try { await api(`/api/gastos/${id}/pago/caja/${cajaId}`, { method: 'POST' });
        toast('Pago vinculado (efectivo)'); cerrarModal(); cargarGastos();
    } catch (err) { toast(err.message, 'error'); }
}
async function pagoEfectivoNuevo(id) {
    const fecha = (document.getElementById('pago-ef-fecha') || {}).value || hoyISO();
    if (!confirm(`Se va a registrar un egreso en el Libro de Caja por este importe, con fecha ${fmtFecha(fecha)}. ¿Continuar?`)) return;
    try { await api(`/api/gastos/${id}/pago/efectivo-nuevo`, { method: 'POST', body: JSON.stringify({ fecha }) });
        toast('Pago en efectivo registrado'); cerrarModal(); cargarGastos();
    } catch (err) { toast(err.message, 'error'); }
}
async function desvincularPagoGasto(id) {
    if (!confirm('¿Deshacer el pago de este gasto?')) return;
    try { await api(`/api/gastos/${id}/desvincular-pago`, { method: 'POST' });
        toast('Pago desvinculado'); cargarGastos();
    } catch (err) { toast(err.message, 'error'); }
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
        if (p.rubro) document.getElementById('gasto-rubro').value = p.rubro;
        sugerirDatosProveedor({ proveedor_id: p.id });
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
            return `<option value="${g.id}">${f} · ${nro || 's/n'} · ${fmtMoneda(g.importe)} · ${escapeHtml(g.concepto || '')}</option>`;
        }).join('');
}

// --- Lectura automática de factura por QR de AFIP ---
const AFIP_TIPO = {
    1: 'Factura A', 2: 'Comprobante', 3: 'Nota de Crédito',
    6: 'Factura B', 7: 'Comprobante', 8: 'Nota de Crédito',
    11: 'Factura C', 12: 'Comprobante', 13: 'Nota de Crédito',
    51: 'Factura A', 52: 'Comprobante', 53: 'Nota de Crédito',
    81: 'Ticket', 82: 'Ticket', 83: 'Ticket',
};
const AFIP_ES_NC = new Set([3, 8, 13, 53]);

function parseAfipQR(texto) {
    try {
        let p = null;
        const m = (texto || '').match(/[?&]p=([^&]+)/);
        if (m) p = decodeURIComponent(m[1]);
        else if (/^[A-Za-z0-9+/=]+$/.test(texto || '')) p = texto;
        if (!p) return null;
        const json = JSON.parse(atob(p));
        return (json && json.cuit) ? json : null;
    } catch (e) { return null; }
}

// Busca un QR en una fuente ya dibujable (imagen o canvas) probando varias
// resoluciones (de mayor a menor) y QR invertidos. Devuelve el texto del QR o null.
function _jsQRdesdeFuente(fuente, anchoNat, altoNat) {
    if (typeof jsQR === 'undefined') return null;
    const maxLado = Math.max(anchoNat, altoNat);
    const objetivos = [2600, 1800, 1200, 900];
    const escalas = [...new Set(objetivos.map(m => Math.min(1, m / maxLado)))];
    const cv = document.createElement('canvas');
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    for (const f of escalas) {
        const w = Math.max(1, Math.round(anchoNat * f));
        const h = Math.max(1, Math.round(altoNat * f));
        cv.width = w; cv.height = h;
        ctx.drawImage(fuente, 0, 0, w, h);
        try {
            const d = ctx.getImageData(0, 0, w, h);
            const code = jsQR(d.data, w, h, { inversionAttempts: 'attemptBoth' });
            if (code && code.data) return code.data;
        } catch (e) {}
    }
    return null;
}

function escanearQRdeImagen(file) {
    return new Promise((resolve) => {
        if (!file.type.startsWith('image/') || typeof jsQR === 'undefined') { resolve(null); return; }
        const img = new Image();
        img.onload = () => {
            const data = _jsQRdesdeFuente(img, img.width, img.height);
            URL.revokeObjectURL(img.src);
            resolve(data);
        };
        img.onerror = () => resolve(null);
        img.src = URL.createObjectURL(file);
    });
}

async function escanearQRdePDF(file) {
    if (typeof pdfjsLib === 'undefined' || typeof jsQR === 'undefined') return null;
    try {
        const buf = await file.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
        const cv = document.createElement('canvas');
        const ctx = cv.getContext('2d', { willReadFrequently: true });
        const maxPag = Math.min(pdf.numPages, 5);
        for (let n = 1; n <= maxPag; n++) {
            const page = await pdf.getPage(n);
            const base = page.getViewport({ scale: 1 });
            // Renderizar a ~2200px de ancho para que el QR salga nítido
            const escala = Math.min(4, Math.max(2, 2200 / base.width));
            const vp = page.getViewport({ scale: escala });
            cv.width = Math.round(vp.width); cv.height = Math.round(vp.height);
            await page.render({ canvasContext: ctx, viewport: vp }).promise;
            const data = _jsQRdesdeFuente(cv, cv.width, cv.height);
            if (data) return data;
        }
    } catch (e) { console.warn('No se pudo leer el PDF:', e); }
    return null;
}

// Detecta el QR en una imagen o un PDF
async function escanearQR(file) {
    const esPDF = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
    return esPDF ? await escanearQRdePDF(file) : await escanearQRdeImagen(file);
}

function aplicarDatosAfip(d) {
    if (d.fecha) document.getElementById('gasto-fecha').value = String(d.fecha).slice(0, 10);
    let provEncontrado = true;
    if (d.cuit) {
        const cuit = String(d.cuit);
        document.getElementById('gasto-cuit').value = cuit;
        const prov = (proveedoresCache || []).find(p => (p.cuit || '').replace(/\D/g, '') === cuit.replace(/\D/g, ''));
        if (prov) {
            document.getElementById('gasto-proveedor').value = prov.id;
            document.getElementById('gasto-razon').value = prov.razon_social || '';
            if (prov.rubro) document.getElementById('gasto-rubro').value = prov.rubro;
        } else {
            provEncontrado = false;
        }
    }
    if (d.cuit) sugerirDatosProveedor({ cuit: String(d.cuit) });
    if (d.codAut) document.getElementById('gasto-cae').value = String(d.codAut);
    if (d.ptoVta != null) document.getElementById('gasto-pv').value = String(d.ptoVta).padStart(4, '0');
    if (d.nroCmp != null) document.getElementById('gasto-numero').value = String(d.nroCmp).padStart(8, '0');
    if (d.importe != null) document.getElementById('gasto-importe').value = d.importe;
    const tipo = AFIP_TIPO[d.tipoCmp];
    if (tipo) document.getElementById('gasto-tipo').value = tipo;
    if (AFIP_ES_NC.has(d.tipoCmp)) { document.getElementById('gasto-es-nc').checked = true; gastoToggleNC(); }
    gastoLlenarNCde();
    return provEncontrado;
}

// Sube el comprobante directo a Supabase Storage con una URL firmada por el servidor
// (Vercel no acepta pedidos de más de 4,5 MB). Si eso falla, prueba la subida clásica.
async function subirComprobante(file) {
    try {
        const r = await fetch(API + '/api/gastos/adjunto-firma', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre: file.name || 'comprobante', tamanio: file.size }),
        });
        const firma = await r.json();
        if (!r.ok) throw new Error(firma.detail || 'Error al preparar la subida');
        const up = await fetch(firma.upload_url, {
            method: 'PUT',
            headers: { 'Content-Type': file.type || 'application/octet-stream' },
            body: file,
        });
        if (!up.ok) throw new Error('Storage respondió ' + up.status);
        return firma.public_url;
    } catch (e) {
        if (file.size > 4 * 1024 * 1024) throw e;  // demasiado grande para la vía clásica
        console.warn('Subida directa falló, uso la clásica:', e);
        const fd = new FormData();
        fd.append('archivo', file);
        const res = await fetch(API + '/api/gastos/adjunto', { method: 'POST', credentials: 'same-origin', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al subir');
        return data.url;
    }
}

async function leerComprobante(input) {
    const file = input.files[0];
    if (!file) return;
    const est = document.getElementById('gasto-lector-estado');
    est.textContent = '⏳ Leyendo la factura...';
    est.className = 'gasto-lector-estado activo';

    let leido = false, provFalta = false, qrPeroNoFactura = false, qrViejo = false;
    const esPDF = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
    const qr = await escanearQR(file);
    if (qr) {
        const datos = parseAfipQR(qr);
        if (datos) { provFalta = !aplicarDatosAfip(datos); leido = true; }
        else if (/qr\.afip\.gob\.ar|[?&]qr=/i.test(qr)) { qrViejo = true; }
        else { qrPeroNoFactura = true; }
    }

    // Subir la imagen/PDF a Storage como respaldo
    try {
        const data = { url: await subirComprobante(file) };
        document.getElementById('gasto-adjunto').value = data.url;
        const ver = document.getElementById('gasto-adjunto-ver');
        ver.href = data.url; ver.style.display = '';
        if (leido) {
            est.textContent = provFalta
                ? '⚠ Proveedor NO registrado. Completá razón social y rubro: al guardar el gasto se da de alta solo.'
                : '✓ Datos leídos del QR (proveedor, rubro e importe). Revisá y guardá.';
            est.className = provFalta ? 'gasto-lector-estado activo' : 'gasto-lector-estado ok';
        } else if (qrViejo) {
            est.textContent = '✓ Comprobante guardado. Tiene el QR viejo de AFIP, que no incluye los datos adentro — cargalos a mano.';
            est.className = 'gasto-lector-estado ok';
        } else if (qrPeroNoFactura) {
            est.textContent = '✓ Comprobante guardado. Leí un QR pero no es el de la factura de AFIP/ARCA — completá los datos a mano.';
            est.className = 'gasto-lector-estado ok';
        } else if (esPDF) {
            est.textContent = '✓ PDF guardado. No encontré el QR de AFIP/ARCA en el PDF: completá los datos a mano.';
            est.className = 'gasto-lector-estado ok';
        } else {
            est.textContent = '✓ Comprobante guardado. No detecté el QR — probá una foto más nítida, derecha y con el QR bien visible y de cerca.';
            est.className = 'gasto-lector-estado ok';
        }
    } catch (err) {
        est.textContent = (leido ? '✓ Datos leídos del QR. ' : '') + '⚠ No se pudo guardar la imagen: ' + err.message;
        est.className = 'gasto-lector-estado ' + (leido ? 'ok' : 'error');
    } finally {
        input.value = '';
    }
}

function gastoMostrarVerAdjunto() {
    const url = document.getElementById('gasto-adjunto').value;
    const ver = document.getElementById('gasto-adjunto-ver');
    if (url) { ver.href = url; ver.style.display = ''; } else { ver.style.display = 'none'; }
}

// Avisa al abrir el form si Supabase Storage está conectado
async function gastoChequearStorage() {
    const est = document.getElementById('gasto-lector-estado');
    if (!est) return;
    try {
        const r = await api('/api/gastos/storage-estado');
        if (!r.configurado) {
            est.textContent = '⚠ Falta conectar Supabase Storage: vas a poder leer el QR, pero la foto no se guardará hasta cargar las claves de Supabase en Vercel (Settings → Environment Variables).';
            est.className = 'gasto-lector-estado error';
        }
    } catch (e) { /* sin sesión */ }
}

function mostrarFormGasto() {
    document.getElementById('form-gasto').style.display = 'block';
    document.getElementById('form-gasto-titulo').textContent = 'Nuevo Gasto';
    document.getElementById('gasto-edit-id').value = '';
    ['gasto-pv', 'gasto-numero', 'gasto-razon', 'gasto-cuit', 'gasto-importe',
        'gasto-rubro', 'gasto-concepto', 'gasto-destino', 'gasto-adjunto',
        'gasto-notas', 'gasto-vencimiento', 'gasto-cae', 'gasto-recibida-id'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('gasto-revision').hidden = true;
    document.getElementById('gasto-btn-revisar').hidden = true;
    gastoPagoLlenar(null);
    document.getElementById('gasto-fecha').value = hoyISO();
    document.getElementById('gasto-tipo').value = '';
    document.getElementById('gasto-proveedor').value = '';
    document.getElementById('gasto-es-nc').checked = false;
    document.getElementById('gasto-nc-wrap').style.display = 'none';
    const est = document.getElementById('gasto-lector-estado');
    if (est) { est.textContent = ''; est.className = 'gasto-lector-estado'; }
    gastoMostrarVerAdjunto();
    gastoLlenarProveedores();
    gastoChequearStorage();
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
    const selProv = document.getElementById('gasto-proveedor');
    if (g.proveedor_id && ![...selProv.options].some(o => o.value === String(g.proveedor_id))) {
        // proveedor que no estaba en la lista (p. ej. recién creado por el portal): se agrega para no desvincularlo al guardar
        selProv.add(new Option(`${g.razon_social || 'Proveedor'}${g.cuit ? ' (' + g.cuit + ')' : ''}`, g.proveedor_id));
    }
    selProv.value = g.proveedor_id || '';
    document.getElementById('gasto-razon').value = g.razon_social || '';
    document.getElementById('gasto-cuit').value = g.cuit || '';
    document.getElementById('gasto-importe').value = g.importe;
    document.getElementById('gasto-rubro').value = g.rubro || '';
    document.getElementById('gasto-concepto').value = g.concepto || '';
    document.getElementById('gasto-destino').value = g.destino || '';
    document.getElementById('gasto-adjunto').value = g.adjunto_url || '';
    document.getElementById('gasto-vencimiento').value = g.vencimiento || '';
    document.getElementById('gasto-cae').value = g.cae || '';
    document.getElementById('gasto-recibida-id').value = '';
    gastoPagoLlenar(g);
    const rev = document.getElementById('gasto-revision');
    rev.hidden = g.revisado !== false;
    rev.innerHTML = g.revisado === false ? `Esta factura llegó del <b>portal de proveedores</b> y se cargó sola. Revisá los datos
        (y completá concepto, rubro, destino y categoría) y tocá <b>«Guardar y marcar revisada»</b>.${g.notas ? '<br>' + escapeHtml(g.notas) : ''}` : '';
    document.getElementById('gasto-btn-revisar').hidden = g.revisado !== false;
    gastoMostrarVerAdjunto();
    const est = document.getElementById('gasto-lector-estado');
    if (est) { est.textContent = ''; est.className = 'gasto-lector-estado'; }
    document.getElementById('gasto-notas').value = g.notas || '';
    const esNC = !!g.nc_de_id;
    document.getElementById('gasto-es-nc').checked = esNC;
    document.getElementById('gasto-nc-wrap').style.display = esNC ? 'block' : 'none';
    if (esNC) { gastoLlenarNCde(); document.getElementById('gasto-nc-de').value = g.nc_de_id; }
    document.getElementById('form-gasto').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Pago cargado a mano en la factura (medio y fecha en que salió la plata)
const FORMAS_PAGO_GASTO = ['Efectivo', 'Transferencia', 'Débito', 'Tarjeta', 'Cheque', 'Otro'];
function gastoPagoLlenar(g) {
    const sel = document.getElementById('gasto-forma-pago');
    sel.innerHTML = '<option value="">— Sin pagar todavía —</option>' + FORMAS_PAGO_GASTO.map(f => `<option>${f}</option>`).join('');
    sel.value = (g && g.forma_pago) || '';
    sel.dataset.original = sel.value;
    document.getElementById('gasto-fecha-pago').value = (g && g.fecha_pago) || '';
    document.getElementById('gasto-categoria').value = (g && g.categoria) || '';
    // El medio sale de conciliar con el banco o de registrar el pago en efectivo: no se elige a mano.
    sel.disabled = true;
    const fp = document.getElementById('gasto-fecha-pago');
    const editable = !!(g && g.forma_pago && (g.caja_mov_id || !g.conciliado));
    fp.disabled = !editable;
    fp.dataset.original = fp.value;
    document.getElementById('gasto-pago-vinc').textContent = !g || !g.forma_pago ? '· sin pagar todavía'
        : g.caja_mov_id ? '· pagada en efectivo (libro de caja): podés corregir la fecha'
        : g.conciliado ? '· pagada por banco (conciliada con el extracto)' : '';
    gastoPagoCambio();
}
function gastoPagoCambio() {
    const f = document.getElementById('gasto-fecha-pago'), m = document.getElementById('gasto-forma-pago');
    f.max = hoyISO();
    f.classList.toggle('pd-mal', false);
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
        destino: document.getElementById('gasto-destino').value || null,
        adjunto_url: document.getElementById('gasto-adjunto').value || null,
        nc_de_id: (esNC && ncDe) ? Number(ncDe) : null,
        notas: document.getElementById('gasto-notas').value || null,
        vencimiento: document.getElementById('gasto-vencimiento').value || null,
        cae: document.getElementById('gasto-cae').value || null,
        categoria: document.getElementById('gasto-categoria').value || null,
    };
    const fp = document.getElementById('gasto-fecha-pago');
    if (editId && !fp.disabled && fp.value && fp.value !== (fp.dataset.original || '')) body.fecha_pago = fp.value;
    const recibida = document.getElementById('gasto-recibida-id').value;
    if (recibida && !editId) body.factura_recibida_id = Number(recibida);
    if (e.submitter && e.submitter.dataset.revisar) body.revisado = true;
    try {
        if (editId) {
            await api(`/api/gastos/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
            toast('Gasto actualizado');
        } else {
            await api('/api/gastos/', { method: 'POST', body: JSON.stringify(body) });
            toast(body.proveedor_id ? 'Gasto registrado' : 'Gasto registrado y proveedor dado de alta');
        }
        cerrarFormGasto();
        proveedoresCache = [];  // se recarga (puede haberse creado un proveedor nuevo)
        cargarGastos();
        actualizarBadgeRecibidas();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarGasto(id) {
    const g = gastosCache.find(x => x.id === id);
    const efectivo = g && g.caja_mov_id ? ' También se borra el egreso que se anotó en el libro de caja al pagarla en efectivo.' : '';
    if (!confirm(`¿Eliminar esta factura${g && g.razon_social ? ' de ' + g.razon_social : ''}${g ? ' por ' + fmtMoneda(g.importe) : ''}?${efectivo}`)) return;
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
                <div class="gasto-kpi-valor">${fmtMoneda(r.saldo_actual)}</div>
                <div class="gasto-kpi-sub">inicial: ${fmtMoneda(r.saldo_inicial)}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Ingresos del período</div>
                <div class="gasto-kpi-valor" style="color:var(--green)">${fmtMoneda(r.ingresos_periodo)}</div>
                <div class="gasto-kpi-sub">${r.cantidad} movimientos</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Egresos del período</div>
                <div class="gasto-kpi-valor" style="color:var(--red)">${fmtMoneda(r.egresos_periodo)}</div>
                <div class="gasto-kpi-sub">&nbsp;</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Neto del período</div>
                <div class="gasto-kpi-valor" style="color:${r.neto_periodo < 0 ? 'var(--red)' : 'var(--green)'}">${fmtMoneda(r.neto_periodo)}</div>
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
            <td style="text-align:right;font-weight:700">${fmtMoneda(m.saldo)}</td>
            <td>
                ${esIng ? `<button class="btn btn-sm btn-primary" title="Imputar como pago de cuota" onclick="imputarCuotaDesdeCaja(${m.id}, ${m.monto})">→ Cuota</button>` : ''}
                <button class="btn btn-sm" onclick="editarCaja(${m.id})">Editar</button>
                <button class="btn btn-sm btn-danger btn-ico" onclick="eliminarCaja(${m.id})" title="Eliminar" aria-label="Eliminar"><svg class="ic"><use href="#i-trash"/></svg></button>
            </td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">Sin movimientos en este período</td></tr>';
}

async function imputarCuotaDesdeCaja(cajaMovId, monto) {
    const leg = prompt(`Imputar este ingreso (${fmtMoneda(monto)}) como pago de cuota.\n\nLegajo del alumno:`);
    if (!leg) return;
    try {
        if (!alumnosCache.length) await cargarAlumnos();
        const a = alumnosCache.find(x => String(x.legajo) === String(leg).trim());
        if (!a) { toast('No encontré un alumno con ese legajo', 'error'); return; }
        if (!confirm(`¿Imputar ${fmtMoneda(monto)} como pago de cuota de ${a.apellido}, ${a.nombre}?`)) return;
        await api('/api/cuotas/efectivo', { method: 'POST', body: JSON.stringify({ alumno_id: a.id, caja_mov_id: cajaMovId }) });
        toast(`Pago imputado a ${a.apellido}, ${a.nombre}`);
    } catch (err) {
        toast(err.message, 'error');
    }
}

function mostrarFormCaja(tipo) {
    document.getElementById('form-caja').style.display = 'block';
    document.getElementById('form-caja-titulo').textContent =
        tipo === 'egreso' ? 'Nuevo egreso (salida de efectivo)' : 'Nuevo ingreso (entrada de efectivo)';
    document.getElementById('caja-edit-id').value = '';
    document.getElementById('caja-tipo').value = tipo;
    ['caja-monto', 'caja-concepto', 'caja-notas'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('caja-fecha').value = hoyISO();
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
        let res = await fetch(`${API}/api/caja/${id}`, { method: 'DELETE', credentials: 'same-origin' });
        let data = await res.json().catch(() => ({}));
        if (res.status === 409) {  // vinculado a un pago de cuota o a una factura: confirmar
            if (!confirm(`${data.detail}\n\n¿Eliminar igual?`)) return;
            res = await fetch(`${API}/api/caja/${id}?confirmar=true`, { method: 'DELETE', credentials: 'same-origin' });
            data = await res.json().catch(() => ({}));
        }
        if (!res.ok) throw new Error(data.detail || 'No se pudo eliminar');
        toast(data.mensaje);
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
        fecha: hoyISO(),
        concepto: concepto,
        tipo_movimiento: tipo === 'ingreso' ? 'Venta' : concepto,
        tipo: tipo,
        monto: monto,
    };
    try {
        await api('/api/caja/', { method: 'POST', body: JSON.stringify(body) });
        toast(`${tipo === 'ingreso' ? 'Ingreso' : 'Egreso'} de ${fmtMoneda(monto)} registrado`);
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
        cargarPanelExtracto();
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
                <div class="gasto-kpi-sub">${fmtMoneda(r.monto_total)}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Conciliados</div>
                <div class="gasto-kpi-valor" style="color:var(--green)">${r.conciliados}</div>
                <div class="gasto-kpi-sub">cruzados con factura</div></div>
            <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Pendientes</div>
                <div class="gasto-kpi-valor">${r.pendientes}</div>
                <div class="gasto-kpi-sub">${fmtMoneda(r.monto_pendiente)} sin factura</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Sin factura</div>
                <div class="gasto-kpi-valor">${r.sin_factura || 0}</div>
                <div class="gasto-kpi-sub">${fmtMoneda(r.monto_sin_factura || 0)} · sueldos, cargas sociales, AFIP, devueltas</div></div>`;
    } catch (err) { /* sin datos */ }
}

function filtrarConciliacion() {
    const q = (document.getElementById('buscar-conc').value || '').toLowerCase();
    const lista = concCache.filter(m => !q ||
        [m.cuit, m.razon_social, m.descripcion].some(v => (v || '').toLowerCase().includes(q)));
    renderConciliacion(lista);
}

const TIPOS_BANCO = {
    '190': 'Transferencia', '190100': 'Transferencia', 'F30': 'DEBIN', 'F30100': 'DEBIN',
    '146': 'Débito directo',
};
const CATEG_EXTRACTO = [
    ['ingreso_siro', 'Cobros por SIRO', 'success'], ['ingreso_qr', 'Cobros por QR', 'success'],
    ['otro_ingreso', 'Otros ingresos', 'success'], ['pago', 'Pagos (a conciliar)', 'danger'],
    ['afip', 'Débitos de AFIP (no llevan factura)', 'danger'],
    ['haberes', 'Pagos de haberes (no se concilian)', 'danger'], ['pago_automatico', 'Pagos automáticos (no se concilian)', 'danger'],
    ['otro_egreso', 'Otros egresos', 'danger'], ['comision', 'Comisiones e impuestos', 'warning'],
];

// Resumen del último extracto importado: saldos, control de cierre y totales
async function cargarPanelExtracto() {
    const cont = document.getElementById('conc-extracto');
    try {
        const lista = await api('/api/conciliacion/extractos');
        if (!lista.length) { cont.innerHTML = ''; return; }
        const e = lista[0];
        const filas = CATEG_EXTRACTO.filter(([k]) => e.resumen[k]).map(([k, nombre, color]) => `
            <tr><td>${nombre}</td><td class="num">${e.resumen[k].cantidad}</td>
                <td class="num" style="color:var(--${color});font-weight:600">${fmtMoneda(e.resumen[k].total)}</td></tr>`).join('');
        const comis = e.resumen.comision;
        cont.innerHTML = `<div class="card extracto-card">
            <div class="extracto-head">
                <div><div class="page-miga">${escapeHtml(e.banco)} · último extracto importado</div>
                    <h3 style="margin:0.15rem 0 0">Del ${fmtFecha(e.desde)} al ${fmtFecha(e.hasta)}</h3>
                    <small class="muted">${escapeHtml(e.archivo || '')} · ${e.movimientos} movimientos leídos</small></div>
                ${e.cierra ? '<span class="badge badge-activa">✓ Los saldos cierran</span>'
                           : '<span class="badge badge-inactiva">⚠ Los saldos no cierran: revisá el archivo</span>'}
            </div>
            <div class="extracto-cuerpo">
                <div class="extracto-saldos">
                    <div><span class="muted">Saldo inicial</span><b>${fmtMoneda(e.saldo_inicial)}</b></div>
                    <div><span class="muted">Saldo final</span><b>${fmtMoneda(e.saldo_final)}</b></div>
                    <div><span class="muted">Variación</span><b style="color:var(--${e.saldo_final >= e.saldo_inicial ? 'success' : 'danger'})">${fmtMoneda(e.saldo_final - e.saldo_inicial)}</b></div>
                </div>
                <table><thead><tr><th>Tipo de movimiento</th><th class="num">Cant.</th><th class="num">Total</th></tr></thead><tbody>${filas}</tbody></table>
            </div>
            ${comis ? `<div class="extracto-pie">
                ${e.comisiones_gasto_id
                    ? `<span class="pago-ok">✓ Comisiones e impuestos del mes ya registrados como gasto (${fmtMoneda(Math.abs(comis.total))})</span>`
                    : `<span class="muted">${comis.cantidad} débitos de comisiones, IVA e impuesto al cheque por <b>${fmtMoneda(Math.abs(comis.total))}</b>.</span>
                       <button class="btn btn-sm btn-primary" onclick="registrarComisiones(${e.id})">Registrarlos como un gasto bancario</button>`}
            </div>` : ''}
        </div>`;
        cont.innerHTML += htmlListaExtractos(lista);
    } catch (err) { cont.innerHTML = ''; }
}

// Lista de extractos importados con opción de eliminarlos (p. ej. los subidos de prueba)
function htmlListaExtractos(lista) {
    const esAdmin = usuarioActual.rol === 'admin';
    return `<div class="card extractos-lista">
        <div class="extractos-lista-head"><h3 style="margin:0">Extractos importados (${lista.length})</h3><span style="flex:1"></span>
            ${esAdmin ? `<button class="btn btn-sm btn-danger" onclick="eliminarTodosExtractos()"><svg class="ic"><use href="#i-trash"/></svg>Eliminar todos los extractos</button>` : ''}</div>
        <div class="tabla-wrap"><table><thead><tr><th>Período</th><th>Archivo</th><th class="num">Movimientos</th><th>Importado</th><th></th></tr></thead><tbody>
        ${lista.map(e => `<tr><td><b>${fmtFecha(e.desde)} al ${fmtFecha(e.hasta)}</b></td><td>${escapeHtml(e.archivo || '')}</td>
            <td class="num">${e.movimientos}</td><td>${e.creado ? fmtFechaHora(e.creado) : ''}</td>
            <td>${esAdmin ? `<button class="btn btn-sm btn-ghost" onclick="eliminarExtracto(${e.id}, '${escapeHtml((e.archivo || '').replace(/'/g, ''))}')">Eliminar</button>` : ''}</td></tr>`).join('')}
        </tbody></table></div></div>`;
}

const AVISO_BORRAR_EXTRACTO = 'Se borran los movimientos del banco. Las facturas que estaban conciliadas con ellos vuelven a quedar pendientes, y los gastos que se crearon desde el extracto (comisiones bancarias y pagos sin factura) se borran. No se puede deshacer.';

async function eliminarExtracto(id, archivo) {
    if (!confirm(`¿Eliminar el extracto ${archivo || ''}?

${AVISO_BORRAR_EXTRACTO}`)) return;
    try { const r = await api(`/api/conciliacion/extractos/${id}`, { method: 'DELETE' }); toast(r.mensaje); cargarConciliacion(); }
    catch (e) { toast(e.message, 'error'); }
}

async function eliminarTodosExtractos() {
    if (!confirm(`¿Eliminar TODOS los extractos bancarios importados?

${AVISO_BORRAR_EXTRACTO}`)) return;
    if (prompt('Para confirmar escribí BORRAR') !== 'BORRAR') return toast('No se borró nada', 'error');
    try { const r = await api('/api/conciliacion/extractos', { method: 'DELETE' }); toast(r.mensaje); cargarConciliacion(); }
    catch (e) { toast(e.message, 'error'); }
}

async function registrarComisiones(id) {
    try {
        const r = await api(`/api/conciliacion/extractos/${id}/registrar-comisiones`, { method: 'POST' });
        toast(r.mensaje);
        cargarPanelExtracto();
    } catch (err) { toast(err.message, 'error'); }
}

// Pagos sin factura de proveedor (AFIP, seguros, servicios): crear el gasto desde el banco
async function crearGastoDesdePago(movId) {
    const m = concCache.find(x => x.id === movId);
    if (!m) return;
    await cargarGastosMeta().catch(() => {});
    const cats = (gastosMeta ? gastosMeta.categorias : CATEGORIAS_GASTO).map(c => `<option>${escapeHtml(c)}</option>`).join('');
    document.getElementById('modal-content').innerHTML = `
        <h3>Crear gasto desde este pago</h3>
        <p class="muted" style="margin-top:-0.4rem">${fmtFecha(m.fecha)} · ${escapeHtml(TIPOS_BANCO[m.concepto] || 'Pago')} ·
            <b>${fmtMoneda(Math.abs(m.importe))}</b><br>${escapeHtml(m.descripcion || '')}</p>
        <p class="muted">Usalo para pagos que no tienen factura de proveedor (AFIP, seguros, servicios con débito directo).
            Si hay factura, cargala en Gastos y usá <b>Vincular factura</b>.</p>
        <form onsubmit="confirmarGastoDesdePago(event, ${movId})">
            <label class="mc-lbl" for="cg-razon">Nombre / razón social</label>
            <input id="cg-razon" class="mc-inp" value="${escapeHtml(m.razon_social || '')}">
            <label class="mc-lbl" for="cg-concepto">Concepto</label>
            <input id="cg-concepto" class="mc-inp" value="${escapeHtml(TIPOS_BANCO[m.concepto] || '')}" required>
            <div class="form-grid">
                <div><label class="mc-lbl" for="cg-rubro">Rubro</label><input id="cg-rubro" class="mc-inp" placeholder="ej: Impuestos, Seguros, Servicios"></div>
                <div><label class="mc-lbl" for="cg-cat">Categoría</label><select id="cg-cat" class="mc-inp"><option value="">—</option>${cats}</select></div>
            </div>
            <div class="form-actions"><button type="submit" class="btn btn-primary">Crear gasto y conciliar</button>
                <button type="button" class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button></div>
        </form>`;
    document.getElementById('modal-overlay').style.display = 'flex';
}

async function confirmarGastoDesdePago(e, movId) {
    e.preventDefault();
    const v = id => document.getElementById(id).value.trim() || null;
    try {
        const r = await api(`/api/conciliacion/${movId}/crear-gasto`, { method: 'POST',
            body: JSON.stringify({ razon_social: v('cg-razon'), concepto: v('cg-concepto'), rubro: v('cg-rubro'), categoria: v('cg-cat') }) });
        toast(r.mensaje);
        cerrarModal();
        cargarConciliacion();
    } catch (err) { toast(err.message, 'error'); }
}

function renderConciliacion(lista) {
    document.getElementById('body-conc').innerHTML = lista.map(m => {
        const fecha = fmtFecha(m.fecha);
        const tipo = TIPOS_BANCO[m.concepto] || m.concepto || '—';
        let estado, acciones;
        const btnSueldo = `<button class="btn btn-sm" onclick="abrirSinFactura(${m.id})" title="Sueldo, cargas sociales o transferencia devuelta: no lleva factura y sale de los pendientes">Sin factura</button>`;
        if (m.sin_factura) {
            const SF = { sueldo: ['Sueldo', 'no lleva factura'], afip: ['AFIP', 'impuestos, no lleva factura'], devuelta: ['Devuelta', 'se reintegró a la cuenta'], cargas_sociales: ['Cargas sociales', 'no lleva factura'] };
            const [et, det] = SF[m.sin_factura] || [m.sin_factura, 'no lleva factura'];
            estado = `<span class="conc-sf">${et}</span> <span style="color:var(--text-muted)">· ${escapeHtml(m.sin_factura_nota || det)}</span>`;
            acciones = `<button class="btn btn-sm" onclick="marcarSinFactura(${m.id}, null)" title="Volver a dejarlo pendiente de conciliar">Deshacer</button>`;
        } else if (m.rendicion) {  // transferencia a un encargado de compras: se rinde con facturas de otros proveedores
            estado = htmlEstadoRendicion(m);
            acciones = `<div class="td-acc"><button class="btn btn-sm ${m.conciliado ? '' : 'btn-primary'}" onclick="abrirRendicion(${m.id})">${m.conciliado ? 'Ver rendición' : 'Rendir facturas'}</button>
                ${!m.conciliado && !m.rendicion.facturas ? btnSueldo : ''}</div>`;
        } else if (m.conciliado && m.gasto) {
            const g = m.gasto;
            const fg = g.fecha ? g.fecha.split('-').reverse().join('/') : '';
            const badge = m.conciliado_manual ? 'manual' : 'auto';
            estado = `<span class="conc-ok">✓ ${badge}</span> ${escapeHtml(g.razon_social || '')}
                <span style="color:var(--text-muted)">· ${escapeHtml(g.concepto || '')} · ${fg}</span>
                ${m.nota_conciliacion ? `<div class="conc-dif">Factura ${fmtMoneda(g.importe)}: ${escapeHtml(m.nota_conciliacion)}</div>` : ''}`;
            acciones = `<button class="btn btn-sm" onclick="desconciliar(${m.id})">Deshacer</button>`;
        } else {
            estado = '<span class="conc-pend">● pendiente</span>';
            acciones = `<div class="td-acc"><button class="btn btn-sm btn-primary" onclick="abrirCandidatos(${m.id})" title="Elegir la factura que corresponde a este pago">Vincular</button>
                <button class="btn btn-sm" onclick="crearGastoDesdePago(${m.id})" title="Para pagos sin factura de proveedor">Crear gasto</button>
                ${Number(m.importe) < 0 ? `<button class="btn btn-sm" onclick="abrirRendicion(${m.id})" title="La transferencia fue a una persona que compró para APAI (reintegro o adelanto)">Encargado</button>` : ''}
                ${btnSueldo}</div>`;
        }
        return `<tr>
            <td>${fecha}</td>
            <td>${tipo}</td>
            <td>${escapeHtml(m.cuit || '-')}</td>
            <td>${escapeHtml(m.razon_social || '—')}</td>
            <td style="text-align:right">${fmtMoneda(Math.abs(m.importe))}</td>
            <td>${estado}</td>
            <td>${acciones}</td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No hay movimientos. Subí un extracto para empezar.</td></tr>';
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
        const cierre = data.cierra === undefined ? ''
            : data.cierra ? '<p class="mc-ok">✓ Los saldos del extracto cierran: se leyeron todos los movimientos.</p>'
                          : `<p style="color:var(--danger);font-weight:600">⚠ Los saldos no cierran (diferencia ${fmtMoneda(data.diferencia)}). Revisá que el PDF sea el extracto completo.</p>`;
        document.getElementById('modal-content').innerHTML = `
            <h3>Extracto importado</h3>
            ${data.periodo ? `<p class="muted" style="margin-top:-0.4rem">Período del ${fmtFecha(data.periodo[0])} al ${fmtFecha(data.periodo[1])} · ${data.movimientos_leidos} movimientos leídos</p>` : ''}
            ${cierre}
            <div class="gasto-resumen">
                <div class="gasto-kpi"><div class="gasto-kpi-label">Pagos nuevos</div><div class="gasto-kpi-valor">${data.nuevos}</div><div class="gasto-kpi-sub">${data.duplicados ? data.duplicados + ' ya estaban cargados' : 'para conciliar'}</div></div>
                <div class="gasto-kpi"><div class="gasto-kpi-label">Conciliados solos</div><div class="gasto-kpi-valor" style="color:var(--success)">${data.conciliados_automaticamente}</div><div class="gasto-kpi-sub">CUIT + importe</div></div>
                <div class="gasto-kpi"><div class="gasto-kpi-label">Para revisar</div><div class="gasto-kpi-valor" style="color:var(--warning)">${data.pendientes}</div><div class="gasto-kpi-sub">vinculá la factura o creá el gasto</div></div>
            </div>
            ${data.afip ? `<p class="muted">${data.afip} débito${data.afip === 1 ? '' : 's'} de AFIP quedaron aparte: no llevan factura ni cuentan como pendientes.</p>` : ''}
            <p class="muted">En los pendientes usá <b>Vincular</b> si la factura ya está cargada, <b>Encargado</b> si se le transfirió a quien hizo la compra, o <b>Sueldo</b> si la transferencia fue un sueldo.</p>`;
        document.getElementById('modal-overlay').style.display = 'flex';
        cargarConciliacion();
    } catch (err) {
        toast(err.message, 'error');
    } finally {
        input.value = '';  // permite volver a subir el mismo archivo
    }
}

// Egresos que no llevan factura: sueldo (transferencia o DEBIN a un CUIT), cargas sociales, o devuelta (con nota)
function abrirSinFactura(movId) {
    const m = (concCache || []).find(x => x.id === movId) || {};
    const puedeSueldo = ['190', '190100', 'F30', 'F30100'].includes(m.concepto) && (m.cuit || '').replace(/\D/g, '').length === 11;
    document.getElementById('modal-content').innerHTML = `
        <h2 style="margin-top:0">Egreso sin factura</h2>
        <p class="muted" style="margin-top:-0.4rem">${fmtFecha(m.fecha)} · ${escapeHtml(m.razon_social || m.descripcion || '')} · <b>${fmtMoneda(Math.abs(m.importe || 0))}</b></p>
        <p>Sale de los pendientes de conciliar y no se le pide factura.</p>
        <div class="sf-opciones">
            ${puedeSueldo ? `<button class="btn" onclick="marcarSinFactura(${movId}, 'sueldo')"><b>Sueldo</b><small>Transferencia a un empleado</small></button>` : ''}
            <button class="btn" onclick="marcarSinFactura(${movId}, 'cargas_sociales')"><b>Cargas sociales</b><small>Aportes, contribuciones, ART, sindicato</small></button>
            <button class="btn" onclick="marcarSinFactura(${movId}, 'devuelta')"><b>Devuelta</b><small>Se transfirió por error y la reintegraron</small></button>
        </div>
        <label for="sf-nota" style="margin-top:0.9rem">Nota <span class="muted">(obligatoria si fue devuelta: cuándo y de quién volvió la plata)</span></label>
        <input type="text" id="sf-nota" maxlength="300" placeholder="Ej.: F.931 de agosto · Devuelta el 29/09 por …">
        <div class="form-actions"><button class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button></div>`;
    document.getElementById('modal-overlay').style.display = 'flex';
}

async function marcarSinFactura(movId, motivo) {
    const nota = motivo ? ((document.getElementById('sf-nota') || {}).value || '').trim() : null;
    if (motivo === 'devuelta' && !nota) { toast('Anotá cuándo y de quién volvió la plata', 'error'); return; }
    try {
        await api(`/api/conciliacion/${movId}/sin-factura`, { method: 'POST', body: JSON.stringify({ motivo, nota }) });
        if (motivo) cerrarModal();
        toast(motivo ? 'Marcado: ' + ({ sueldo: 'sueldo', cargas_sociales: 'cargas sociales', devuelta: 'devuelta' }[motivo] || motivo) : 'Volvió a quedar pendiente de conciliar');
        cargarConciliacion();
    } catch (e) { toast(e.message, 'error'); }
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
        const resp = await api(`/api/conciliacion/${movId}/candidatos`);
        const cands = resp.facturas || [];
        const filas = cands.map(c => {
            const f = c.fecha ? c.fecha.split('-').reverse().join('/') : '';
            const tags = [c.coincide_cuit ? '<span class="conc-tag-ok">CUIT ✓</span>' : '',
                c.coincide_nombre ? '<span class="conc-tag-ok">Razón social ✓</span>' : '',
                c.coincide_monto ? '<span class="conc-tag-ok">Importe ✓</span>' : `<span class="conc-tag-dif">Dif. ${fmtMoneda(c.diferencia)}</span>`].join(' ');
            return `<tr>
                <td>${f}</td>
                <td>${escapeHtml(c.razon_social || '-')}<br><small style="color:var(--text-muted)">${escapeHtml(c.concepto || '')}</small></td>
                <td>${escapeHtml(c.cuit || '-')}</td>
                <td style="text-align:right">${fmtMoneda(c.importe)}</td>
                <td>${tags}</td>
                <td><button class="btn btn-sm btn-primary" onclick="matchManual(${movId},${c.id},${c.coincide_monto ? 0 : c.importe})">Vincular</button></td>
            </tr>`;
        }).join('') ||
            `<tr><td colspan="6">No hay facturas libres con ese CUIT ni ese importe.
                ${resp.proveedor ? `El proveedor <b>${escapeHtml(resp.proveedor)}</b> está cargado: falta su factura en Gastos.` : 'Cargá la factura en Gastos'}
                o usá <b>Crear gasto</b> si es un pago sin factura.</td></tr>`;
        const html = `
            <h2 style="margin-top:0">Vincular movimiento con una factura</h2>
            <p style="color:var(--text-muted);margin-top:-0.4rem">
                ${mov ? `${escapeHtml(mov.razon_social || mov.descripcion || '')} · CUIT ${escapeHtml(mov.cuit || '-')} · ${fmtMoneda(Math.abs(mov.importe))}` : ''}
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

// Importes distintos (ej. nota de crédito, interés, redondeo): se pide el motivo y queda anotado
function motivoDiferencia(pagado, facturado) {
    const dif = Math.abs(pagado) - Math.abs(facturado);
    const nota = prompt(`El banco muestra ${fmtMoneda(Math.abs(pagado))} y la factura es de ${fmtMoneda(Math.abs(facturado))}: `
        + `se pagó ${fmtMoneda(Math.abs(dif))} ${dif > 0 ? 'de más' : 'de menos'}.\n\n¿Por qué? Queda anotado en la factura y en la conciliación.`,
        dif < 0 ? 'Nota de crédito por la diferencia' : 'Intereses o recargo por pago fuera de término');
    return nota === null ? null : nota.trim();
}

async function matchManual(movId, gastoId, importeFactura) {
    let nota = null;
    if (importeFactura) {
        const mov = concCache.find(m => m.id === movId) || {};
        nota = motivoDiferencia(mov.importe, importeFactura);
        if (nota === null) return;
        if (!nota) { toast('Anotá el motivo de la diferencia', 'error'); return; }
    }
    try {
        await api(`/api/conciliacion/${movId}/match/${gastoId}`, { method: 'POST', body: JSON.stringify({ nota }) });
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

// =========================================================
// --- CUOTAS: pestañas, pagos SIRO y cursos ---
// =========================================================
function cargarCuotasSec() {
    cuotaTab('pagos');
}

function cuotaTab(tab) {
    document.querySelectorAll('.cuota-tab').forEach(b =>
        b.classList.toggle('activo', b.dataset.tab === tab));
    ['pagos', 'estado', 'stats', 'cursos'].forEach(t =>
        document.getElementById('cuotas-tab-' + t).style.display = t === tab ? 'block' : 'none');
    if (tab === 'pagos') cargarPagosSiro();
    else if (tab === 'estado') cargarEstado();
    else if (tab === 'stats') cargarStats();
    else if (tab === 'cursos') cargarCursos();
}

// Ordenador genérico para tablas
function ordenarLista(lista, sort, numericos, accessors) {
    const dir = sort.asc ? 1 : -1;
    const get = (o, c) => accessors && accessors[c] ? accessors[c](o) : o[c];
    return lista.slice().sort((a, b) => {
        const va = get(a, sort.campo), vb = get(b, sort.campo);
        if (numericos.has(sort.campo)) return ((Number(va) || 0) - (Number(vb) || 0)) * dir;
        return normTxt(va).localeCompare(normTxt(vb)) * dir;
    });
}

// ---- Estado de cuenta ----
let estadoCache = [];
let estadoSort = { campo: 'deuda_total', asc: false };
function sortEstado(campo) {
    estadoSort.asc = estadoSort.campo === campo ? !estadoSort.asc : true;
    estadoSort.campo = campo;
    filtrarEstado();
}

async function cargarEstado() {
    try {
        const p = new URLSearchParams();
        const area = document.getElementById('estado-f-area').value;
        const est = document.getElementById('estado-f-estado').value;
        if (area) p.set('area', area);
        if (est && est !== 'debe-anterior') p.set('estado', est);
        const r = await api('/api/cuotas/estado?' + p.toString());
        estadoCache = (r.alumnos || []).filter(x => est !== 'debe-anterior' || (x.estado || '').startsWith('Al día ·'));
        const tot = estadoCache.length;
        const aldia = estadoCache.filter(x => x.estado === 'Al día' || x.estado === 'Pagado').length;
        const debeAnt = estadoCache.filter(x => x.deuda_anterior > 0).length;
        const mor = estadoCache.filter(x => x.estado === 'Moroso').length;
        const sinp = estadoCache.filter(x => x.estado === 'Sin pagos').length;
        const deuda = estadoCache.reduce((s, x) => s + (x.deuda_total ?? x.deuda), 0);
        document.getElementById('estado-resumen').innerHTML = `
            <div class="gasto-kpi"><div class="gasto-kpi-label">Alumnos</div><div class="gasto-kpi-valor">${tot}</div><div class="gasto-kpi-sub">cuotas vencidas hasta ${MESES[r.mes_corte - 1] ? MESES[r.mes_corte - 1].toLowerCase() : 'el mes ' + r.mes_corte}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Al día (sin deuda anterior)</div><div class="gasto-kpi-valor" style="color:var(--green)">${aldia}</div><div class="gasto-kpi-sub">${debeAnt} deben el año anterior</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Morosos / sin pagos</div><div class="gasto-kpi-valor" style="color:var(--warning)">${mor + sinp}</div><div class="gasto-kpi-sub">${mor} mor. · ${sinp} s/pago</div></div>
            <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Deuda total</div><div class="gasto-kpi-valor">${fmtMoneda(deuda)}</div><div class="gasto-kpi-sub">al corte</div></div>`;
        filtrarEstado();
    } catch (err) { toast(err.message, 'error'); }
}

function estadoBadge(e) {
    e = e || '';
    // "Al día · debe 2025": al día con el año, pero con deuda del anterior (no se mezcla con el verde)
    const m = e.match(/^Al día · debe (\d{4})$/);
    if (m) return `<span style="color:var(--green);font-weight:700">Al día</span> <span class="badge badge-revisar" title="Debe cuotas del ${m[1]}">debe ${m[1]}</span>`;
    const col = { 'Al día': 'var(--green)', 'Pagado': 'var(--green)', 'Moroso': 'var(--red)', 'Sin pagos': '#d97706', 'Becado': 'var(--sky)', 'Exento': 'var(--sky)' }[e] || 'var(--text-muted)';
    return `<span style="color:${col};font-weight:700">${escapeHtml(e)}${e === 'Pagado' ? ' ✓' : ''}</span>`;
}

function filtrarEstado() {
    const q = normTxt(document.getElementById('buscar-estado').value);
    let lista = estadoCache.filter(x => !q ||
        normTxt(`${x.apellido} ${x.nombre} ${x.legajo}`).includes(q));
    lista = ordenarLista(lista, estadoSort,
        new Set(['legajo', 'pagado', 'esperado', 'deuda', 'deuda_total']),
        { alumno: o => o.apellido });
    document.getElementById('body-estado').innerHTML = lista.slice(0, 800).map(x => `
        <tr>
            <td>${escapeHtml(x.legajo)}</td>
            <td>${escapeHtml(x.apellido)}, ${escapeHtml(x.nombre)}</td>
            <td>${escapeHtml(x.curso || '-')}${x.cursos_nombres && x.cursos_nombres.length > 1 ? `<br><span class="badge">${x.cursos_nombres.length} cursos</span>` : ''}</td>
            <td>${escapeHtml(x.area || '-')}</td>
            <td style="text-align:right">${fmtMoneda(x.pagado)}</td>
            <td style="text-align:right">${fmtMoneda(x.esperado)}</td>
            <td style="text-align:right;${(x.deuda_total ?? x.deuda) > 0 ? 'color:var(--red)' : ''}">${fmtMoneda(x.deuda_total ?? x.deuda)}${x.detalle_deuda ? `<br><span style="font-size:.72rem;color:var(--text-muted)">${escapeHtml(x.detalle_deuda.replace(/^Debe /, ''))}</span>` : ''}${x.deuda_anterior > 0 ? `<br><span style="font-size:.72rem;color:var(--text-muted)">(incl. ${fmtMoneda(x.deuda_anterior)} año ant.)</span>` : ''}</td>
            <td>${estadoBadge(x.estado)}</td>
            <td><button class="btn btn-sm" onclick="verEstadoAlumno(${x.id})">Ver</button></td>
        </tr>`).join('') ||
        '<tr><td colspan="9" style="text-align:center;color:var(--text-muted)">Sin resultados</td></tr>';
}

async function verEstadoAlumno(id) {
    try {
        const [e, cupones] = await Promise.all([api(`/api/cuotas/estado/${id}`), api(`/api/cupones-siro/alumno/${id}`).catch(() => [])]);
        setTimeout(() => cargarCursosAlumno(id), 0);
        document.getElementById('modal-content').innerHTML = `
            <h2 style="margin-top:0">${escapeHtml(e.apellido)}, ${escapeHtml(e.nombre)}</h2>
            <p style="color:var(--text-muted);margin-top:-.4rem">Legajo ${escapeHtml(e.legajo)} · ${escapeHtml(e.curso || '')} · ${escapeHtml(e.area || '')}</p>
            ${htmlCuentaAlumno(e, cupones)}
            <div class="form-actions"><button class="btn btn-outline" onclick="cerrarModal();verAlumno(${e.id})">Ver ficha completa</button>
            ${usuarioActual.rol === 'admin' ? `<button class="btn btn-ghost" onclick="verComoFamilia(${e.id})">Ver como familia</button>` : ''}
            <button class="btn" onclick="cerrarModal()">Cerrar</button></div>`;
        const ov = document.getElementById('modal-overlay');
        ov.querySelector('.modal').classList.add('modal-ancho');
        ov.style.display = 'flex';
    } catch (err) { toast(err.message, 'error'); }
}

// Estado de cuenta cuota por cuota + pagos imputados + cupones vigentes (ficha del alumno)
function htmlCuentaAlumno(e, cupones) {
    const cp = e.curso_param;
    return `<h4 style="margin:1rem 0 0.2rem">Estado de cuenta ${e.anio} · ${estadoBadge(e.estado)}</h4>
        <p class="muted" style="margin:0">${cp ? `${escapeHtml(cp.nombre)} · cuota ${fmtMoneda(e.cuota || cp.cuota)} × ${cp.n_cuotas}${cp.matricula ? ' + matrícula ' + fmtMoneda(cp.matricula) : ''} · ` : ''}pagado en el año ${fmtMoneda(e.pagado)}</p>
        ${htmlResumenDeuda(e)}
        <div id="ac-${e.id}" class="ac-bloque"></div>
        ${htmlCuotasGrid(e)}
        <h4 style="margin:0.8rem 0 0.2rem">Pagos del año</h4>
        ${htmlPagosImputados(e.pagos, e.cursos)}
        <h4 style="margin:1rem 0 0.4rem">Cupones vigentes en el portal</h4>
        ${cupones && cupones.length ? cupones.map(htmlCupon).join('') : '<p class="muted">No tiene cupones vigentes cargados.</p>'}`;
}

// ---- Estadisticas ----
let chartCuotasMensual = null, chartCuotasArea = null, statsUltimo = null;

// Estadísticas de cuotas: comparativa de cursos (como la hoja COMPARATIVA CURSOS de la planilla), siempre A LA FECHA
let chartCuotasCvd = null;
const COLORES_AREA = { 'Ciclo Basico': '#2563eb', 'Avionica': '#059669', 'Mecanica': '#d97706', 'Aeronavegantes': '#7c3aed', 'Examenes': '#be123c' };
const NOMBRE_AREA = { 'Ciclo Basico': 'Ciclo Básico', 'Avionica': 'Aviónica', 'Mecanica': 'Mecánica', 'Aeronavegantes': 'Aeronavegantes', 'Examenes': 'Exámenes' };
const nomArea = a => NOMBRE_AREA[a] || a;
const colorArea = a => COLORES_AREA[a] || '#64748b';
const pct = (v, dec = 1) => fmtNumero(v || 0, dec) + '%';
const millones = v => '$' + (Math.abs(v) >= 1e6 ? fmtNumero(v / 1e6, 1) + ' M' : Math.abs(v) >= 1000 ? fmtNumero(v / 1000, 0) + ' mil' : v);
const hexA = (hex, a) => { const h = hex.replace('#', ''); return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`; };

function exportarEstadisticasCSV() {
    if (!statsUltimo) return toast('Abrí primero las estadísticas', 'error');
    const s = statsUltimo, filas = [['Curso', 'Área', 'Alumnos', 'Becados', 'Al día', 'Pagado', 'Al día (debe año anterior)', 'Moroso', 'Sin pagos', 'Cobrado a la fecha', 'Esperado a la fecha', 'Deuda a la fecha', '% Cumpl.']];
    s.por_curso.forEach(d => filas.push([d.clave, nomArea(d.area), d.alumnos, d.becados, d.al_dia, d.pagado, d.al_dia_debe_anterior, d.moroso, d.sin_pagos,
        d.cobrado, d.esperado, d.deuda, String(d.cumplimiento).replace('.', ',')]));
    filas.push([]); filas.push(['Mes', ...s.mensual.areas.map(nomArea), 'Total']);
    s.mensual.meses.forEach(x => filas.push([MESES[x.mes - 1], ...s.mensual.areas.map(a => x.valores[a]), x.total]));
    const csv = '﻿' + filas.map(f => f.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(';')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `comparativa_cursos_${s.anio}${s.mes ? '_' + s.mes : ''}.csv`;
    a.click();
}

function exportarEstadisticasPDF() {
    if (!statsUltimo) { toast('Abrí primero las estadísticas', 'error'); return; }
    if (typeof window.jspdf === 'undefined') { toast('No se pudo cargar el generador de PDF', 'error'); return; }
    const s = statsUltimo, k = s.indicadores;
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'landscape' });
    const fmt = n => '$' + Number(n || 0).toLocaleString('es-AR', { maximumFractionDigits: 0 });
    doc.setFontSize(15); doc.text('APAI — Comparativa de cursos', 14, 15);
    doc.setFontSize(10); doc.setTextColor(110);
    doc.text(`A la fecha: cuotas vencidas hasta ${MESES[s.mes_corte - 1] ? MESES[s.mes_corte - 1].toLowerCase() : '-'} ${s.anio} · generado ${fmtFecha(hoyISO())}`, 14, 21);
    doc.setTextColor(20);
    doc.autoTable({ startY: 26, theme: 'plain', styles: { fontSize: 10 }, columnStyles: { 0: { fontStyle: 'bold' } },
        body: [['Alumnos', k.alumnos], ['Cobrado a la fecha', fmt(k.cobrado)], ['Esperado a la fecha', fmt(k.esperado)], ['Deuda a la fecha', fmt(k.deuda)],
               ['% Cumplimiento', pct(k.cumplimiento)], ['Con deuda del año anterior', `${k.con_deuda_anterior} alumnos · ${fmt(k.deuda_anterior)}`]] });
    const tabla = (titulo, filas) => doc.autoTable({ startY: doc.lastAutoTable.finalY + 6, styles: { fontSize: 8 }, headStyles: { fillColor: [21, 35, 59] },
        head: [[titulo, 'Área', 'Alumnos', 'Becados', 'Al día', 'Pagado', 'Al día (debe ant.)', 'Moroso', 'Sin pagos', 'Cobrado', 'Esperado', 'Deuda', '% Cumpl.']],
        body: filas.map(d => [d.clave, nomArea(d.area), d.alumnos, d.becados, d.al_dia, d.pagado, d.al_dia_debe_anterior, d.moroso, d.sin_pagos,
                              fmt(d.cobrado), fmt(d.esperado), fmt(d.deuda), pct(d.cumplimiento)]) });
    tabla('Curso', s.por_curso);
    tabla('Grupo', s.por_grupo);
    doc.save(`comparativa_cursos_${s.anio}${s.mes ? '_' + String(s.mes).padStart(2, '0') : ''}.pdf`);
}

// ---------------------------------------------------------------- PDF para compartir: recaudación por área
// Logo para los PDF, achicado a 256 px (el original pesa 750 KB y hacía PDF de 8 a 30 MB)
let _logoPDF = null;
async function _imagenLogo() {
    if (_logoPDF) return _logoPDF;
    try {
        const img = new Image();
        await new Promise((ok, mal) => { img.onload = ok; img.onerror = mal; img.src = '/static/logo.png'; });
        const lado = 256, c = document.createElement('canvas');
        c.width = c.height = lado;
        c.getContext('2d').drawImage(img, 0, 0, lado, lado);
        _logoPDF = c.toDataURL('image/png');
        return _logoPDF;
    } catch { return null; }
}

// Dibuja un gráfico fuera de pantalla (alta resolución) y devuelve la imagen PNG
function _graficoImagen(config, ancho, alto) {
    const cv = document.createElement('canvas');
    cv.width = ancho; cv.height = alto;
    cv.style.cssText = 'position:fixed;left:-99999px;top:0';
    document.body.appendChild(cv);
    config.options = { ...(config.options || {}), responsive: false, animation: false, devicePixelRatio: 2 };
    const ch = new Chart(cv, config);
    const img = ch.toBase64Image('image/png', 1);
    ch.destroy(); cv.remove();
    return img;
}

async function exportarDesglosePDF() {
    if (!statsUltimo) return toast('Abrí primero las estadísticas', 'error');
    if (typeof window.jspdf === 'undefined') return toast('No se pudo cargar el generador de PDF', 'error');
    const s = statsUltimo, m = s.mensual;
    const meses = m.meses.filter(x => x.total > 0 || x.mes <= (s.mes_corte || 12));
    const ultimo = meses.length ? meses[meses.length - 1].mes : 12;
    const total = m.total;
    const areas = m.areas.filter(a => m.totales[a] > 0);
    const fmt = n => '$ ' + Number(n || 0).toLocaleString('es-AR', { maximumFractionDigits: 0 });
    const rgb = hex => [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight();
    const logo = await _imagenLogo();

    // Encabezado
    doc.setFillColor(21, 35, 59); doc.rect(0, 0, W, 30, 'F');
    doc.setFillColor(160, 30, 34); doc.rect(0, 30, W, 1.4, 'F');
    if (logo) { doc.setFillColor(255, 255, 255); doc.circle(21, 15, 9.5, 'F'); doc.addImage(logo, 'PNG', 12.5, 6.5, 17, 17); }
    doc.setTextColor(255, 255, 255); doc.setFont('helvetica', 'bold'); doc.setFontSize(17);
    doc.text('Recaudación de cuotas por área', 36, 14);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(10); doc.setTextColor(200, 214, 234);
    doc.text(`Asociación de Padres y Alumnos del I.N.A.C. · ${MESES[0]} a ${MESES[ultimo - 1].toLowerCase()} ${s.anio}`, 36, 21);
    doc.setFontSize(8.5); doc.text(`Generado el ${fmtFecha(hoyISO())}`, W - 14, 21, { align: 'right' });

    // Total recaudado
    doc.setTextColor(91, 107, 128); doc.setFontSize(9); doc.text('TOTAL RECAUDADO', 14, 42);
    doc.setTextColor(21, 35, 59); doc.setFont('helvetica', 'bold'); doc.setFontSize(24); doc.text(fmt(total), 14, 52);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(91, 107, 128);
    doc.text(`${meses.filter(x => x.total > 0).length} meses con cobranza · promedio mensual ${fmt(total / Math.max(1, meses.filter(x => x.total > 0).length))}`, 14, 58);

    // Participación por área: tabla + torta
    doc.autoTable({
        startY: 64, margin: { left: 14, right: W / 2 + 4 }, theme: 'plain',
        head: [['Área', 'Monto', '% del total']],
        body: areas.map(a => ['    ' + nomArea(a), fmt(m.totales[a]), pct(total ? m.totales[a] / total * 100 : 0)]),
        foot: [['Total', fmt(total), '100%']],
        styles: { fontSize: 10, cellPadding: { top: 3, bottom: 3, left: 2, right: 2 }, textColor: [30, 41, 59] },
        headStyles: { fontStyle: 'bold', textColor: [91, 107, 128], fontSize: 8.5, lineWidth: { bottom: 0.3 }, lineColor: [210, 218, 230] },
        footStyles: { fontStyle: 'bold', lineWidth: { top: 0.3 }, lineColor: [210, 218, 230] },
        columnStyles: { 1: { halign: 'right' }, 2: { halign: 'right', fontStyle: 'bold' } },
        didDrawCell: d => {
            if (d.section === 'body' && d.column.index === 0) {
                doc.setFillColor(...rgb(colorArea(areas[d.row.index])));
                doc.roundedRect(d.cell.x + 2, d.cell.y + d.cell.height / 2 - 2, 4, 4, 1, 1, 'F');
            }
        },
    });
    const torta = _graficoImagen({
        type: 'doughnut',
        data: { labels: areas.map(nomArea), datasets: [{ data: areas.map(a => m.totales[a]), backgroundColor: areas.map(colorArea), borderColor: '#fff', borderWidth: 3 }] },
        options: { cutout: '62%', plugins: { legend: { display: false }, tooltip: { enabled: false } } },
        plugins: [{ id: 'centro', afterDraw(ch) {
            const { ctx, chartArea: c } = ch; const x = (c.left + c.right) / 2, y = (c.top + c.bottom) / 2;
            ctx.save(); ctx.textAlign = 'center'; ctx.fillStyle = '#5b6b80'; ctx.font = '600 22px Inter, sans-serif'; ctx.fillText('Total', x, y - 14);
            ctx.fillStyle = '#15233b'; ctx.font = '700 30px Inter, sans-serif'; ctx.fillText(millones(total), x, y + 22); ctx.restore();
        } }, { id: 'porcentajes', afterDatasetsDraw(ch) {
            const { ctx } = ch; const meta = ch.getDatasetMeta(0);
            ctx.save(); ctx.font = '700 20px Inter, sans-serif'; ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            meta.data.forEach((arc, i) => { const v = areas[i] ? m.totales[areas[i]] / total * 100 : 0; if (v < 4) return;
                const p = arc.tooltipPosition(); ctx.fillText(Math.round(v) + '%', p.x, p.y); });
            ctx.restore();
        } }],
    }, 520, 520);
    doc.addImage(torta, 'PNG', W / 2 + 12, 60, 62, 62);

    // Evolución mensual (barras apiladas por área)
    const yBarras = Math.max(doc.lastAutoTable.finalY, 124) + 8;
    doc.setTextColor(21, 35, 59); doc.setFont('helvetica', 'bold'); doc.setFontSize(12); doc.text('Cobranza mes a mes', 14, yBarras);
    const altoBarras = Math.min((W - 28) * 0.55, H - yBarras - 22);
    const barras = _graficoImagen(_configMensual(meses, areas, null, true), 1400, Math.round(1400 * altoBarras / (W - 28)));
    doc.addImage(barras, 'PNG', 14, yBarras + 3, W - 28, altoBarras);

    // Página 2: tabla del desglose mensual (entera, sin cortes)
    doc.addPage();
    doc.setFillColor(21, 35, 59); doc.rect(0, 0, W, 16, 'F');
    doc.setFillColor(160, 30, 34); doc.rect(0, 16, W, 1, 'F');
    doc.setTextColor(255, 255, 255); doc.setFont('helvetica', 'bold'); doc.setFontSize(12);
    doc.text(`Desglose mensual por área · ${s.anio}`, 14, 10.5);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(91, 107, 128);
    doc.text('Monto cobrado en cada mes y porcentaje que representa cada área dentro del total del mes.', 14, 25);
    doc.autoTable({
        startY: 29, margin: { left: 14, right: 14 }, showFoot: 'lastPage', rowPageBreak: 'avoid',
        head: [['Mes', ...areas.map(nomArea), 'Total del mes']],
        body: meses.map(x => [MESES[x.mes - 1], ...areas.map(a => x.valores[a] ? `${fmt(x.valores[a])}\n${pct(x.valores[a] / x.total * 100)}` : '—'), fmt(x.total)]),
        foot: [['Total', ...areas.map(a => `${fmt(m.totales[a])}\n${pct(total ? m.totales[a] / total * 100 : 0)}`), fmt(total)]],
        styles: { fontSize: 9, halign: 'right', cellPadding: 2.4, textColor: [30, 41, 59], valign: 'middle' },
        headStyles: { fillColor: [21, 35, 59], textColor: 255, halign: 'right', fontStyle: 'bold' },
        footStyles: { fillColor: [232, 238, 247], textColor: [21, 35, 59], fontStyle: 'bold', halign: 'right' },
        alternateRowStyles: { fillColor: [247, 249, 252] },
        columnStyles: { 0: { halign: 'left', fontStyle: 'bold' } },
        didParseCell: d => {
            if (d.section === 'head' && d.column.index > 0 && d.column.index <= areas.length) d.cell.styles.fillColor = rgb(colorArea(areas[d.column.index - 1]));
            if (d.column.index === 0) d.cell.styles.halign = 'left';
        },
    });

    // Pie de página
    const paginas = doc.internal.getNumberOfPages();
    for (let i = 1; i <= paginas; i++) {
        doc.setPage(i); doc.setFontSize(8); doc.setTextColor(140);
        doc.text('APAI · Asociación de Padres y Alumnos del I.N.A.C. · Los porcentajes son sobre el total recaudado.', 14, H - 8);
        doc.text(`Página ${i} de ${paginas}`, W - 14, H - 8, { align: 'right' });
    }
    doc.save(`recaudacion_por_area_${s.anio}.pdf`);
}

// ---------------------------------------------------------------- pantalla
let statsFiltrosListos = false;
async function cargarStats() {
    try {
        const per = document.getElementById('st-periodo');
        if (!statsFiltrosListos) {
            per.innerHTML = '<option value="">Hoy (cuotas vencidas a la fecha)</option>' + MESES.map((m, i) => `<option value="${i + 1}">Al cierre de ${m.toLowerCase()}</option>`).join('');
            statsFiltrosListos = true;
        }
        const p = new URLSearchParams();
        const mes = per.value, area = document.getElementById('st-area').value, nivel = document.getElementById('st-nivel').value;
        if (mes) p.set('mes', mes);
        if (area) p.set('area', area);
        if (nivel) p.set('nivel', nivel);
        const s = await api('/api/cuotas/estadisticas?' + p);
        statsUltimo = s;
        const llenar = (id, lista, todos, nombre) => {
            const sel = document.getElementById(id), actual = sel.value;
            sel.innerHTML = `<option value="">${todos}</option>` + lista.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(nombre ? nombre(v) : v)}</option>`).join('');
            sel.value = lista.includes(actual) ? actual : '';
        };
        llenar('st-area', s.filtros.areas, 'Todas las áreas', nomArea);
        llenar('st-nivel', s.filtros.niveles, 'Todos los niveles');
        const k = s.indicadores;
        const corte = MESES[s.mes_corte - 1] ? MESES[s.mes_corte - 1].toLowerCase() : '';
        document.getElementById('st-explica').textContent =
            `A la fecha: se compara lo pagado con las cuotas vencidas hasta ${corte} (cada cuota vence el último día de su mes). ` +
            `Así el cumplimiento refleja lo que ya se tenía que pagar; en diciembre equivale al total anual.`;
        document.getElementById('stats-kpis').innerHTML = `
            <div class="gasto-kpi"><div class="gasto-kpi-label">Alumnos</div><div class="gasto-kpi-valor">${k.alumnos}</div><div class="gasto-kpi-sub">${k.becados} becados</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Cobrado a la fecha</div><div class="gasto-kpi-valor" style="color:var(--success)">${fmtMoneda(k.cobrado)}</div>
                <div class="gasto-kpi-sub">${s.mes ? 'en ' + MESES[s.mes - 1].toLowerCase() + ': ' + fmtMoneda(k.cobrado_mes) : 'de enero a hoy'}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Esperado a la fecha</div><div class="gasto-kpi-valor">${fmtMoneda(k.esperado)}</div><div class="gasto-kpi-sub">matrícula + cuotas vencidas hasta ${corte}</div></div>
            <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Deuda a la fecha</div><div class="gasto-kpi-valor">${fmtMoneda(k.deuda)}</div><div class="gasto-kpi-sub">cuotas vencidas sin pagar</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">% Cumplimiento</div><div class="gasto-kpi-valor">${pct(k.cumplimiento)}</div>
                <div class="st-progreso"><span style="width:${Math.min(100, k.cumplimiento)}%"></span></div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Deben el año anterior</div><div class="gasto-kpi-valor" style="color:var(--warning)">${k.con_deuda_anterior}</div><div class="gasto-kpi-sub">${fmtMoneda(k.deuda_anterior)} pendientes</div></div>`;
        const est = [['Al día', k.al_dia, 'ok', 'al día y sin deuda anterior', 'Al día'], ['Pagado', k.pagado, 'ok', 'año (o curso) completo pagado', 'Pagado'],
            [`Al día · debe ${s.anio - 1}`, k.al_dia_debe_anterior, 'aviso', 'al día con el año, pero debe el anterior', 'debe-anterior'],
            ['Moroso', k.moroso, 'mal', 'tiene cuotas vencidas', 'Moroso'], ['Sin pagos', k.sin_pagos, 'mal', 'no pagó nada este año', 'Sin pagos'],
            ['Becados', k.becados, 'neutro', 'becados (no pagan cuota)', 'Becado']];
        document.getElementById('stats-estados').innerHTML = est.map(([n, v, c, t, filtro]) =>
            `<button type="button" class="st-estado st-${c}" title="Ver la lista: ${escapeHtml(t)}" onclick="verAlumnosConEstado('${filtro}')">
                <b>${v}</b><span>${escapeHtml(n)}</span><small>${k.alumnos ? pct(v / k.alumnos * 100, 0) : '0%'} · ver lista →</small></button>`).join('');

        // Desglose mensual por área ($ y % del mes)
        const m = s.mensual;
        document.getElementById('st-mensual').innerHTML = `<div class="tabla-wrap"><table class="st-tabla"><thead><tr><th>Mes</th>
            ${m.areas.map(a => `<th class="num"><span class="st-punto" style="background:${colorArea(a)}"></span>${escapeHtml(nomArea(a))}</th><th class="num">%</th>`).join('')}<th class="num">Total del mes</th></tr></thead><tbody>
            ${m.meses.map(x => `<tr class="${s.mes === x.mes ? 'st-sel' : ''}"><td>${MESES[x.mes - 1]}</td>
                ${m.areas.map(a => `<td class="num">${fmtMoneda(x.valores[a])}</td><td class="num muted">${x.total ? pct(x.valores[a] / x.total * 100) : '—'}</td>`).join('')}
                <td class="num"><b>${fmtMoneda(x.total)}</b></td></tr>`).join('')}
            <tr class="st-total"><td>TOTAL</td>${m.areas.map(a => `<td class="num">${fmtMoneda(m.totales[a])}</td><td class="num">${m.total ? pct(m.totales[a] / m.total * 100) : '—'}</td>`).join('')}
                <td class="num">${fmtMoneda(m.total)}</td></tr></tbody></table></div>`;

        const tabla = (filas, titulo) => `<div class="tabla-wrap"><table class="st-tabla"><thead><tr><th>${titulo}</th><th>Área</th><th class="num">Alumnos</th>
            <th class="num">Becados</th><th class="num">Al día</th><th class="num">Pagado</th><th class="num" title="Al día con el año pero debe el anterior">Al día · debe ant.</th>
            <th class="num">Moroso</th><th class="num">Sin pagos</th><th class="num">Cobrado</th><th class="num">Esperado</th><th class="num">Deuda</th><th class="num">% Cumpl.</th></tr></thead><tbody>
            ${filas.map(d => `<tr><td><b>${escapeHtml(d.clave)}</b></td><td><span class="st-punto" style="background:${colorArea(d.area)}"></span>${escapeHtml(nomArea(d.area))}</td><td class="num">${d.alumnos}</td><td class="num">${d.becados}</td>
                <td class="num">${d.al_dia}</td><td class="num">${d.pagado || ''}</td><td class="num">${d.al_dia_debe_anterior || ''}</td><td class="num">${d.moroso}</td><td class="num">${d.sin_pagos}</td>
                <td class="num">${fmtMoneda(d.cobrado)}</td><td class="num">${fmtMoneda(d.esperado)}</td><td class="num">${fmtMoneda(d.deuda)}</td>
                <td class="num"><span class="st-pct" style="--p:${Math.min(100, d.cumplimiento)}%">${pct(d.cumplimiento)}</span></td></tr>`).join('')
                || '<tr><td colspan="13" class="muted" style="text-align:center">Sin datos con estos filtros</td></tr>'}
            </tbody></table></div>`;
        document.getElementById('st-cursos').innerHTML = tabla(s.por_curso, 'Curso');
        document.getElementById('st-grupos').innerHTML = tabla(s.por_grupo, 'Grupo');
        dibujarChartsCuotas(s);
    } catch (err) { toast(err.message, 'error'); }
}

// ---------------------------------------------------------------- gráficos
const _animEscalonada = (base = 70) => _reduceMotion ? false : {
    duration: 900, easing: 'easeOutQuart',
    delay: c => (c.type === 'data' && c.mode === 'default') ? c.dataIndex * base + c.datasetIndex * 60 : 0,
};

// Total arriba de cada columna apilada
const pluginTotales = (totales, destacado, tamFuente = 11) => ({
    id: 'totales',
    afterDatasetsDraw(ch) {
        const { ctx } = ch;
        ctx.save();
        ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
        ctx.font = `700 ${tamFuente}px Inter, system-ui, sans-serif`;
        const ultimo = ch.data.datasets.length - 1;
        ch.getDatasetMeta(ultimo).data.forEach((bar, i) => {
            if (!totales[i]) return;
            let tope = Infinity;
            ch.data.datasets.forEach((ds, di) => { if (ch.isDatasetVisible(di)) { const el = ch.getDatasetMeta(di).data[i]; if (el && ds.data[i]) tope = Math.min(tope, el.y); } });
            if (!isFinite(tope)) return;
            ctx.fillStyle = destacado && destacado !== i + 1 ? 'rgba(91,107,128,0.45)' : '#15233b';
            ctx.fillText(millones(totales[i]), bar.x, tope - 5);
        });
        ctx.restore();
    },
});

// Valor al final de cada barra horizontal
const pluginValorFinal = (formato, datasetIndex = 0) => ({
    id: 'valorFinal',
    afterDatasetsDraw(ch) {
        const { ctx } = ch;
        ctx.save(); ctx.textBaseline = 'middle'; ctx.font = '600 11px Inter, system-ui, sans-serif'; ctx.fillStyle = '#334155';
        const metas = ch.data.datasets.map((d, i) => ch.getDatasetMeta(i));
        metas[datasetIndex].data.forEach((bar, i) => {
            const fin = Math.max(...metas.filter((mm, mi) => ch.isDatasetVisible(mi) && !ch.data.datasets[mi].esFondo).map(mm => mm.data[i] ? mm.data[i].x : 0));
            const texto = formato(i);
            if (texto) ctx.fillText(texto, Math.min(fin + 6, ch.chartArea.right - ctx.measureText(texto).width - 2), bar.y);
        });
        ctx.restore();
    },
});

function _configMensual(meses, areas, destacado, paraPdf = false) {
    const totales = meses.map(x => x.total);
    const topeDe = (ctx) => {  // la columna lleva las puntas redondeadas solo arriba
        const i = ctx.dataIndex, ds = ctx.chart.data.datasets;
        for (let d = ds.length - 1; d >= 0; d--) if (ctx.chart.isDatasetVisible(d) && ds[d].data[i]) return d === ctx.datasetIndex;
        return false;
    };
    return {
        type: 'bar',
        data: {
            labels: meses.map(x => MESES[x.mes - 1].slice(0, 3)),
            datasets: areas.map(a => ({
                label: nomArea(a), data: meses.map(x => x.valores[a]), stack: 'cobranza',
                backgroundColor: meses.map(x => (!destacado || destacado === x.mes) ? colorArea(a) : hexA(colorArea(a), 0.22)),
                hoverBackgroundColor: colorArea(a),
                borderRadius: c => topeDe(c) ? { topLeft: 7, topRight: 7 } : 0, borderSkipped: false,
                borderColor: 'rgba(255,255,255,0.9)', borderWidth: { top: 1.2 },
                categoryPercentage: 0.72, barPercentage: 0.92, maxBarThickness: 54,
            })),
        },
        options: {
            maintainAspectRatio: false, animation: paraPdf ? false : _animEscalonada(),
            layout: { padding: { top: paraPdf ? 40 : 22 } },
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { font: { size: paraPdf ? 20 : 12, weight: '600' }, color: '#5b6b80' } },
                y: { stacked: true, beginAtZero: true, border: { display: false }, grid: { color: 'rgba(91,107,128,0.14)', borderDash: [4, 4], drawTicks: false },
                     ticks: { callback: millones, padding: 8, font: { size: paraPdf ? 18 : 11 }, color: '#5b6b80', maxTicksLimit: 6 } },
            },
            plugins: {
                legend: { position: 'top', align: 'end', labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: paraPdf ? 18 : 10, padding: paraPdf ? 26 : 16, font: { size: paraPdf ? 20 : 12, weight: '600' }, color: '#334155' } },
                tooltip: {
                    backgroundColor: 'rgba(15,23,42,0.94)', padding: 12, cornerRadius: 10, boxPadding: 5, usePointStyle: true,
                    itemSort: (a, b) => b.raw - a.raw, filter: it => it.raw > 0,
                    callbacks: {
                        title: it => MESES[meses[it[0].dataIndex].mes - 1],
                        label: c => ` ${c.dataset.label}: ${fmtMoneda(c.raw)} (${pct(totales[c.dataIndex] ? c.raw / totales[c.dataIndex] * 100 : 0)})`,
                        footer: it => 'Total del mes: ' + fmtMoneda(totales[it[0].dataIndex]),
                    },
                },
            },
        },
        plugins: [pluginTotales(totales, destacado, paraPdf ? 22 : 11)],
    };
}

function dibujarChartsCuotas(s) {
    if (typeof Chart === 'undefined') return;
    [chartCuotasMensual, chartCuotasArea, chartCuotasCvd].forEach(c => c && c.destroy());
    const m = s.mensual;
    const cfg = _configMensual(m.meses, m.areas, s.mes);
    cfg.options.onClick = (e, el) => { if (el.length) { document.getElementById('st-periodo').value = String(el[0].index + 1); cargarStats(); } };
    cfg.options.onHover = (e, el) => { e.native.target.style.cursor = el.length ? 'pointer' : 'default'; };
    chartCuotasMensual = new Chart(document.getElementById('chart-cuotas-mensual'), cfg);

    const grupos = s.por_grupo;
    const alto = Math.max(240, grupos.length * 30 + 50);
    document.getElementById('st-wrap-cumpl').style.height = alto + 'px';
    document.getElementById('st-wrap-cvd').style.height = alto + 'px';
    const corto = g => { const m2 = g.clave.match(/^Todos los (\S+) — (.+)$/); return m2 ? `${m2[1]} ${nomArea(m2[2])}` : g.clave.split(' — ')[0]; };
    const ejeY = { grid: { display: false }, border: { display: false }, ticks: { font: { size: 11, weight: '600' }, color: '#334155', padding: 6 } };

    // % de cumplimiento: barra de progreso sobre un fondo al 100%
    chartCuotasArea = new Chart(document.getElementById('chart-cuotas-area'), {
        type: 'bar',
        data: { labels: grupos.map(corto), datasets: [
            { label: '% Cumplimiento', data: grupos.map(g => g.cumplimiento), backgroundColor: grupos.map(g => colorArea(g.area)),
              hoverBackgroundColor: grupos.map(g => colorArea(g.area)), borderRadius: 999, borderSkipped: false, barThickness: 14, grouped: false, order: 1 },
            { label: 'fondo', esFondo: true, data: grupos.map(() => 100), backgroundColor: 'rgba(148,163,184,0.16)', borderRadius: 999,
              borderSkipped: false, barThickness: 14, grouped: false, order: 2 }] },
        options: { indexAxis: 'y', maintainAspectRatio: false, animation: _animEscalonada(45), layout: { padding: { right: 48 } },
                   plugins: { legend: { display: false }, tooltip: { filter: it => !it.dataset.esFondo, backgroundColor: 'rgba(15,23,42,0.94)', padding: 10, cornerRadius: 10,
                       callbacks: { label: c => ` Cumplimiento: ${pct(c.raw)} · ${fmtMoneda(grupos[c.dataIndex].deuda)} de deuda` } } },
                   scales: { x: { max: 100, border: { display: false }, grid: { color: 'rgba(91,107,128,0.12)', borderDash: [4, 4] }, ticks: { callback: v => v + '%', color: '#5b6b80' } }, y: ejeY } },
        plugins: [pluginValorFinal(i => pct(grupos[i].cumplimiento, 0))],
    });

    // Cobrado vs. deuda: barra apilada con las puntas redondeadas por fuera
    const radio = (lado) => c => {
        const g = grupos[c.dataIndex], otro = lado === 'izq' ? g.deuda : g.cobrado;
        if (!otro) return 999;
        return lado === 'izq' ? { topLeft: 999, bottomLeft: 999 } : { topRight: 999, bottomRight: 999 };
    };
    chartCuotasCvd = new Chart(document.getElementById('chart-cuotas-cvd'), {
        type: 'bar',
        data: { labels: grupos.map(corto), datasets: [
            { label: 'Cobrado', data: grupos.map(g => g.cobrado), backgroundColor: '#16a34a', hoverBackgroundColor: '#15803d', borderRadius: radio('izq'), borderSkipped: false, barThickness: 14 },
            { label: 'Deuda a la fecha', data: grupos.map(g => g.deuda), backgroundColor: '#ef4444', hoverBackgroundColor: '#dc2626', borderRadius: radio('der'), borderSkipped: false, barThickness: 14 }] },
        options: { indexAxis: 'y', maintainAspectRatio: false, animation: _animEscalonada(45), layout: { padding: { right: 56 } },
                   interaction: { mode: 'index', intersect: false },
                   scales: { x: { stacked: true, border: { display: false }, grid: { color: 'rgba(91,107,128,0.12)', borderDash: [4, 4] }, ticks: { callback: millones, color: '#5b6b80', maxTicksLimit: 6 } },
                             y: { ...ejeY, stacked: true } },
                   plugins: { legend: { position: 'top', align: 'end', labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10, font: { weight: '600' } } },
                       tooltip: { backgroundColor: 'rgba(15,23,42,0.94)', padding: 10, cornerRadius: 10, usePointStyle: true,
                           callbacks: { label: c => ` ${c.dataset.label}: ${fmtMoneda(c.raw)}` } } } },
        plugins: [pluginValorFinal(i => pct(grupos[i].cumplimiento, 0), 1)],  // mismo % que el gráfico de cumplimiento
    });
}

// ---- Pagos SIRO ----

// ---- Pagos SIRO ----
let pagosSiroCache = [];
let siroFiltrosListos = false;

function siroLlenarFiltros() {
    if (siroFiltrosListos) return;
    const fmes = document.getElementById('siro-f-mes');
    fmes.innerHTML = '<option value="">Todos los meses</option>' +
        MESES.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('');
    const hoy = new Date().getFullYear();
    const fanio = document.getElementById('siro-f-anio');
    fanio.innerHTML = '<option value="">Todos los años</option>' +
        [0, 1, 2, 3].map(d => `<option value="${hoy - d}">${hoy - d}</option>`).join('');
    fanio.value = String(hoy);
    siroFiltrosListos = true;
}

async function cargarPagosSiro() {
    try {
        siroLlenarFiltros();
        const estado = document.getElementById('siro-f-estado').value;
        const mes = document.getElementById('siro-f-mes').value;
        const anio = document.getElementById('siro-f-anio').value;
        const p = new URLSearchParams();
        if (estado) p.set('estado', estado);
        if (mes) p.set('mes', mes);
        if (anio) p.set('anio', anio);
        pagosSiroCache = await api('/api/cuotas/?' + p.toString());
        filtrarSiro();
        cargarResumenSiro(mes, anio);
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function cargarResumenSiro(mes, anio) {
    try {
        const p = new URLSearchParams();
        if (mes) p.set('mes', mes);
        if (anio) p.set('anio', anio);
        const r = await api('/api/cuotas/resumen?' + p.toString());
        document.getElementById('siro-resumen').innerHTML = `
            <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Pagos importados</div>
                <div class="gasto-kpi-valor">${r.total}</div>
                <div class="gasto-kpi-sub">${fmtMoneda(r.monto_total)}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Asignados</div>
                <div class="gasto-kpi-valor" style="color:var(--green)">${r.asignados}</div>
                <div class="gasto-kpi-sub">a un alumno</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Sin asignar</div>
                <div class="gasto-kpi-valor" style="color:var(--warning)">${r.sin_asignar}</div>
                <div class="gasto-kpi-sub">${fmtMoneda(r.monto_sin_asignar)}</div></div>`;
    } catch (e) { /* sin datos */ }
}

let siroSort = { campo: 'fecha', asc: false };
function sortSiro(campo) {
    siroSort.asc = siroSort.campo === campo ? !siroSort.asc : true;
    siroSort.campo = campo;
    filtrarSiro();
}

function filtrarSiro() {
    const q = normTxt(document.getElementById('buscar-siro').value);
    let lista = pagosSiroCache.filter(p => !q || normTxt(
        `${p.cliente_siro} ${p.alumno ? p.alumno.apellido + ' ' + p.alumno.nombre : ''}`).includes(q));
    lista = ordenarLista(lista, siroSort, new Set(['importe']),
        { alumno: o => o.alumno ? o.alumno.apellido : 'zzz', curso: o => o.alumno ? o.alumno.curso : '' });
    renderSiro(lista);
}

function renderSiro(lista) {
    document.getElementById('body-siro').innerHTML = lista.map(p => {
        const f = p.fecha ? p.fecha.split('-').reverse().join('/') : '-';
        let alumno, acciones;
        if (p.alumno) {
            const via = p.via ? ` <span style="color:var(--text-muted);font-size:.78rem">(${p.via})</span>` : '';
            alumno = `${escapeHtml(p.alumno.apellido)}, ${escapeHtml(p.alumno.nombre)}${via}`;
            acciones = '';
        } else {
            alumno = '<span class="conc-pend">● sin asignar</span>';
            acciones = `<button class="btn btn-sm btn-primary" onclick="asignarPagoSiro(${p.id})">Asignar</button>`;
        }
        return `<tr>
            <td>${f}</td>
            <td>${escapeHtml(p.cliente_siro || '-')}</td>
            <td>${alumno}</td>
            <td>${p.alumno ? escapeHtml(p.alumno.curso || '-') : '-'}</td>
            <td>${escapeHtml(p.canal || '-')}</td>
            <td style="text-align:right">${fmtMoneda(p.importe)}</td>
            <td>${acciones}</td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No hay pagos. Subí un listado de cobranzas SIRO.</td></tr>';
}

async function importarSiro(input) {
    const file = input.files[0];
    if (!file) return;
    toast('Procesando cobranzas...', 'success');
    try {
        const fd = new FormData();
        fd.append('archivo', file);
        const res = await fetch(API + '/api/cuotas/importar', { method: 'POST', credentials: 'same-origin', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Error al importar');
        toast(`Listo: ${data.nuevos} pagos nuevos, ${data.asignados} asignados, ${data.sin_asignar} sin asignar` +
            (data.duplicados ? ` (${data.duplicados} ya estaban)` : ''), 'success');
        cargarPagosSiro();
    } catch (err) {
        toast(err.message, 'error');
    } finally {
        input.value = '';
    }
}

async function reasignarSiro() {
    try {
        const r = await api('/api/cuotas/reasignar', { method: 'POST' });
        toast(`Se asignaron ${r.asignados} más. Quedan ${r.sin_asignar} sin asignar.`);
        cargarPagosSiro();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function asignarPagoSiro(pagoId) {
    const leg = prompt('Legajo del alumno al que asignar este pago:');
    if (!leg) return;
    try {
        if (!alumnosCache.length) await cargarAlumnos();
        const a = alumnosCache.find(x => String(x.legajo) === String(leg).trim());
        if (!a) { toast('No encontré un alumno con ese legajo', 'error'); return; }
        await api(`/api/cuotas/${pagoId}/asignar/${a.id}`, { method: 'POST' });
        toast(`Asignado a ${a.apellido}, ${a.nombre}`);
        cargarPagosSiro();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =========================================================
// --- CURSOS Y PARAMETROS ---
// =========================================================
let cursosCache = [];

async function cargarCursos() {
    try {
        cursosCache = await api('/api/cursos/');
        // Si no hay ninguno, ofrecer cargar la config inicial
        if (!cursosCache.length) {
            if (confirm('No hay cursos cargados. ¿Cargar la configuración inicial (Ciclo Básico, ORR, TCP, DESP AER, etc.)?')) {
                await api('/api/cursos/seed', { method: 'POST' });
                cursosCache = await api('/api/cursos/');
            }
        }
        renderCursos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

function renderCursos() {
    document.getElementById('body-cursos').innerHTML = cursosCache.map(c => `
        <tr>
            <td><b>${escapeHtml(c.nombre)}</b>${c.patron ? ` <span style="color:var(--text-muted);font-size:.8rem">(${escapeHtml(c.patron)})</span>` : ''}</td>
            <td>${escapeHtml(c.area || '-')}</td>
            <td>${escapeHtml(c.divisiones || '-')}</td>
            <td style="text-align:right">${fmtMoneda(c.cuota)}</td>
            <td style="text-align:right">${c.n_cuotas}</td>
            <td style="text-align:right">${Number(c.matricula) ? '$' + gastoFmt(c.matricula) : '—'}</td>
            <td>${c.cobra_cuotas_viejas ? 'Sí' : 'No'}</td>
            <td>
                <button class="btn btn-sm" onclick="editarCurso(${c.id})">Editar</button>
                <button class="btn btn-sm btn-danger btn-ico" onclick="eliminarCurso(${c.id})" title="Eliminar" aria-label="Eliminar"><svg class="ic"><use href="#i-trash"/></svg></button>
            </td>
        </tr>`).join('') ||
        '<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">Sin cursos cargados</td></tr>';
}

function mostrarFormCurso() {
    document.getElementById('form-curso').style.display = 'block';
    document.getElementById('form-curso-titulo').textContent = 'Nuevo curso';
    document.getElementById('cur-edit-id').value = '';
    ['cur-nombre', 'cur-area', 'cur-divisiones', 'cur-patron', 'cur-cuota',
        'cur-ncuotas', 'cur-matricula', 'cur-cuota-ant'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('cur-anio').value = '2026';
    document.getElementById('cur-viejas').checked = false;
    document.getElementById('form-curso').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cerrarFormCurso() {
    document.getElementById('form-curso').style.display = 'none';
}

function editarCurso(id) {
    const c = cursosCache.find(x => x.id === id);
    if (!c) return;
    document.getElementById('form-curso').style.display = 'block';
    document.getElementById('form-curso-titulo').textContent = 'Editar curso';
    document.getElementById('cur-edit-id').value = id;
    document.getElementById('cur-nombre').value = c.nombre || '';
    document.getElementById('cur-area').value = c.area || '';
    document.getElementById('cur-divisiones').value = c.divisiones || '';
    document.getElementById('cur-patron').value = c.patron || '';
    document.getElementById('cur-cuota').value = c.cuota;
    document.getElementById('cur-ncuotas').value = c.n_cuotas;
    document.getElementById('cur-matricula').value = c.matricula;
    document.getElementById('cur-cuota-ant').value = c.cuota_anio_anterior;
    document.getElementById('cur-anio').value = c.anio;
    document.getElementById('cur-viejas').checked = !!c.cobra_cuotas_viejas;
    document.getElementById('form-curso').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function guardarCurso(e) {
    e.preventDefault();
    const editId = document.getElementById('cur-edit-id').value;
    const body = {
        nombre: document.getElementById('cur-nombre').value,
        area: document.getElementById('cur-area').value || null,
        divisiones: document.getElementById('cur-divisiones').value || null,
        patron: document.getElementById('cur-patron').value || null,
        cuota: parseFloat(document.getElementById('cur-cuota').value) || 0,
        n_cuotas: parseInt(document.getElementById('cur-ncuotas').value) || 0,
        matricula: parseFloat(document.getElementById('cur-matricula').value) || 0,
        cuota_anio_anterior: parseFloat(document.getElementById('cur-cuota-ant').value) || 0,
        anio: parseInt(document.getElementById('cur-anio').value) || 2026,
        cobra_cuotas_viejas: document.getElementById('cur-viejas').checked,
    };
    try {
        if (editId) {
            await api(`/api/cursos/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
            toast('Curso actualizado');
        } else {
            await api('/api/cursos/', { method: 'POST', body: JSON.stringify(body) });
            toast('Curso creado');
        }
        cerrarFormCurso();
        cargarCursos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function eliminarCurso(id) {
    const c = cursosCache.find(x => x.id === id);
    if (!confirm(`¿Eliminar el curso "${c ? c.nombre : ''}"?`)) return;
    try {
        const res = await api(`/api/cursos/${id}`, { method: 'DELETE' });
        toast(res.mensaje);
        cargarCursos();
    } catch (err) {
        toast(err.message, 'error');
    }
}

// =========================================================
// --- CONTROL HORARIO (fichada) ---
// =========================================================
let horMeta = null, empleadosCache = [], horRegistros = [], horResumen = null;

async function cargarHorario() {
    try {
        if (!horMeta) horMeta = await api('/api/horario/meta');
        empleadosCache = await api('/api/horario/empleados');
        if (!empleadosCache.length) {
            await api('/api/horario/empleados', { method: 'POST', body: JSON.stringify({ nombre: 'Administración', puesto: 'Empleada administrativa', horas_diarias: 8 }) });
            empleadosCache = await api('/api/horario/empleados');
        }
        const selE = document.getElementById('hor-empleado');
        selE.innerHTML = empleadosCache.map(e => `<option value="${e.id}">${escapeHtml(e.nombre)}</option>`).join('');
        // mes / anio
        const fmes = document.getElementById('hor-mes');
        fmes.innerHTML = horMeta.meses.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('');
        fmes.value = String(new Date().getMonth() + 1);
        const hoy = new Date().getFullYear();
        const fanio = document.getElementById('hor-anio');
        fanio.innerHTML = [0, 1, 2].map(d => `<option value="${hoy - d}">${hoy - d}</option>`).join('');
        // tipos para el form
        gastoOpts('dia-tipo', horMeta.tipos_dia, '');
        cargarHorarioMes();
    } catch (err) { toast(err.message, 'error'); }
}

function horEmpleadoActual() { return Number(document.getElementById('hor-empleado').value); }

async function cargarHorarioMes() {
    const emp = horEmpleadoActual();
    const mes = document.getElementById('hor-mes').value;
    const anio = document.getElementById('hor-anio').value;
    if (!emp) return;
    try {
        const r = await api(`/api/horario/registros?empleado_id=${emp}&anio=${anio}&mes=${mes}`);
        horRegistros = r.registros;
        renderResumenHor(r.resumen, emp, mes, anio);
        renderHorarioDias(r.registros);
        cargarHorarioAnual(emp, anio);
    } catch (err) { toast(err.message, 'error'); }
}

function renderResumenHor(s, emp, mes, anio) {
    horResumen = s;
    document.getElementById('hor-resumen').innerHTML = `
        <div class="gasto-kpi"><div class="gasto-kpi-label">Días trabajados</div><div class="gasto-kpi-valor">${s.dias_trabajados}</div><div class="gasto-kpi-sub">${s.dias_vacaciones} vacac.</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Hs trabajadas</div><div class="gasto-kpi-valor">${s.hs_trabajadas}</div><div class="gasto-kpi-sub">de ${s.hs_esperadas} esperadas</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Hs extras del mes</div><div class="gasto-kpi-valor" style="color:var(--green)">${s.hs_extras}</div><div class="gasto-kpi-sub">+ ${s.saldo_anterior} del mes anterior</div></div>
        <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Acumulado a liquidar</div><div class="gasto-kpi-valor">${s.acumulado_a_liquidar}</div><div class="gasto-kpi-sub">${s.saldo_anterior} ant. + ${s.hs_extras} del mes</div></div>
        <div class="gasto-kpi" style="cursor:pointer" onclick="editarLiquidadas(${emp},${anio},${mes},${s.hs_liquidadas})"><div class="gasto-kpi-label">Hs liquidadas ✎</div><div class="gasto-kpi-valor">${s.hs_liquidadas}</div><div class="gasto-kpi-sub">queda pend.: ${s.pendiente_cierre}</div></div>`;
}

function renderHorarioDias(regs) {
    const dias = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
    document.getElementById('body-horario').innerHTML = regs.map(r => {
        const f = r.fecha ? r.fecha.split('-').reverse().join('/') : '-';
        const dl = new Date(r.fecha + 'T12:00:00').getDay();
        const tipoBadge = r.tipo === 'Normal' ? '' : ` <span class="tag-nc" style="background:var(--steel)">${escapeHtml(r.tipo)}</span>`;
        return `<tr>
            <td>${f}</td><td>${dias[dl]}</td>
            <td>${r.tipo === 'Normal' ? 'Normal' : escapeHtml(r.tipo)}</td>
            <td>${r.entrada || '-'}</td><td>${r.salida || '-'}</td>
            <td style="text-align:right">${r.hs_trabajadas || ''}</td>
            <td style="text-align:right;${r.hs_extras > 0 ? 'color:var(--green);font-weight:700' : ''}">${r.hs_extras || ''}</td>
            <td>
                <button class="btn btn-sm" onclick="editarDia(${r.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="eliminarDia(${r.id})">✕</button>
            </td>
        </tr>`;
    }).join('') ||
        '<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">Sin fichadas este mes. Usá "+ Registrar día".</td></tr>';
}

async function cargarHorarioAnual(emp, anio) {
    try {
        const r = await api(`/api/horario/anual?empleado_id=${emp}&anio=${anio}`);
        document.getElementById('hor-anual-emp').textContent = `· ${r.empleado} · ${r.anio}`;
        document.getElementById('body-horario-anual').innerHTML = r.meses.map(m => `
            <tr${(m.hs_trabajadas || m.dias_vacaciones) ? '' : ' style="opacity:.5"'}>
                <td>${m.mes_nombre}</td>
                <td style="text-align:right">${m.dias_trabajados}</td>
                <td style="text-align:right">${m.hs_trabajadas}</td>
                <td style="text-align:right">${m.hs_esperadas}</td>
                <td style="text-align:right;${m.hs_extras > 0 ? 'color:var(--green)' : ''}">${m.hs_extras}</td>
                <td style="text-align:right">${m.dias_vacaciones}</td>
                <td style="text-align:right">${m.hs_liquidadas}</td>
                <td style="text-align:right;font-weight:700">${m.pend_acumuladas}</td>
            </tr>`).join('') +
            `<tr style="font-weight:700;border-top:2px solid var(--border)">
                <td>TOTAL</td><td style="text-align:right">${r.totales.dias}</td>
                <td style="text-align:right">${r.totales.trab.toFixed(1)}</td>
                <td style="text-align:right">${r.totales.esperadas.toFixed(1)}</td>
                <td style="text-align:right">${r.totales.extras.toFixed(1)}</td>
                <td style="text-align:right">${r.totales.vac}</td>
                <td style="text-align:right">${r.totales.liq.toFixed(1)}</td><td></td></tr>`;
    } catch (err) { /* */ }
}

function exportarHorarioPDF() {
    if (typeof window.jspdf === 'undefined') { toast('No se pudo cargar el generador de PDF', 'error'); return; }
    if (!horRegistros.length) { toast('No hay registros en este mes', 'error'); return; }
    const dias = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
    const selE = document.getElementById('hor-empleado');
    const nombreEmp = selE.options[selE.selectedIndex] ? selE.options[selE.selectedIndex].text : '';
    const mes = Number(document.getElementById('hor-mes').value);
    const anio = document.getElementById('hor-anio').value;
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    const f1 = n => Number(n || 0).toFixed(1);

    doc.setFontSize(14); doc.text('Control horario — Registro mensual', 14, 16);
    doc.setFontSize(10); doc.setTextColor(90);
    doc.text(`${nombreEmp}  ·  ${MESES[mes - 1]} ${anio}`, 14, 22);
    doc.setTextColor(20);

    let acum = 0, totTrab = 0, totExtra = 0;
    const body = horRegistros.map(r => {
        const dl = new Date(r.fecha + 'T12:00:00').getDay();
        const trab = Number(r.hs_trabajadas || 0), extra = Number(r.hs_extras || 0);
        acum += extra; totTrab += trab; totExtra += extra;
        const esNormal = r.tipo === 'Normal';
        return [
            r.fecha.split('-').reverse().join('/'),
            dias[dl],
            esNormal ? '' : r.tipo,
            r.entrada || '', r.salida || '',
            esNormal ? f1(trab) : '', esNormal ? f1(extra) : '',
            esNormal ? f1(acum) : '',
        ];
    });

    doc.autoTable({
        startY: 27,
        head: [['Fecha', 'Día', 'Tipo', 'Entrada', 'Salida', 'Hs trab.', 'Hs extras', 'Extras acum.']],
        body: body,
        styles: { fontSize: 8.5, halign: 'center' },
        headStyles: { fillColor: [13, 148, 136] },
        columnStyles: { 0: { halign: 'left' }, 1: { halign: 'left' }, 2: { halign: 'left' } },
        foot: [[
            { content: 'TOTALES', colSpan: 5, styles: { halign: 'right' } },
            f1(totTrab), f1(totExtra), '',
        ]],
        footStyles: { fillColor: [21, 35, 59], textColor: 255 },
    });

    let y = doc.lastAutoTable.finalY + 8;
    if (horResumen) {
        doc.setFontSize(10);
        doc.text(`Saldo extras del mes anterior: ${f1(horResumen.saldo_anterior)} hs`, 14, y);
        doc.text(`Acumulado a liquidar (anterior + mes): ${f1(horResumen.acumulado_a_liquidar)} hs`, 14, y + 6);
        doc.text(`Horas liquidadas este mes: ${f1(horResumen.hs_liquidadas)} hs   ·   Pendiente al cierre: ${f1(horResumen.pendiente_cierre)} hs`, 14, y + 12);
    }
    doc.save(`horario_${nombreEmp}_${MESES[mes - 1]}_${anio}.pdf`.replace(/\s+/g, '_'));
}

function diaToggleHoras() {
    const normal = document.getElementById('dia-tipo').value === 'Normal';
    document.getElementById('dia-entrada').disabled = !normal;
    document.getElementById('dia-salida').disabled = !normal;
}

function mostrarFormDia() {
    document.getElementById('form-dia').style.display = 'block';
    document.getElementById('form-dia-titulo').textContent = 'Registrar día';
    document.getElementById('dia-edit-id').value = '';
    document.getElementById('dia-fecha').value = hoyISO();
    document.getElementById('dia-tipo').value = 'Normal';
    ['dia-entrada', 'dia-salida', 'dia-notas'].forEach(id => document.getElementById(id).value = '');
    diaToggleHoras();
    document.getElementById('form-dia').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function cerrarFormDia() { document.getElementById('form-dia').style.display = 'none'; }

function editarDia(id) {
    const r = horRegistros.find(x => x.id === id);
    if (!r) return;
    document.getElementById('form-dia').style.display = 'block';
    document.getElementById('form-dia-titulo').textContent = 'Editar día';
    document.getElementById('dia-edit-id').value = id;
    document.getElementById('dia-fecha').value = r.fecha;
    document.getElementById('dia-tipo').value = r.tipo;
    document.getElementById('dia-entrada').value = r.entrada || '';
    document.getElementById('dia-salida').value = r.salida || '';
    document.getElementById('dia-notas').value = r.notas || '';
    diaToggleHoras();
    document.getElementById('form-dia').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function guardarDia(e) {
    e.preventDefault();
    const editId = document.getElementById('dia-edit-id').value;
    const tipo = document.getElementById('dia-tipo').value;
    const body = {
        empleado_id: horEmpleadoActual(),
        fecha: document.getElementById('dia-fecha').value,
        tipo: tipo,
        entrada: tipo === 'Normal' ? (document.getElementById('dia-entrada').value || null) : null,
        salida: tipo === 'Normal' ? (document.getElementById('dia-salida').value || null) : null,
        notas: document.getElementById('dia-notas').value || null,
    };
    try {
        if (editId) await api(`/api/horario/registros/${editId}`, { method: 'PUT', body: JSON.stringify(body) });
        else await api('/api/horario/registros', { method: 'POST', body: JSON.stringify(body) });
        toast('Día registrado');
        cerrarFormDia();
        cargarHorarioMes();
    } catch (err) { toast(err.message, 'error'); }
}

async function eliminarDia(id) {
    if (!confirm('¿Eliminar este día?')) return;
    try { await api(`/api/horario/registros/${id}`, { method: 'DELETE' }); cargarHorarioMes(); }
    catch (err) { toast(err.message, 'error'); }
}

async function editarLiquidadas(emp, anio, mes, actual) {
    const v = prompt('Horas extras liquidadas (pagadas) este mes:', actual);
    if (v === null) return;
    const h = parseFloat(v);
    if (isNaN(h)) { toast('Valor inválido', 'error'); return; }
    try {
        await api(`/api/horario/liquidacion?empleado_id=${emp}&anio=${anio}&mes=${mes}&horas=${h}`, { method: 'PUT' });
        toast('Horas liquidadas actualizadas');
        cargarHorarioMes();
    } catch (err) { toast(err.message, 'error'); }
}

async function abrirEmpleados() {
    empleadosCache = await api('/api/horario/empleados');
    const filas = empleadosCache.map(e => `
        <tr><td>${escapeHtml(e.nombre)}</td><td>${escapeHtml(e.puesto || '-')}</td>
        <td style="text-align:right">${e.horas_diarias} hs/día</td>
        <td><button class="btn btn-sm" onclick="editarEmpleado(${e.id})">Editar</button>
        <button class="btn btn-sm btn-danger" onclick="eliminarEmpleado(${e.id})">✕</button></td></tr>`).join('');
    const html = `
        <h2 style="margin-top:0">Empleados</h2>
        <table><thead><tr><th>Nombre</th><th>Puesto</th><th style="text-align:right">Jornada</th><th></th></tr></thead><tbody>${filas}</tbody></table>
        <h3 style="margin:1rem 0 .5rem">Agregar / editar</h3>
        <input type="hidden" id="emp-edit-id">
        <div class="form-grid">
            <div><label>Nombre</label><input type="text" id="emp-nombre"></div>
            <div><label>Puesto</label><input type="text" id="emp-puesto"></div>
            <div><label>Horas por día</label><input type="number" step="0.5" id="emp-horas" value="8"></div>
        </div>
        <div style="margin-top:1rem;display:flex;gap:.5rem;justify-content:flex-end">
            <button class="btn btn-primary" onclick="guardarEmpleado()">Guardar</button>
            <button class="btn" onclick="cerrarModal()">Cerrar</button>
        </div>`;
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').style.display = 'flex';
}

function editarEmpleado(id) {
    const e = empleadosCache.find(x => x.id === id);
    if (!e) return;
    document.getElementById('emp-edit-id').value = id;
    document.getElementById('emp-nombre').value = e.nombre;
    document.getElementById('emp-puesto').value = e.puesto || '';
    document.getElementById('emp-horas').value = e.horas_diarias;
}

async function guardarEmpleado() {
    const id = document.getElementById('emp-edit-id').value;
    const body = {
        nombre: document.getElementById('emp-nombre').value,
        puesto: document.getElementById('emp-puesto').value || null,
        horas_diarias: parseFloat(document.getElementById('emp-horas').value) || 8,
    };
    if (!body.nombre) { toast('Poné un nombre', 'error'); return; }
    try {
        if (id) await api(`/api/horario/empleados/${id}`, { method: 'PUT', body: JSON.stringify(body) });
        else await api('/api/horario/empleados', { method: 'POST', body: JSON.stringify(body) });
        toast('Empleado guardado');
        await abrirEmpleados();
        cargarHorario();
    } catch (err) { toast(err.message, 'error'); }
}

async function eliminarEmpleado(id) {
    if (!confirm('¿Eliminar este empleado y todos sus registros?')) return;
    try { await api(`/api/horario/empleados/${id}`, { method: 'DELETE' }); await abrirEmpleados(); cargarHorario(); }
    catch (err) { toast(err.message, 'error'); }
}

// --- TEMA CLARO / OSCURO ---
function aplicarTema(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('tema', t); } catch (e) {}
    const b = document.getElementById('btn-tema');
    if (b) {
        b.innerHTML = `<svg class="ic"><use href="#i-${t === 'dark' ? 'sun' : 'moon'}"/></svg>`;
        b.title = t === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = t === 'dark' ? '#0b1220' : '#15233b';
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

// =========================================================
// --- USUARIOS Y SEGURIDAD (solo administradores) ---
// =========================================================
let usuariosCache = [];

const ACCIONES_AUDITORIA = {
    ingreso: 'Ingreso', ingreso_fallido: 'Ingreso fallido', cuenta_bloqueada: 'Cuenta bloqueada',
    cambio_password: 'Cambió su contraseña', reset_password: 'Contraseña restablecida por link',
    pedido_reset: 'Pidió recuperar contraseña', '2fa_activado': '2FA activado', '2fa_desactivado': '2FA desactivado',
    '2fa_reiniciado': '2FA reiniciado por admin', '2fa_codigos_regenerados': 'Nuevos códigos de respaldo',
    codigo_respaldo_usado: 'Ingresó con código de respaldo', usuario_creado: 'Usuario creado',
    usuario_editado: 'Usuario modificado', clave_temporal: 'Clave temporal asignada',
    link_reset_enviado: 'Link de clave enviado', usuario_desbloqueado: 'Usuario desbloqueado',
    sesiones_cerradas: 'Sesiones cerradas por admin', cerrar_sesiones: 'Cerró sesión en todos lados',
    actualizar_cuenta: 'Actualizó sus datos', limpieza_finanzas: 'Dejó finanzas en cero', importacion_facturas: 'Importó facturas desde planilla',
    consulta_respondida: 'Respondió una consulta', consulta_estado: 'Cambió el estado de una consulta', reporte_problema: 'Reportó un problema',
    portal_ingreso: 'Portal: ingreso de familia', portal_cuenta_creada: 'Portal: cuenta de familia creada', portal_cuenta_bloqueada: 'Portal: cuenta bloqueada',
    portal_cambio_password: 'Portal: cambio de contraseña', portal_reset_password: 'Portal: contraseña restablecida',
    portal_pedido_reset: 'Portal: pidió recuperar contraseña', portal_consulta: 'Portal: nueva consulta',
    portal_vista_admin: 'Vio el portal como familia',
};

async function cargarUsuarios() {
    renderConfigSistema();
    try {
        const [lista, audit] = await Promise.all([api('/api/usuarios/'), api('/api/usuarios/auditoria')]);
        usuariosCache = lista;
        const yo = usuarioActual.username;
        document.getElementById('body-usuarios').innerHTML = lista.map(u => `
            <tr class="${u.activo ? '' : 'fila-inactiva'}">
                <td><b>${escapeHtml(u.nombre)}</b>${u.username === yo ? ' <span class="badge">vos</span>' : ''}</td>
                <td>${escapeHtml(u.username)}<br><small class="muted">${escapeHtml(u.email || 'sin correo')}</small></td>
                <td>
                    <select onchange="cambiarRolUsuario(${u.id}, this.value)" ${u.username === yo ? 'disabled' : ''}>
                        <option value="admin" ${u.rol === 'admin' ? 'selected' : ''}>Administrador</option>
                        <option value="lectura" ${u.rol === 'lectura' ? 'selected' : ''}>Solo lectura</option>
                    </select>
                </td>
                <td>${u.totp_activo ? '<span class="badge badge-activa">Activo</span>' : '<span class="badge badge-inactiva">No</span>'}</td>
                <td>${!u.activo ? '<span class="badge badge-inactiva">Desactivado</span>'
                    : u.bloqueado ? '<span class="badge badge-inactiva">Bloqueado</span>'
                    : u.debe_cambiar_password ? '<span class="badge">Clave temporal</span>'
                    : '<span class="badge badge-activa">Activo</span>'}</td>
                <td>${escapeHtml(u.ultimo_ingreso || '—')}</td>
                <td class="acciones-usuario">
                    <select onchange="accionUsuario(${u.id}, this.value); this.value=''">
                        <option value="">Acciones…</option>
                        ${u.email ? '<option value="link">Enviar link para crear clave</option>' : ''}
                        <option value="temporal">Asignar clave temporal</option>
                        ${u.totp_activo ? '<option value="2fa">Reiniciar 2FA (perdió el celular)</option>' : ''}
                        ${u.bloqueado ? '<option value="desbloquear">Desbloquear</option>' : ''}
                        <option value="sesiones">Cerrar sus sesiones</option>
                        <option value="editar">Editar nombre / correo</option>
                        ${u.username !== yo ? `<option value="${u.activo ? 'desactivar' : 'activar'}">${u.activo ? 'Desactivar' : 'Reactivar'}</option>` : ''}
                    </select>
                </td>
            </tr>`).join('');
        document.getElementById('body-auditoria').innerHTML = audit.map(a => `
            <tr class="${/fallido|bloqueada|desactivado/.test(a.accion) ? 'fila-alerta' : ''}">
                <td style="white-space:nowrap">${escapeHtml(a.fecha)}</td>
                <td>${escapeHtml(a.usuario || '—')}</td>
                <td>${escapeHtml(ACCIONES_AUDITORIA[a.accion] || a.accion)}</td>
                <td>${escapeHtml(a.detalle || '')}</td>
                <td><small>${escapeHtml(a.ip || '')}</small></td>
            </tr>`).join('') || '<tr><td colspan="5" class="muted">Sin actividad registrada todavía.</td></tr>';
    } catch (err) { toast(err.message, 'error'); }
}

function mostrarFormUsuario() {
    const f = document.getElementById('form-usuario');
    f.style.display = 'block';
    f.querySelector('form').reset();
    document.getElementById('nu-nombre').focus();
}

async function crearUsuario(e) {
    e.preventDefault();
    const v = id => document.getElementById(id).value.trim();
    try {
        const r = await api('/api/usuarios/', {
            method: 'POST',
            body: JSON.stringify({ nombre: v('nu-nombre'), username: v('nu-username'), email: v('nu-email') || null,
                                   rol: v('nu-rol'), password: v('nu-password') || null }),
        });
        toast(r.mensaje);
        document.getElementById('form-usuario').style.display = 'none';
        cargarUsuarios();
    } catch (err) { toast(err.message, 'error'); }
}

async function cambiarRolUsuario(id, rol) {
    try {
        await api(`/api/usuarios/${id}`, { method: 'PUT', body: JSON.stringify({ rol }) });
        toast('Rol actualizado. El usuario deberá volver a ingresar.');
    } catch (err) { toast(err.message, 'error'); }
    cargarUsuarios();
}

async function accionUsuario(id, accion) {
    if (!accion) return;
    const u = usuariosCache.find(x => x.id === id) || {};
    try {
        let r;
        if (accion === 'link') {
            r = await api(`/api/usuarios/${id}/enviar-link`, { method: 'POST' });
        } else if (accion === 'temporal') {
            const clave = prompt(`Clave temporal para ${u.nombre} (mín. 10 caracteres, letras y números).\nDeberá cambiarla al ingresar:`);
            if (!clave) return;
            r = await api(`/api/usuarios/${id}/clave-temporal`, { method: 'POST', body: JSON.stringify({ password: clave }) });
        } else if (accion === '2fa') {
            if (!confirm(`¿Reiniciar la verificación en 2 pasos de ${u.nombre}? Podrá entrar solo con su contraseña hasta que la vuelva a activar.`)) return;
            r = await api(`/api/usuarios/${id}/reiniciar-2fa`, { method: 'POST' });
        } else if (accion === 'desbloquear') {
            r = await api(`/api/usuarios/${id}/desbloquear`, { method: 'POST' });
        } else if (accion === 'sesiones') {
            r = await api(`/api/usuarios/${id}/cerrar-sesiones`, { method: 'POST' });
        } else if (accion === 'editar') {
            const nombre = prompt('Nombre y apellido:', u.nombre);
            if (nombre === null) return;
            const email = prompt('Correo (vacío para quitarlo):', u.email || '');
            if (email === null) return;
            r = await api(`/api/usuarios/${id}`, { method: 'PUT', body: JSON.stringify({ nombre, email }) });
        } else if (accion === 'desactivar' || accion === 'activar') {
            if (accion === 'desactivar' && !confirm(`¿Desactivar a ${u.nombre}? No podrá ingresar más hasta que lo reactives.`)) return;
            r = await api(`/api/usuarios/${id}`, { method: 'PUT', body: JSON.stringify({ activo: accion === 'activar' }) });
        }
        toast((r && r.mensaje) || 'Listo');
        cargarUsuarios();
    } catch (err) { toast(err.message, 'error'); }
}

// =========================================================
// --- IMPORTAR FACTURAS DESDE PLANILLA ---
// =========================================================
let impFilas = [];

function abrirImportarFacturas() {
    document.getElementById('modal-content').innerHTML = `
        <h3>Importar facturas desde una planilla</h3>
        <ol class="tf-pasos">
            <li>Descargá la <a href="/api/importar-gastos/plantilla">plantilla de Excel</a> (o usá la planilla que te armamos con las facturas escaneadas).</li>
            <li>Completá una fila por comprobante y subila acá. <b>Nada se guarda</b> hasta que revises y confirmes.</li>
        </ol>
        <input type="file" id="imp-archivo" accept=".xlsx,.csv" onchange="previsualizarImportacion(this)">
        <div id="imp-resultado"></div>`;
    const m = document.querySelector('#modal-overlay .modal');
    m.classList.add('modal-ancho');
    document.getElementById('modal-overlay').style.display = 'flex';
}

async function previsualizarImportacion(input) {
    const file = input.files[0];
    if (!file) return;
    const cont = document.getElementById('imp-resultado');
    cont.innerHTML = '<p class="muted">Leyendo la planilla…</p>';
    try {
        const fd = new FormData();
        fd.append('archivo', file);
        const res = await fetch('/api/importar-gastos/previsualizar', { method: 'POST', credentials: 'same-origin', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'No se pudo leer la planilla');
        impFilas = data.filas;
        const r = data.resumen;
        const etiqueta = { nuevo: '<span class="badge badge-activa">Nueva</span>', duplicado: '<span class="badge">Ya cargada</span>',
                           repetido: '<span class="badge">Repetida en la planilla</span>', error: '<span class="badge badge-inactiva">Con error</span>' };
        const filas = impFilas.map((f, i) => `<tr class="${f.estado === 'error' ? 'fila-alerta' : f.estado !== 'nuevo' ? 'fila-inactiva' : ''}">
            <td><input type="checkbox" class="imp-sel" data-i="${i}" ${f.estado === 'nuevo' ? 'checked' : 'disabled'} aria-label="Importar fila ${f.fila}"></td>
            <td>${f.fila}</td>
            <td>${fmtFecha(f.fecha)}</td>
            <td>${escapeHtml(f.tipo || '')}<br><small class="muted">${escapeHtml([f.punto_venta, f.numero].filter(Boolean).join('-'))}</small></td>
            <td>${escapeHtml(f.razon_social || '—')}<br><small class="muted">${escapeHtml(f.cuit || 'sin CUIT')}</small></td>
            <td>${escapeHtml(f.concepto || '')}<br><small class="muted">${escapeHtml([f.rubro, f.categoria, f.destino].filter(Boolean).join(' · '))}</small></td>
            <td class="num" style="${f.importe < 0 ? 'color:var(--danger)' : ''}">${f.importe != null ? fmtMoneda(f.importe) : '—'}</td>
            <td>${escapeHtml(f.medio_pago)}${f.fecha_pago ? `<br><small class="muted">${fmtFecha(f.fecha_pago)}</small>` : ''}</td>
            <td>${etiqueta[f.estado] || ''}${[...f.errores, ...f.avisos].map(t => `<br><small style="color:var(--${f.errores.includes(t) ? 'danger' : 'text-muted'})">${escapeHtml(t)}</small>`).join('')}</td>
        </tr>`).join('');
        const hayEfectivo = impFilas.some(f => f.estado === 'nuevo' && f.medio_pago === 'Efectivo');
        cont.innerHTML = `
            <div class="gasto-resumen" style="margin-top:1rem">
                <div class="gasto-kpi"><div class="gasto-kpi-label">Nuevas</div><div class="gasto-kpi-valor" style="color:var(--success)">${r.nuevo}</div><div class="gasto-kpi-sub">${fmtMoneda(r.total_nuevos)}</div></div>
                <div class="gasto-kpi"><div class="gasto-kpi-label">Ya cargadas</div><div class="gasto-kpi-valor">${r.duplicado + r.repetido}</div><div class="gasto-kpi-sub">se omiten</div></div>
                <div class="gasto-kpi"><div class="gasto-kpi-label">Con error</div><div class="gasto-kpi-valor" style="color:var(--danger)">${r.error}</div><div class="gasto-kpi-sub">corregilas en el Excel</div></div>
            </div>
            <table class="imp-tabla"><thead><tr><th></th><th>Fila</th><th>Fecha</th><th>Comprobante</th><th>Proveedor</th><th>Concepto</th><th class="num">Importe</th><th>Pago</th><th>Estado</th></tr></thead>
            <tbody>${filas}</tbody></table>
            ${hayEfectivo ? `<label class="check-inline" style="margin:0.75rem 0"><input type="checkbox" id="imp-caja" checked>
                Registrar los pagos en <b>efectivo</b> como egresos en el Libro de caja</label>` : ''}
            <p class="muted">Las pagadas por <b>transferencia o débito</b> quedan pendientes y se concilian solas al subir el extracto del banco.</p>
            <div class="form-actions"><button class="btn btn-primary" id="imp-ok" onclick="confirmarImportacion()" ${r.nuevo ? '' : 'disabled'}>Importar las seleccionadas</button>
                <button class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button></div>`;
    } catch (err) {
        cont.innerHTML = `<p style="color:var(--danger);font-weight:600;margin-top:0.75rem">${escapeHtml(err.message)}</p>`;
    } finally { input.value = ''; }
}

async function confirmarImportacion() {
    const sel = [...document.querySelectorAll('.imp-sel:checked')].map(c => impFilas[Number(c.dataset.i)]);
    if (!sel.length) return toast('No hay filas seleccionadas', 'error');
    const btn = document.getElementById('imp-ok');
    btn.disabled = true;
    try {
        const caja = document.getElementById('imp-caja');
        const r = await api('/api/importar-gastos/confirmar', { method: 'POST', body: JSON.stringify({
            filas: sel.map(f => ({ fecha: f.fecha, tipo: f.tipo, punto_venta: f.punto_venta, numero: f.numero, cuit: f.cuit,
                razon_social: f.razon_social, importe: f.importe, concepto: f.concepto, rubro: f.rubro, categoria: f.categoria,
                destino: f.destino, medio_pago: f.medio_pago, fecha_pago: f.fecha_pago, notas: f.notas })),
            efectivo_a_caja: caja ? caja.checked : false }) });
        toast(r.mensaje);
        cerrarModal();
        cargarGastos();
    } catch (err) { toast(err.message, 'error'); btn.disabled = false; }
}

// =========================================================
// --- MANTENIMIENTO: dejar finanzas en cero (solo admin) ---
// =========================================================
async function abrirLimpiezaFinanzas() {
    let n = {};
    try { n = await api('/api/mantenimiento/conteos'); } catch (err) { return toast(err.message, 'error'); }
    const op = (id, txt, cant, marcado = true) => `
        <label class="check-inline" style="margin:0.45rem 0"><input type="checkbox" id="lf-${id}" ${marcado ? 'checked' : ''}>
            ${txt} <span class="badge">${cant}</span></label>`;
    document.getElementById('modal-content').innerHTML = `
        <h3>Dejar las finanzas en cero</h3>
        <p class="muted" style="margin-top:-0.4rem">Elegí qué borrar. <b>No se puede deshacer.</b> Alumnos, tarjetas, saldos, cuotas y usuarios no se tocan.</p>
        <div class="mc-card">
            ${op('gastos', 'Gastos y facturas', n.gastos)}
            ${op('conciliacion', 'Conciliación bancaria (extractos y movimientos del banco)', `${n.conciliacion} mov. · ${n.extractos} extracto(s)`)}
            ${op('caja', 'Libro de caja (y su saldo inicial)', n.caja)}
            ${op('proveedores', 'Proveedores (requiere borrar también los gastos)', n.proveedores, false)}
        </div>
        <label class="mc-lbl" for="lf-pass">Tu contraseña</label>
        <input type="password" id="lf-pass" class="mc-inp" autocomplete="current-password">
        <label class="mc-lbl" for="lf-conf">Para confirmar, escribí <b>BORRAR</b></label>
        <input type="text" id="lf-conf" class="mc-inp" autocomplete="off" autocapitalize="characters">
        <div class="form-actions">
            <button class="btn btn-red" id="lf-ok" onclick="confirmarLimpiezaFinanzas()"><svg class="ic"><use href="#i-trash"/></svg>Borrar definitivamente</button>
            <button class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button>
        </div>`;
    document.getElementById('modal-overlay').style.display = 'flex';
    document.getElementById('lf-proveedores').addEventListener('change', e => { if (e.target.checked) document.getElementById('lf-gastos').checked = true; });
}

async function confirmarLimpiezaFinanzas() {
    const v = id => document.getElementById(id);
    if (v('lf-conf').value.trim().toUpperCase() !== 'BORRAR') return toast('Escribí BORRAR para confirmar', 'error');
    const btn = v('lf-ok');
    btn.disabled = true;
    try {
        const r = await api('/api/mantenimiento/limpiar-finanzas', { method: 'POST', body: JSON.stringify({
            password: v('lf-pass').value, confirmacion: v('lf-conf').value,
            gastos: v('lf-gastos').checked, conciliacion: v('lf-conciliacion').checked,
            caja: v('lf-caja').checked, proveedores: v('lf-proveedores').checked }) });
        toast(r.mensaje);
        cerrarModal();
        gastosCache = []; concCache = []; gaDatos = null;
        cargarUsuarios();
    } catch (err) { toast(err.message, 'error'); btn.disabled = false; }
}

// =========================================================
// --- GASTOS: ANÁLISIS Y POR PROVEEDOR ---
// =========================================================
const PALETA_GASTOS = ['#1f5fa8', '#a01e22', '#15803d', '#b45309', '#6d4ec7', '#0e7490', '#94a3b8'];
let gaDatos = null, gaRangoActual = 'mes';
let chartGaRubro = null, chartGaMes = null, chartGaProv = null;

function gastosTab(tab) {
    document.querySelectorAll('.gasto-tab').forEach(b => b.classList.toggle('activo', b.dataset.tab === tab));
    ['facturas', 'analisis', 'proveedores', 'recibidas'].forEach(t =>
        document.getElementById('gastos-tab-' + t).style.display = t === tab ? 'block' : 'none');
    if (tab === 'facturas') cargarGastos();
    else if (tab === 'recibidas') cargarRecibidas();
    else if (!gaDatos) gaRango(gaRangoActual);
    else if (tab === 'analisis') dibujarAnalisisGastos();
    else renderGastosProveedores();
}

// Rangos rápidos (calculados en fecha argentina)
function gaRango(r) {
    gaRangoActual = r;
    document.querySelectorAll('.ga-rango').forEach(b => b.classList.toggle('chip-activo', b.dataset.rango === r));
    if (r !== 'custom') {
        const hoy = hoyISO();
        const [a, m] = hoy.split('-').map(Number);
        const primero = (aa, mm) => `${aa}-${String(mm).padStart(2, '0')}-01`;
        const ultimo = (aa, mm) => isoDeFecha(new Date(aa, mm, 0, 12));
        let desde = '', hasta = '';
        if (r === 'mes') { desde = primero(a, m); hasta = hoy; }
        else if (r === 'mesant') { const mm = m === 1 ? 12 : m - 1, aa = m === 1 ? a - 1 : a; desde = primero(aa, mm); hasta = ultimo(aa, mm); }
        else if (r === 'anio') { desde = `${a}-01-01`; hasta = hoy; }
        else if (r === '12m') { const d = new Date(a, m - 12, 1, 12); desde = primero(d.getFullYear(), d.getMonth() + 1); hasta = hoy; }
        document.getElementById('ga-desde').value = desde;
        document.getElementById('ga-hasta').value = hasta;
    }
    cargarAnalisisGastos();
}

function gaPeriodoTexto() {
    const d = document.getElementById('ga-desde').value, h = document.getElementById('ga-hasta').value;
    if (!d && !h) return 'Todo el historial';
    return `Del ${d ? fmtFecha(d) : 'inicio'} al ${h ? fmtFecha(h) : 'hoy'}`;
}

async function cargarAnalisisGastos() {
    try {
        await cargarGastosMeta();
        const sel = document.getElementById('ga-categoria');
        if (sel.options.length <= 1) gastoOpts('ga-categoria', gastosMeta.categorias, 'Todas las categorías');
        const p = new URLSearchParams();
        const d = document.getElementById('ga-desde').value, h = document.getElementById('ga-hasta').value;
        if (d) p.set('desde', d);
        if (h) p.set('hasta', h);
        if (sel.value) p.set('categoria', sel.value);
        gaDatos = await api('/api/gastos/estadisticas?' + p.toString());
        dibujarAnalisisGastos();
        renderGastosProveedores();
    } catch (err) { toast(err.message, 'error'); }
}

function tablaPorcentajes(filas, etiqueta) {
    if (!filas.length) return '<p class="muted">Sin datos en el período.</p>';
    return `<table><thead><tr><th>${etiqueta}</th><th class="num">Cant.</th><th class="num">Total</th><th style="width:34%">% del total</th></tr></thead><tbody>` +
        filas.map(f => `<tr><td>${escapeHtml(f.nombre)}</td><td class="num">${f.cantidad}</td><td class="num">${fmtMoneda(f.total)}</td>
            <td><div class="barra-pct"><span style="width:${Math.max(0, Math.min(100, f.porcentaje))}%"></span><b>${fmtNumero(f.porcentaje, 1)}%</b></div></td></tr>`).join('') +
        '</tbody></table>';
}

function dibujarAnalisisGastos() {
    const s = gaDatos;
    if (!s || document.getElementById('gastos-tab-analisis').style.display === 'none') return;
    const k = s.kpis;
    document.getElementById('ga-kpis').innerHTML = `
        <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Total gastado</div><div class="gasto-kpi-valor">${fmtMoneda(k.total)}</div><div class="gasto-kpi-sub">${gaPeriodoTexto()}</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Facturas</div><div class="gasto-kpi-valor">${k.facturas}</div><div class="gasto-kpi-sub">promedio ${fmtMoneda(k.promedio)}</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Proveedores</div><div class="gasto-kpi-valor">${k.proveedores}</div><div class="gasto-kpi-sub">con compras en el período</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Pendiente de pago</div><div class="gasto-kpi-valor" style="color:var(--warning)">${fmtMoneda(k.pendiente_pago)}</div><div class="gasto-kpi-sub">${k.facturas - k.pagadas} factura(s) sin pago</div></div>
        <div class="gasto-kpi"><div class="gasto-kpi-label">Conciliadas con banco</div><div class="gasto-kpi-valor">${k.conciliadas}</div><div class="gasto-kpi-sub">de ${k.facturas} facturas</div></div>`;

    // Torta por rubro: los 6 principales + "Otros"
    const top = s.por_rubro.slice(0, 6);
    const otros = s.por_rubro.slice(6).reduce((a, x) => a + x.total, 0);
    const etiquetas = top.map(x => x.nombre).concat(otros > 0 ? ['Otros'] : []);
    const valores = top.map(x => x.total).concat(otros > 0 ? [otros] : []);
    const total = valores.reduce((a, v) => a + v, 0) || 1;
    if (chartGaRubro) chartGaRubro.destroy();
    chartGaRubro = new Chart(document.getElementById('chart-ga-rubro'), {
        type: 'doughnut',
        data: { labels: etiquetas, datasets: [{ data: valores, backgroundColor: PALETA_GASTOS.slice(0, valores.length), borderWidth: 2, borderColor: getComputedStyle(document.documentElement).getPropertyValue('--surface').trim() }] },
        options: {
            cutout: '62%', maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { generateLabels: ch => ch.data.labels.map((l, i) => ({
                    text: `${l}  ${fmtNumero(valores[i] / total * 100, 1)}%`, fillStyle: PALETA_GASTOS[i], strokeStyle: PALETA_GASTOS[i], pointStyle: 'circle', index: i,
                    fontColor: getComputedStyle(document.documentElement).getPropertyValue('--text').trim() })) } },
                tooltip: { callbacks: { label: c => ` ${c.label}: ${fmtMoneda(c.raw)} (${fmtNumero(c.raw / total * 100, 1)}%)` } },
            },
        },
    });

    if (chartGaMes) chartGaMes.destroy();
    chartGaMes = new Chart(document.getElementById('chart-ga-mes'), {
        type: 'bar',
        data: { labels: s.por_mes.map(x => `${MESES[x.mes - 1].slice(0, 3)} ${String(x.anio).slice(2)}`),
                datasets: [{ label: 'Gastos', data: s.por_mes.map(x => x.total), backgroundColor: '#a01e22', maxBarThickness: 40 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ' ' + fmtMoneda(c.raw) } } },
                   scales: { y: { ticks: { callback: v => '$' + (v >= 1e6 ? fmtNumero(v / 1e6, 1) + ' M' : v >= 1000 ? fmtNumero(v / 1000, 0) + ' mil' : v) } } } },
    });

    const provs = s.por_proveedor.slice(0, 10);
    document.getElementById('ga-prov-wrap').style.height = Math.max(160, provs.length * 34 + 40) + 'px';
    if (chartGaProv) chartGaProv.destroy();
    chartGaProv = new Chart(document.getElementById('chart-ga-prov'), {
        type: 'bar',
        data: { labels: provs.map(p => p.razon_social.length > 32 ? p.razon_social.slice(0, 31) + '…' : p.razon_social),
                datasets: [{ data: provs.map(p => p.total), backgroundColor: '#1f5fa8', maxBarThickness: 22 }] },
        options: { indexAxis: 'y', maintainAspectRatio: false,
                   onClick: (e, el) => { if (el.length && provs[el[0].index].proveedor_id) verFacturasProveedor(provs[el[0].index].proveedor_id, true); },
                   plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${fmtMoneda(c.raw)} · ${fmtNumero(provs[c.dataIndex].porcentaje, 1)}% · ${provs[c.dataIndex].cantidad} factura(s)` } } },
                   scales: { x: { ticks: { callback: v => '$' + (v >= 1e6 ? fmtNumero(v / 1e6, 1) + ' M' : v >= 1000 ? fmtNumero(v / 1000, 0) + ' mil' : v) } } } },
    });

    document.getElementById('ga-tabla-rubro').innerHTML = tablaPorcentajes(s.por_rubro, 'Rubro');
    document.getElementById('ga-tabla-categoria').innerHTML = tablaPorcentajes(s.por_categoria, 'Categoría');
    document.getElementById('ga-tabla-destino').innerHTML = tablaPorcentajes(s.por_destino, 'Destino');
    document.getElementById('ga-tabla-pago').innerHTML = tablaPorcentajes(s.por_forma_pago, 'Forma de pago');
}

function renderGastosProveedores() {
    if (!gaDatos) return;
    document.getElementById('gp-periodo').textContent = gaPeriodoTexto() + ' · el período se elige en "Análisis y gráficos"';
    const q = normTxt(document.getElementById('gp-buscar').value);
    const lista = gaDatos.por_proveedor.filter(p => !q || normTxt(`${p.razon_social} ${p.cuit} ${p.rubro}`).includes(q));
    document.getElementById('body-gp').innerHTML = lista.map(p => `<tr>
        <td><b>${escapeHtml(p.razon_social)}</b><br><small class="muted">${escapeHtml(p.cuit || 'sin CUIT')}</small></td>
        <td>${escapeHtml(p.rubro || '—')}</td>
        <td class="num">${p.cantidad}</td>
        <td class="num"><b>${fmtMoneda(p.total)}</b></td>
        <td class="num">${fmtNumero(p.porcentaje, 1)}%</td>
        <td class="num" style="${p.pendiente > 0 ? 'color:var(--warning);font-weight:600' : ''}">${p.pendiente > 0 ? fmtMoneda(p.pendiente) : '—'}</td>
        <td>${fmtFecha(p.ultima)}</td>
        <td>${p.proveedor_id ? `<button class="btn btn-sm btn-primary" onclick="verFacturasProveedor(${p.proveedor_id}, true)">Ver facturas</button>` : ''}</td>
    </tr>`).join('') || '<tr><td colspan="8">No hay gastos en el período.</td></tr>';
}

// Detalle de un proveedor: todas sus facturas, total, pagado y pendiente
async function verFacturasProveedor(pid, usarPeriodo = false) {
    try {
        const p = new URLSearchParams();
        if (usarPeriodo) {
            const d = document.getElementById('ga-desde').value, h = document.getElementById('ga-hasta').value;
            if (d) p.set('desde', d);
            if (h) p.set('hasta', h);
        }
        const r = await api(`/api/gastos/por-proveedor/${pid}?` + p.toString());
        const pr = r.proveedor;
        const filas = r.facturas.map(f => `<tr>
            <td>${fmtFecha(f.fecha)}</td>
            <td>${escapeHtml(f.tipo || '')} ${escapeHtml(f.numero || '')}</td>
            <td>${escapeHtml(f.concepto || '—')}<br><small class="muted">${escapeHtml([f.categoria, f.destino].filter(Boolean).join(' · '))}</small></td>
            <td class="num" style="${f.importe < 0 ? 'color:var(--danger)' : ''}">${fmtMoneda(f.importe)}</td>
            <td>${f.forma_pago ? `<span class="pago-ok">${escapeHtml(f.forma_pago)} · ${fmtFecha(f.fecha_pago)}</span>${f.conciliado ? ' <span class="conc-tag-ok">banco ✓</span>' : ''}`
                               : (f.importe > 0 ? '<span class="conc-pend">Pendiente</span>' : '—')}
                ${f.nota_diferencia ? `<div class="conc-dif">En el banco: ${fmtMoneda(f.pagado_banco)}<br>${escapeHtml(f.nota_diferencia)}</div>` : ''}</td>
            <td>${f.adjunto_url ? `<a class="btn btn-sm" href="${escapeHtml(f.adjunto_url)}" target="_blank" rel="noopener">Ver</a>` : ''}</td>
        </tr>`).join('') || '<tr><td colspan="6">Sin facturas en el período.</td></tr>';
        document.getElementById('modal-content').innerHTML = `
            <h3>${escapeHtml(pr.razon_social)}</h3>
            <p class="muted" style="margin-top:-0.4rem">CUIT ${escapeHtml(pr.cuit)} · ${escapeHtml(pr.rubro || 'sin rubro')}
               ${pr.telefono ? ' · Tel. ' + escapeHtml(pr.telefono) : ''}${pr.email ? ' · ' + escapeHtml(pr.email) : ''}
               ${usarPeriodo ? '<br>' + gaPeriodoTexto() : '<br>Todo el historial'}</p>
            <div class="gasto-resumen" style="margin-top:0.75rem">
                <div class="gasto-kpi gasto-kpi-total"><div class="gasto-kpi-label">Total facturado</div><div class="gasto-kpi-valor">${fmtMoneda(r.total)}</div><div class="gasto-kpi-sub">${r.cantidad} comprobante(s)</div></div>
                <div class="gasto-kpi"><div class="gasto-kpi-label">Pagado</div><div class="gasto-kpi-valor" style="color:var(--success)">${fmtMoneda(r.pagado)}</div>
                    ${r.diferencia_banco ? `<div class="gasto-kpi-sub conc-dif">En el banco ${fmtMoneda(Math.abs(r.diferencia_banco))} ${r.diferencia_banco > 0 ? 'de más' : 'de menos'} (ver observaciones)</div>` : ''}</div>
                <div class="gasto-kpi"><div class="gasto-kpi-label">Pendiente</div><div class="gasto-kpi-valor" style="color:var(--warning)">${fmtMoneda(r.pendiente)}</div></div>
            </div>
            <table><thead><tr><th>Fecha</th><th>Comprobante</th><th>Concepto</th><th class="num">Importe</th><th>Pago</th><th></th></tr></thead><tbody>${filas}</tbody></table>`;
        document.querySelector('#modal-overlay .modal').classList.add('modal-ancho');
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) { toast(err.message, 'error'); }
}

function exportarAnalisisGastos() {
    if (!gaDatos) return;
    const n = v => fmtNumero(v, 2);
    const sep = ';';
    const lineas = [`Análisis de gastos APAI;${gaPeriodoTexto()}`, '', 'RUBRO;Cantidad;Total;% del total',
        ...gaDatos.por_rubro.map(x => [x.nombre, x.cantidad, n(x.total), n(x.porcentaje)].join(sep)), '',
        'PROVEEDOR;CUIT;Rubro;Facturas;Total;% del total;Pendiente de pago;Última factura',
        ...gaDatos.por_proveedor.map(x => [x.razon_social, x.cuit || '', x.rubro || '', x.cantidad, n(x.total), n(x.porcentaje), n(x.pendiente), fmtFecha(x.ultima)].join(sep)), '',
        'CATEGORÍA;Cantidad;Total;% del total', ...gaDatos.por_categoria.map(x => [x.nombre, x.cantidad, n(x.total), n(x.porcentaje)].join(sep)), '',
        'DESTINO;Cantidad;Total;% del total', ...gaDatos.por_destino.map(x => [x.nombre, x.cantidad, n(x.total), n(x.porcentaje)].join(sep)), '',
        'MES;Total', ...gaDatos.por_mes.map(x => [`${MESES[x.mes - 1]} ${x.anio}`, n(x.total)].join(sep))];
    const csv = lineas.map(l => l.replace(/"/g, "'")).join('\r\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `analisis_gastos_${hoyISO()}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
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
const _bsi = document.getElementById('buscar-siro');
if (_bsi) _bsi.addEventListener('input', filtrarSiro);
const _bes = document.getElementById('buscar-estado');
if (_bes) _bes.addEventListener('input', filtrarEstado);
cargarUsuario();
cargarAlumnos();
cargarMovimientosGenerales();


// =========================================================
// CONSULTAS DE FAMILIAS Y REPORTES DE PROBLEMAS
// =========================================================
let consultasEstado = '';
const ESTADO_CONSULTA = {
    abierta: '<span class="badge badge-inactiva">Esperando respuesta</span>',
    respondida: '<span class="badge badge-activa">Respondida</span>',
    cerrada: '<span class="badge">Cerrada</span>',
};

async function actualizarContadorConsultas() {
    try {
        const c = await api('/api/consultas/contador');
        const b = document.getElementById('side-badge-consultas');
        b.textContent = c.sin_leer; b.hidden = !c.sin_leer;
    } catch {}
}

function filtrarConsultas(btn) {
    document.querySelectorAll('#cq-filtros .cuota-tab').forEach(b => b.classList.toggle('activo', b === btn));
    consultasEstado = btn.dataset.estado;
    cargarConsultas();
}

async function cargarConsultas() {
    const body = document.getElementById('body-consultas');
    const qs = new URLSearchParams();
    if (consultasEstado) qs.set('estado', consultasEstado);
    const origen = document.getElementById('cq-origen').value;
    if (origen) qs.set('origen', origen);
    try {
        const lista = await api('/api/consultas/?' + qs);
        body.innerHTML = lista.length ? lista.map(x => `
            <tr class="${x.sin_leer ? 'fila-no-leida' : ''}" style="cursor:pointer" onclick="verConsulta(${x.id})">
                <td>${fmtFechaHora(x.actualizada)}</td>
                <td>${escapeHtml(x.categoria_titulo)}</td>
                <td>${x.sin_leer ? '<span class="punto-nuevo" title="Sin leer"></span>' : ''}<b>${escapeHtml(x.asunto)}</b> <span class="muted">(${x.mensajes_n})</span></td>
                <td>${x.origen === 'sistema' ? '<span class="badge">Personal</span> ' : ''}${escapeHtml(x.autor || '')}</td>
                <td>${x.alumno ? escapeHtml(x.alumno.nombre) + ' <span class="muted">' + escapeHtml(x.alumno.curso || '') + '</span>' : '—'}</td>
                <td>${ESTADO_CONSULTA[x.estado] || escapeHtml(x.estado)}</td>
                <td><button class="btn btn-sm btn-outline" onclick="event.stopPropagation();verConsulta(${x.id})">Abrir</button></td>
            </tr>`).join('') : '<tr><td colspan="7" class="muted" style="text-align:center;padding:1.5rem">No hay consultas con este filtro.</td></tr>';
        actualizarContadorConsultas();
    } catch (e) { toast(e.message, 'error'); }
}

async function verConsulta(id) {
    try {
        const x = await api('/api/consultas/' + id);
        const esAdmin = usuarioActual.rol === 'admin';
        const msjs = x.mensajes.map(m => {
            const nuestro = m.autor === 'admin';
            return `<div class="cq-msj ${nuestro ? 'nuestro' : ''}"><div class="cq-txt">${escapeHtml(m.texto)}</div>
                ${m.adjunto_url ? `<br><a href="${escapeHtml(m.adjunto_url)}" target="_blank" rel="noopener noreferrer">Ver comprobante adjunto</a>` : ''}
                <small>${escapeHtml(nuestro ? m.autor_nombre + ' (APAI)' : m.autor_nombre)} · ${fmtFechaHora(m.fecha)}</small></div>`;
        }).join('');
        window._cqRapidas = x.respuestas_rapidas;
        const rapidas = esAdmin ? x.respuestas_rapidas.map((r, i) =>
            `<button type="button" class="btn btn-sm btn-ghost" onclick="usarRespuestaRapida(${i})">${escapeHtml(r.titulo)}</button>`).join('') : '';
        const alumno = x.alumno ? `${escapeHtml(x.alumno.nombre)} · ${escapeHtml(x.alumno.curso || '')} · legajo ${escapeHtml(x.alumno.legajo)}` : '';
        document.getElementById('modal-content').innerHTML = `
            <h3 style="margin-bottom:0.2rem">${escapeHtml(x.asunto)}</h3>
            <p class="muted" style="margin:0 0 0.5rem">${[escapeHtml(x.categoria_titulo), escapeHtml(x.autor || ''), alumno].filter(Boolean).join(' · ')}
                · ${ESTADO_CONSULTA[x.estado] || ''}</p>
            <div class="cq-hilo">${msjs}</div>
            ${esAdmin ? `
            <label for="cq-resp">Respuesta</label>
            <div class="cq-rapidas">${rapidas}</div>
            <textarea id="cq-resp" rows="4" maxlength="4000" placeholder="Escribí la respuesta.${x.origen === 'portal' ? ' A la familia le llega un aviso por correo.' : ''}"></textarea>
            <div class="form-actions">
                <button class="btn btn-primary btn-3d" onclick="responderConsultaAdmin(${x.id}, false)"><svg class="ic"><use href="#i-mail"/></svg>Responder</button>
                <button class="btn btn-outline" onclick="responderConsultaAdmin(${x.id}, true)">Responder y cerrar</button>
                ${x.estado === 'cerrada'
                    ? `<button class="btn btn-ghost" onclick="estadoConsulta(${x.id}, 'abierta')">Reabrir</button>`
                    : `<button class="btn btn-ghost" onclick="estadoConsulta(${x.id}, 'cerrada')">Cerrar sin responder</button>`}
                ${x.alumno ? `<button class="btn btn-ghost" onclick="cerrarModal();verAlumno(${x.alumno.id})">Ver perfil del alumno</button>
                <button class="btn btn-ghost" onclick="verComoFamilia(${x.alumno.id})">Ver como familia</button>` : ''}
            </div>` : '<p class="muted">Solo un administrador puede responder.</p>'}`;
        const ov = document.getElementById('modal-overlay');
        ov.querySelector('.modal').classList.add('modal-ancho');
        ov.style.display = 'flex';
        const hilo = document.querySelector('.cq-hilo'); hilo.scrollTop = hilo.scrollHeight;
        actualizarContadorConsultas();
    } catch (e) { toast(e.message, 'error'); }
}

function usarRespuestaRapida(i) {
    const t = document.getElementById('cq-resp');
    t.value = window._cqRapidas[i].texto;
    t.focus();
}

async function responderConsultaAdmin(id, cerrar) {
    const texto = document.getElementById('cq-resp').value.trim();
    if (!texto) return toast('Escribí la respuesta', 'error');
    try {
        const r = await api(`/api/consultas/${id}/responder`, { method: 'POST', body: JSON.stringify({ texto, cerrar }) });
        cerrarModal(); toast(r.mensaje);
        if (document.getElementById('sec-consultas').classList.contains('active')) cargarConsultas();
    } catch (e) { toast(e.message, 'error'); }
}

async function estadoConsulta(id, estado) {
    try {
        await api(`/api/consultas/${id}/estado`, { method: 'POST', body: JSON.stringify({ estado }) });
        toast(estado === 'cerrada' ? 'Consulta cerrada' : 'Consulta reabierta');
        cerrarModal(); cargarConsultas();
    } catch (e) { toast(e.message, 'error'); }
}

function abrirReportarProblema() {
    const pantalla = (PAGINAS[location.hash.slice(1)] || ['', 'Inicio'])[1];
    window._rpPantalla = pantalla;
    document.getElementById('modal-content').innerHTML = `
        <h3><svg class="ic"><use href="#i-flag"/></svg> Reportar un problema</h3>
        <p class="muted" style="margin:0.3rem 0 0.8rem">¿Algo no anda o se ve mal? Contalo acá: le llega al administrador del sistema
        y te responde por correo.</p>
        <label for="rp-asunto">Asunto</label>
        <input type="text" id="rp-asunto" maxlength="150" placeholder="Ej: no carga el gráfico de gastos">
        <label for="rp-texto">¿Qué pasó?</label>
        <textarea id="rp-texto" rows="5" maxlength="4000" placeholder="Qué estabas haciendo, qué esperabas que pasara y qué pasó."></textarea>
        <p class="muted" style="font-size:0.82rem">Pantalla: <b>${escapeHtml(pantalla)}</b> (se adjunta automáticamente).</p>
        <div class="form-actions">
            <button class="btn btn-primary btn-3d" id="rp-enviar" onclick="enviarReporteProblema()">Enviar reporte</button>
            <button class="btn btn-ghost" onclick="cerrarModal()">Cancelar</button>
        </div>`;
    document.getElementById('modal-overlay').style.display = 'flex';
    document.getElementById('rp-asunto').focus();
}

async function enviarReporteProblema() {
    const btn = document.getElementById('rp-enviar'); btn.disabled = true;
    try {
        const r = await api('/api/consultas/reportar', { method: 'POST', body: JSON.stringify({
            asunto: document.getElementById('rp-asunto').value, texto: document.getElementById('rp-texto').value,
            pantalla: window._rpPantalla }) });
        cerrarModal(); toast(r.mensaje);
        actualizarContadorConsultas();
    } catch (e) { toast(e.message, 'error'); btn.disabled = false; }
}

// Abre el portal de familias tal cual lo ve la familia del alumno (vista previa de solo lectura)
async function verComoFamilia(alumnoId) {
    const ventana = window.open('', '_blank');  // se abre ya, en el clic, para que el navegador no la bloquee
    try {
        await api('/api/portal/vista-previa', { method: 'POST', body: JSON.stringify({ alumno_id: alumnoId }) });
        if (ventana) ventana.location = '/portal'; else location.href = '/portal';
    } catch (e) {
        if (ventana) ventana.close();
        toast(e.message, 'error');
    }
}


// =========================================================
// CUPONES DE SIRO: se lee el PDF en el navegador y se publican en el portal
// =========================================================
let csCupones = [], csFilas = [], csErrores = [];

function _filasTextoPDF(items, alto) {
    const arr = items.filter(i => i.str && i.str.trim())
        .map(i => ({ s: i.str.trim(), x: i.transform[4], y: alto - i.transform[5] }))
        .sort((a, b) => a.y - b.y || a.x - b.x);
    const filas = [];
    for (const it of arr) {
        const f = filas[filas.length - 1];
        if (f && Math.abs(f.y - it.y) <= 3) f.items.push(it); else filas.push({ y: it.y, items: [it] });
    }
    filas.forEach(f => f.items.sort((a, b) => a.x - b.x));
    return filas;
}

function _parsearCuponSiro(filas) {
    const texto = f => f.items.map(i => i.s).join(' ');
    const fila = re => filas.findIndex(f => re.test(texto(f)));
    const todos = filas.flatMap(f => f.items);
    const iId = fila(/^Identificador/);
    if (iId < 0 || !filas[iId + 1]) throw new Error('no parece un cupón de SIRO');
    const fid = filas[iId + 1].items;
    const ident = fid.find(i => /^\d{7,9}$/.test(i.s));
    if (!ident) throw new Error('no se encontró el identificador');
    const nombre = fid.filter(i => i !== ident && i.x < 405).map(i => i.s).join(' ');
    const iCon = fila(/^Descripci.n de Concepto/);
    const fc = iCon >= 0 && filas[iCon + 1] ? filas[iCon + 1].items : [];
    const iV = fila(/1er vencimiento/);
    const col = x => x < 215 ? 0 : x < 385 ? 1 : 2;
    const fechas = [null, null, null], importes = [null, null, null];
    for (const f of filas.slice(iV + 1, iV + 4)) {
        for (const it of f.items) {
            const m = it.s.match(/^(\d\d)\/(\d\d)\/(\d{4})$/);
            if (m) fechas[col(it.x)] = `${m[3]}-${m[2]}-${m[1]}`;
            else if (/^\$\s?[\d.]+,\d\d$/.test(it.s)) importes[col(it.x)] = Number(it.s.replace(/[$\s.]/g, '').replace(',', '.'));
        }
    }
    const vencimientos = [0, 1, 2].filter(i => fechas[i] && importes[i]).map(i => ({ fecha: fechas[i], importe: importes[i] }));
    if (!vencimientos.length) throw new Error('no se encontraron vencimiento e importe');
    const barras = todos.find(i => /^\d{40,}$/.test(i.s));
    const codigo = todos.find(i => /^\d{15,25}$/.test(i.s));
    return {
        identificador: ident.s, nombre,
        descripcion: fc.filter(i => i.x < 300).map(i => i.s).join(' '),
        periodo: fc.filter(i => i.x >= 300).map(i => i.s).join(' '),
        vencimientos, codigo_barras: barras ? barras.s : null, codigo_pago: codigo ? codigo.s : null,
    };
}

// Imagen de pdf.js ({width, height, kind, data}) -> ImageData RGBA
function _imagenPDFaRGBA(o) {
    const { width: w, height: h, kind, data } = o;
    const out = new Uint8ClampedArray(w * h * 4);
    if (kind === 3) out.set(data.subarray(0, w * h * 4));
    else if (kind === 2) {
        for (let i = 0, j = 0; i < w * h; i++, j += 3) { out[i * 4] = data[j]; out[i * 4 + 1] = data[j + 1]; out[i * 4 + 2] = data[j + 2]; out[i * 4 + 3] = 255; }
    } else {  // 1 bit por pixel, filas completadas al byte
        const fila = (w + 7) >> 3;
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
            const v = (data[y * fila + (x >> 3)] >> (7 - (x & 7))) & 1 ? 255 : 0, k = (y * w + x) * 4;
            out[k] = out[k + 1] = out[k + 2] = v; out[k + 3] = 255;
        }
    }
    return new ImageData(out, w, h);
}

function _pngDe(imgData) {
    const c = document.createElement('canvas');
    c.width = imgData.width; c.height = imgData.height;
    c.getContext('2d').putImageData(imgData, 0, 0);
    return c.toDataURL('image/png');
}

function _leerQR(imgData) {
    const { width: w, height: h, data } = imgData;
    let q = jsQR(data, w, h, { inversionAttempts: 'attemptBoth' });
    if (!q) {  // con margen blanco alrededor lo detecta mejor
        const m = 24, W = w + 2 * m, H = h + 2 * m, d = new Uint8ClampedArray(W * H * 4).fill(255);
        for (let y = 0; y < h; y++) d.set(data.subarray(y * w * 4, (y + 1) * w * 4), ((y + m) * W + m) * 4);
        q = jsQR(d, W, H, { inversionAttempts: 'attemptBoth' });
    }
    return q && q.data ? q.data : null;
}

// Lee un cupón (una página): texto, enlace de pago e imágenes originales del QR y del código de barras.
// No dibuja la página: toma las imágenes tal cual vienen dentro del PDF (más rápido y sin pérdida).
async function _leerPaginaCupon(page) {
    const cupon = _parsearCuponSiro(_filasTextoPDF((await page.getTextContent()).items, page.view[3]));
    const link = (await page.getAnnotations()).find(a => a.url && /PagoOffLine/i.test(a.url));
    cupon.pago_url = link ? link.url : null;
    const ops = await page.getOperatorList();
    const ids = [];
    ops.fnArray.forEach((f, i) => { if (f === pdfjsLib.OPS.paintImageXObject) ids.push(ops.argsArray[i][0]); });
    let qr = null, barras = null;
    for (const id of ids) {
        const o = await new Promise(res => (id.startsWith('g_') ? page.commonObjs : page.objs).get(id, res));
        if (!o || !o.data) continue;
        if (o.width === o.height && o.width >= 150 && (!qr || o.width > qr.width)) qr = o;           // QR: cuadrado grande
        else if (o.width / o.height > 8 && (!barras || o.width > barras.width)) barras = o;          // código de barras: muy apaisado
    }
    cupon.qr_texto = null; cupon.qr_imagen = null; cupon.barras_imagen = null;
    if (qr) {
        const d = _imagenPDFaRGBA(qr);
        cupon.qr_texto = _leerQR(d);
        if (!cupon.qr_texto) cupon.qr_imagen = _pngDe(d);
    }
    if (barras) cupon.barras_imagen = _pngDe(_imagenPDFaRGBA(barras));
    page.cleanup();
    return cupon;
}

function _progresoCupones(hechos, total, texto) {
    document.getElementById('cs-estado').hidden = false;
    document.getElementById('cs-barra').style.width = (total ? Math.round(hechos / total * 100) : 0) + '%';
    document.getElementById('cs-texto').textContent = texto;
}

async function leerCuponesSiro() {
    const archivos = [...document.getElementById('cs-archivos').files];
    if (!archivos.length) return toast('Elegí el PDF de cupones que descargaste de SIRO', 'error');
    if (typeof pdfjsLib === 'undefined' || typeof jsQR === 'undefined') return toast('No se pudo cargar el lector de PDF. Recargá la página.', 'error');
    const btn = document.getElementById('cs-leer'); btn.disabled = true;
    document.getElementById('cs-vista').hidden = true;
    csCupones = []; csErrores = [];
    try {
        const docs = [];
        for (const f of archivos) {
            if (f.size > 80 * 1024 * 1024) { csErrores.push(`${f.name}: el archivo es demasiado grande`); continue; }
            try { docs.push({ f, pdf: await pdfjsLib.getDocument({ data: await f.arrayBuffer(), isOffscreenCanvasSupported: false }).promise }); }
            catch { csErrores.push(`${f.name}: no se pudo abrir el PDF`); }
        }
        const total = docs.reduce((s, d) => s + d.pdf.numPages, 0);
        let hechos = 0;
        for (const { f, pdf } of docs) {
            for (let i = 1; i <= pdf.numPages; i++) {
                _progresoCupones(hechos, total, `Leyendo ${f.name}: cupón ${i} de ${pdf.numPages} (${hechos + 1} de ${total})…`);
                try {
                    const c = await _leerPaginaCupon(await pdf.getPage(i));
                    c.pagina = i; c.archivo = f.name;
                    csCupones.push(c);
                } catch (e) { csErrores.push(`${f.name}, página ${i}: ${e.message}`); }
                hechos++;
            }
            pdf.destroy();
        }
        _progresoCupones(total, total, 'Verificando alumnos…');
        csFilas = [];
        const liviano = csCupones.map(({ qr_imagen, barras_imagen, qr_texto, ...c }) => ({ ...c, qr_texto: qr_texto ? 'x' : null, qr_imagen: qr_imagen ? 'x' : null, barras_imagen: barras_imagen ? 'x' : null }));
        for (let i = 0; i < liviano.length; i += 400) {
            const r = await api('/api/cupones-siro/previsualizar', { method: 'POST', body: JSON.stringify({ cupones: liviano.slice(i, i + 400).map(c => ({ ...c, qr_imagen: null, barras_imagen: null })) }) });
            csFilas.push(...r.filas);
        }
        csFilas.forEach((f, i) => { f.archivo = csCupones[i].archivo; f.qr = !!(csCupones[i].qr_texto || csCupones[i].qr_imagen); });
        document.getElementById('cs-estado').hidden = true;
        renderVistaCupones();
    } catch (e) {
        toast(e.message, 'error');
        document.getElementById('cs-estado').hidden = true;
    } finally { btn.disabled = false; }
}

function renderVistaCupones(soloProblemas = false) {
    const f = csFilas;
    const publicables = f.filter(x => x.alumno && !x.vencido).length;
    const cuenta = (fn) => f.filter(fn).length;
    const estado = x => !x.alumno ? '<span class="badge badge-inactiva">Sin alumno</span>'
        : x.vencido ? '<span class="badge">Vencido: no se publica</span>'
        : x.repetido ? '<span class="badge">Ya cargado: se actualiza</span>' : '<span class="badge badge-activa">Nuevo</span>';
    const filas = f.filter(x => !soloProblemas || !x.alumno || x.vencido || x.avisos.length || !x.qr);
    const v = document.getElementById('cs-vista');
    v.hidden = false;
    v.innerHTML = `
        <h3>Revisá antes de publicar</h3>
        <div class="gasto-resumen">
            <div class="gasto-kpi"><div class="gasto-kpi-label">Cupones leídos</div><div class="gasto-kpi-valor">${f.length}</div><div class="gasto-kpi-sub">${csErrores.length ? csErrores.length + ' página(s) con error' : 'sin errores de lectura'}</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Se publican</div><div class="gasto-kpi-valor" style="color:var(--success)">${publicables}</div><div class="gasto-kpi-sub">${cuenta(x => x.repetido)} ya estaban cargados</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Sin alumno en el padrón</div><div class="gasto-kpi-valor" style="color:var(--${cuenta(x => !x.alumno) ? 'danger' : 'text-muted'})">${cuenta(x => !x.alumno)}</div><div class="gasto-kpi-sub">no se publican</div></div>
            <div class="gasto-kpi"><div class="gasto-kpi-label">Para revisar</div><div class="gasto-kpi-valor" style="color:var(--warning)">${cuenta(x => x.avisos.length || !x.qr)}</div><div class="gasto-kpi-sub">nombre o importe distinto, o sin QR</div></div>
        </div>
        ${csErrores.length ? `<div class="aviso-banda" style="margin:0.6rem 0">${csErrores.map(escapeHtml).join('<br>')}</div>` : ''}
        <label style="display:flex;gap:0.4rem;align-items:center;margin:0.6rem 0"><input type="checkbox" ${soloProblemas ? 'checked' : ''} onchange="renderVistaCupones(this.checked)"> Mostrar solo los que hay que revisar</label>
        <div class="tabla-wrap"><table class="imp-tabla"><thead><tr><th>Archivo · pág.</th><th>Cupón</th><th>Alumno en el sistema</th><th>Concepto</th><th style="text-align:right">Importe</th><th>Vence</th><th>QR</th><th>Estado</th></tr></thead><tbody>
        ${filas.map(x => `<tr>
            <td>${escapeHtml(x.archivo)} · ${x.pagina}</td>
            <td>${escapeHtml(x.identificador)}<br><span class="muted">${escapeHtml(x.nombre_cupon || '')}</span></td>
            <td>${x.alumno ? `${escapeHtml(x.alumno.nombre)}<br><span class="muted">${escapeHtml(x.alumno.curso || '')} · por ${x.alumno.via === 'dni' ? 'DNI' : 'legajo ' + escapeHtml(x.alumno.legajo)}</span>` : '<span style="color:var(--danger)">No encontrado</span>'}
                ${x.avisos.length ? `<div style="color:var(--warning);font-size:0.8rem">⚠ ${x.avisos.map(escapeHtml).join('; ')}</div>` : ''}</td>
            <td>${escapeHtml(x.concepto)}</td>
            <td style="text-align:right">${fmtMoneda(x.importe)}</td>
            <td>${fmtFecha(x.vence)}</td>
            <td>${x.qr ? '✓' : '<span style="color:var(--warning)">✗</span>'}</td>
            <td>${estado(x)}</td></tr>`).join('') || '<tr><td colspan="8" class="muted" style="text-align:center">Nada para revisar.</td></tr>'}
        </tbody></table></div>
        <div class="form-actions">
            <button class="btn btn-primary btn-3d" id="cs-publicar" onclick="publicarCuponesSiro()" ${publicables ? '' : 'disabled'}>Publicar ${publicables} cupón(es) en el portal</button>
            <button class="btn btn-ghost" onclick="document.getElementById('cs-vista').hidden=true">Cancelar</button>
        </div>`;
}

async function publicarCuponesSiro() {
    const btn = document.getElementById('cs-publicar'); btn.disabled = true;
    const porArchivo = {};
    csCupones.forEach((c, i) => { if (csFilas[i].alumno && !csFilas[i].vencido) (porArchivo[c.archivo] = porArchivo[c.archivo] || []).push(c); });
    const total = Object.values(porArchivo).reduce((s, l) => s + l.length, 0);
    let hechos = 0, nuevos = 0, actualizados = 0;
    try {
        for (const [archivo, lista] of Object.entries(porArchivo)) {
            const lote = Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
            for (let i = 0; i < lista.length; i += 25) {
                _progresoCupones(hechos, total, `Publicando ${archivo}: ${hechos} de ${total}…`);
                const r = await api('/api/cupones-siro/importar', { method: 'POST', body: JSON.stringify({ archivo, lote, cupones: lista.slice(i, i + 25) }) });
                nuevos += r.nuevos; actualizados += r.actualizados; hechos += Math.min(25, lista.length - i);
            }
        }
        document.getElementById('cs-estado').hidden = true;
        document.getElementById('cs-vista').hidden = true;
        document.getElementById('cs-archivos').value = '';
        toast(`Listo: ${nuevos} cupones nuevos y ${actualizados} actualizados ya se ven en el portal`);
        cargarLotesCupones();
    } catch (e) { toast(e.message, 'error'); btn.disabled = false; }
}

async function cargarLotesCupones() {
    psCargar();
    try {
        const lotes = await api('/api/cupones-siro/lotes');
        const esAdmin = usuarioActual.rol === 'admin';
        document.getElementById('body-lotes-cupones').innerHTML = lotes.map(l => `<tr>
            <td>${fmtFechaHora(l.cargado)}</td><td>${escapeHtml(l.archivo || '')}</td><td>${escapeHtml(l.concepto || '')}</td>
            <td style="text-align:right">${l.cupones}</td><td style="text-align:right">${fmtMoneda(l.total)}</td><td>${fmtFecha(l.vence)}</td>
            <td>${l.vigente ? '<span class="badge badge-activa">Vigente</span>' : '<span class="badge">Vencido (oculto)</span>'}</td>
            <td>${esAdmin ? `<button class="btn btn-sm btn-danger" onclick="borrarLoteCupones('${escapeHtml(l.lote)}')">Quitar</button>` : ''}</td></tr>`).join('')
            || '<tr><td colspan="8" class="muted" style="text-align:center;padding:1.2rem">Todavía no se cargaron cupones de SIRO.</td></tr>';
    } catch (e) { toast(e.message, 'error'); }
}

async function borrarLoteCupones(lote) {
    if (!confirm('¿Quitar estos cupones del portal? Las familias dejarán de verlos.')) return;
    try {
        const r = await api('/api/cupones-siro/lotes/' + encodeURIComponent(lote), { method: 'DELETE' });
        toast(`Se quitaron ${r.borrados} cupones`); cargarLotesCupones();
    } catch (e) { toast(e.message, 'error'); }
}


// =========================================================
// CONFIGURACIÓN DEL SISTEMA: datos fiscales de APAI y módulos
// =========================================================
let sistemaCfg = { tarjeta_activa: false, apai: {} };

async function cargarSistema() {
    try { sistemaCfg = await api('/api/config/sistema'); } catch {}
    actualizarBadgeRecibidas();
    actualizarBadgePedidos();
    document.body.classList.toggle('sin-tarjeta', !sistemaCfg.tarjeta_activa);
    if (!sistemaCfg.tarjeta_activa && ['cobrar', 'operaciones', 'tarjetas', 'reportes'].includes(location.hash.slice(1))) history.replaceState(null, '', location.pathname);
    dashKPIs();
}

function renderConfigSistema() {
    const c = document.getElementById('config-sistema');
    if (!c) return;
    const a = sistemaCfg.apai || {};
    const url = location.origin + '/facturas';
    c.innerHTML = `
        <h3 style="margin-bottom:0.3rem">Datos de APAI y módulos</h3>
        <p class="muted" style="margin:0 0 0.8rem">Estos datos se muestran en el portal de facturas para que los proveedores facturen a nombre de APAI.</p>
        <div class="form-grid">
            <div style="grid-column:1/-1"><label for="cfg-razon">Razón social</label><input id="cfg-razon" value="${escapeHtml(a.razon_social || '')}"></div>
            <div><label for="cfg-cuit">CUIT</label><input id="cfg-cuit" value="${escapeHtml(a.cuit || '')}"></div>
            <div><label for="cfg-iva">Condición frente al IVA</label><input id="cfg-iva" value="${escapeHtml(a.condicion_iva || '')}"></div>
            <div style="grid-column:1/-1"><label for="cfg-dom">Domicilio</label><input id="cfg-dom" value="${escapeHtml(a.domicilio || '')}"></div>
            <div style="grid-column:1/-1"><label class="check-inline"><input type="checkbox" id="cfg-tarjeta" ${sistemaCfg.tarjeta_activa ? 'checked' : ''}>
                Tarjeta APAI activa <span class="muted">(desmarcada: se ocultan cobros, recargas, tarjetas y consumos, y las familias no ven el saldo)</span></label></div>
        </div>
        <div class="form-actions" style="align-items:center">
            <button class="btn btn-primary btn-3d" onclick="guardarConfigSistema()">Guardar</button>
            <span class="muted">Portal de facturas para proveedores: <a href="${url}" target="_blank" rel="noopener">${url}</a>
            <button class="btn btn-sm btn-ghost" onclick="copiarTexto('${url}','Enlace copiado')">Copiar enlace</button></span>
        </div>`;
}

async function guardarConfigSistema() {
    try {
        await api('/api/config/sistema', { method: 'POST', body: JSON.stringify({
            apai_razon_social: document.getElementById('cfg-razon').value, apai_cuit: document.getElementById('cfg-cuit').value,
            apai_domicilio: document.getElementById('cfg-dom').value, apai_condicion_iva: document.getElementById('cfg-iva').value,
            tarjeta_activa: document.getElementById('cfg-tarjeta').checked }) });
        toast('Configuración guardada');
        await cargarSistema(); renderConfigSistema();
    } catch (e) { toast(e.message, 'error'); }
}


// =========================================================
// CURSOS DEL ALUMNO (más de uno en el año: aeronavegantes, exámenes)
// =========================================================
async function cargarCursosAlumno(id) {
    const cont = document.getElementById('ac-' + id);
    if (!cont) return;
    try {
        const anio = new Date().getFullYear();
        const [mios, todos] = await Promise.all([api(`/api/alumnos/${id}/cursos`), api(`/api/cursos/?anio=${anio}`)]);
        const esAdmin = usuarioActual.rol === 'admin';
        const libres = todos.filter(c => c.activo && !mios.some(m => m.curso_id === c.id));
        cont.innerHTML = `<h4 style="margin:0.8rem 0 0">Cursos ${anio}</h4>
            <ul class="ac-lista">${mios.map(m => `<li><span><b>${escapeHtml(m.nombre)}</b>${m.principal && mios.length > 1 ? ' <span class="badge">principal</span>' : ''}
                <span class="muted"> · cuota ${fmtMoneda(m.cuota)} × ${m.n_cuotas}${m.matricula ? ' + matrícula ' + fmtMoneda(m.matricula) : ''} · desde ${MESES_ES[m.mes_inicio - 1]}</span></span>
                ${esAdmin && m.id && mios.length > 1 ? `<button class="btn btn-sm btn-ghost" onclick="quitarCursoAlumno(${id}, ${m.id})">Quitar</button>` : ''}</li>`).join('')
                || '<li class="muted">No se encontró su curso en la configuración de cursos.</li>'}</ul>
            ${esAdmin && libres.length ? `<div class="ac-form">
                <label>Sumar otro curso <select id="ac-curso-${id}">${libres.map(c => `<option value="${c.id}">${escapeHtml(c.nombre)} (${fmtMoneda(c.cuota)} × ${c.n_cuotas})</option>`).join('')}</select></label>
                <label>desde <select id="ac-mes-${id}">${MESES_ES.map((m, i) => `<option value="${i + 1}" ${i + 1 === new Date().getMonth() + 1 ? 'selected' : ''}>${m}</option>`).join('')}</select></label>
                <button class="btn btn-sm btn-outline" onclick="agregarCursoAlumno(${id})">Agregar curso</button></div>` : ''}`;
    } catch (e) { cont.innerHTML = ''; }
}

async function agregarCursoAlumno(id) {
    try {
        const r = await api(`/api/alumnos/${id}/cursos`, { method: 'POST', body: JSON.stringify({
            curso_id: Number(document.getElementById('ac-curso-' + id).value), mes_inicio: Number(document.getElementById('ac-mes-' + id).value) }) });
        toast(r.mensaje); verAlumno(id);
    } catch (e) { toast(e.message, 'error'); }
}

async function quitarCursoAlumno(id, filaId) {
    if (!confirm('¿Quitar este curso del alumno? Sus cuotas dejan de contarse.')) return;
    try { const r = await api(`/api/alumnos/${id}/cursos/${filaId}`, { method: 'DELETE' }); toast(r.mensaje); verAlumno(id); }
    catch (e) { toast(e.message, 'error'); }
}

async function imputarPagoCurso(pagoId, cursoId) {
    try {
        await api(`/api/cuotas/pagos/${pagoId}/imputar`, { method: 'POST', body: JSON.stringify({ curso_id: cursoId ? Number(cursoId) : null }) });
        toast('Imputación actualizada');
        const m = document.querySelector('.ac-bloque');
        if (m) verAlumno(Number(m.id.slice(3)));
    } catch (e) { toast(e.message, 'error'); }
}


// =========================================================
// GASTOS: sugerencias por proveedor y facturas recibidas del portal
// =========================================================
async function sugerirDatosProveedor(param) {
    try {
        const r = await api('/api/gastos/sugerencias?' + new URLSearchParams(param));
        for (const [campo, id] of [['rubro', 'gasto-rubro'], ['concepto', 'gasto-concepto'], ['destino', 'gasto-destino']]) {
            const el = document.getElementById(id);
            if (r[campo] && !el.value) el.value = r[campo];
        }
    } catch { /* sin historial */ }
}

let recibidasEstado = '';
let recibidasCache = [];

async function actualizarBadgeRecibidas() {
    try {
        const c = await api('/api/facturas-recibidas/contador');
        const b = document.getElementById('badge-recibidas');
        if (b) { b.textContent = c.sin_cargar; b.hidden = !c.sin_cargar; }
        const r = document.getElementById('badge-por-revisar');
        if (r) { r.textContent = c.sin_revisar; r.hidden = !c.sin_revisar; }
    } catch {}
}

function filtrarRecibidas(btn) {
    document.querySelectorAll('#rec-estados .chip').forEach(b => b.classList.toggle('chip-activo', b === btn));
    recibidasEstado = btn.dataset.estado;
    cargarRecibidas();
}

async function cargarRecibidas() {
    try {
        recibidasCache = await api('/api/facturas-recibidas/' + (recibidasEstado ? '?estado=' + recibidasEstado : ''));
        const esAdmin = usuarioActual.rol === 'admin';
        const chip = { cargada: 'badge-activa', revisar: 'badge-revisar', duplicada: '', descartada: '' };
        document.getElementById('body-recibidas').innerHTML = recibidasCache.map(x => {
            const d = x.datos || {};
            const comp = [d.tipo, d.numero ? `${d.punto_venta || ''}-${d.numero}` : ''].filter(Boolean).join(' ');
            const acciones = [];
            if (x.gasto) acciones.push(`<button class="btn btn-sm ${x.gasto.revisado ? '' : 'btn-primary'}" onclick="abrirGastoRecibido(${x.gasto.id})">${x.gasto.revisado ? 'Ver gasto' : 'Revisar'}</button>`);
            if (x.estado === 'revisar' && esAdmin) {
                acciones.push(`<button class="btn btn-sm btn-primary" onclick="cargarRecibidaAMano(${x.id})">Cargar</button>`);
                acciones.push(`<button class="btn btn-sm btn-ghost" onclick="reintentarRecibida(${x.id})" title="Busca el QR de AFIP en esta computadora">Leer QR</button>`);
                acciones.push(`<button class="btn btn-sm btn-ghost" onclick="descartarRecibida(${x.id})">Descartar</button>`);
            }
            return `<tr>
                <td>${fmtFechaHora(x.recibida)}</td>
                <td><a href="/api/facturas-recibidas/${x.id}/archivo" target="_blank" rel="noopener">${escapeHtml(x.archivo)}</a>
                    ${x.comentario ? `<div class="muted" style="font-size:0.8rem">💬 ${escapeHtml(x.comentario)}</div>` : ''}</td>
                <td>${escapeHtml(d.razon_social || x.proveedor_declarado || '—')}${d.cuit ? `<div class="muted" style="font-size:0.8rem">CUIT ${escapeHtml(d.cuit)}</div>` : ''}
                    ${x.email ? `<div class="muted" style="font-size:0.8rem">${escapeHtml(x.email)}</div>` : ''}</td>
                <td>${escapeHtml(comp || '—')}${d.fecha ? `<div class="muted" style="font-size:0.8rem">${fmtFecha(d.fecha)}</div>` : ''}</td>
                <td class="num">${d.importe != null ? fmtMoneda(d.importe) : '—'}</td>
                <td><span class="badge ${chip[x.estado] || ''}">${escapeHtml(x.estado_texto)}</span>
                    ${x.motivo ? `<div class="muted" style="font-size:0.78rem">${escapeHtml(x.motivo)}</div>` : ''}</td>
                <td>${acciones.join(' ')}</td></tr>`;
        }).join('') || '<tr><td colspan="7" class="muted" style="text-align:center;padding:1.2rem">No hay facturas recibidas con este filtro.</td></tr>';
        actualizarBadgeRecibidas();
    } catch (e) { toast(e.message, 'error'); }
}

async function abrirGastoRecibido(id) {
    gastosTab('facturas');
    await cargarGastos();
    if (!gastosCache.some(g => g.id === id)) {  // puede estar fuera del período elegido
        filtrarEstadoGasto(document.querySelector('#gasto-estados [data-estado="por_revisar"]'));
        await cargarGastos();
    }
    editarGasto(id);
}

function cargarRecibidaAMano(id) {
    const x = recibidasCache.find(r => r.id === id);
    if (!x) return;
    const d = x.datos || {};
    gastosTab('facturas');
    mostrarFormGasto();
    const set = (campo, v) => { if (v != null && v !== '') document.getElementById(campo).value = v; };
    set('gasto-fecha', d.fecha); set('gasto-pv', d.punto_venta); set('gasto-numero', d.numero);
    set('gasto-cuit', d.cuit); set('gasto-razon', d.razon_social || x.proveedor_declarado);
    set('gasto-importe', d.importe); set('gasto-concepto', d.concepto); set('gasto-vencimiento', d.vencimiento); set('gasto-cae', d.cae);
    if (d.tipo) document.getElementById('gasto-tipo').value = d.tipo;
    document.getElementById('gasto-adjunto').value = `/api/facturas-recibidas/${x.id}/archivo`;
    document.getElementById('gasto-recibida-id').value = x.id;
    if (d.cuit) sugerirDatosProveedor({ cuit: d.cuit });
    gastoMostrarVerAdjunto();
    const rev = document.getElementById('gasto-revision');
    rev.hidden = false;
    rev.innerHTML = `Cargando a mano la factura <b>${escapeHtml(x.archivo)}</b> recibida del portal (<a href="/api/facturas-recibidas/${x.id}/archivo" target="_blank" rel="noopener">abrir PDF</a>).
        ${x.motivo ? escapeHtml(x.motivo) + '.' : ''}`;
}

async function reintentarRecibida(id) {
    toast('Buscando el QR de AFIP en la factura…');
    try {
        const blob = await (await fetch(`/api/facturas-recibidas/${id}/archivo`, { credentials: 'same-origin' })).blob();
        const qr = await escanearQR(new File([blob], 'factura.pdf', { type: 'application/pdf' }));
        if (!qr) return toast('No se encontró el QR de AFIP: cargala a mano con «Cargar».', 'error');
        const r = await api(`/api/facturas-recibidas/${id}/reprocesar`, { method: 'POST', body: JSON.stringify({ qr }) });
        toast(r.estado === 'cargada' ? 'Leída: quedó en Facturas → Por revisar' : r.mensaje, r.estado === 'cargada' ? 'success' : 'error');
        cargarRecibidas();
    } catch (e) { toast(e.message, 'error'); }
}

async function descartarRecibida(id) {
    if (!confirm('¿Descartar esta factura? No se carga como gasto (el PDF queda guardado).')) return;
    try { await api(`/api/facturas-recibidas/${id}/descartar`, { method: 'POST' }); toast('Factura descartada'); cargarRecibidas(); }
    catch (e) { toast(e.message, 'error'); }
}


// Desde las estadísticas: abre el estado de cuenta filtrado por ese estado (y el área elegida)
function verAlumnosConEstado(filtro) {
    document.getElementById('estado-f-estado').value = filtro;
    const area = document.getElementById('st-area').value;
    const selArea = document.getElementById('estado-f-area');
    if (selArea) selArea.value = [...selArea.options].some(o => o.value === area) ? area : '';
    document.getElementById('buscar-estado').value = '';
    cuotaTab('estado');
    document.getElementById('tabla-estado').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// =========================================================
// --- PLANILLA PARA SIRO (Excel de carga de cupones) ---
// =========================================================
// Se traen una sola vez los cursos con todos sus alumnos (y si reciben cupón o por qué no);
// la lista, los totales y la vista previa se calculan acá al instante. El Excel lo arma el servidor.

let psCursos = [];
const psSel = new Set();          // cursos elegidos, en el orden en que se marcaron
const psAbiertos = new Set();     // cursos desplegados en la lista
const PS_AREAS = { 'Ciclo Basico': 'Ciclo Básico', 'Avionica': 'Aviónica', 'Mecanica': 'Mecánica', 'Examenes': 'Exámenes' };
const PS_ESTADOS = { becado: ['Becado', 'badge-beca'], pagado: ['Año pagado', 'badge-pagado'], sin_numero: ['Sin número', 'badge-sin'] };

function psUltimoDiaMes() {
    const h = new Date();
    const f = new Date(h.getFullYear(), h.getMonth() + 1, 0);
    return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, '0')}-${String(f.getDate()).padStart(2, '0')}`;
}

async function psCargar() {
    if (usuarioActual.rol !== 'admin') return;
    const vto = document.getElementById('ps-vto');
    if (!vto.value) vto.value = psUltimoDiaMes();
    try {
        psCursos = await api('/api/cupones-siro/planilla/cursos');
    } catch (e) { document.getElementById('ps-cursos').innerHTML = `<p class="muted" style="padding:1rem">${escapeHtml(e.message)}</p>`; return; }
    psCursos.forEach(c => { c.importeElegido = c.importe; });
    [...psSel].forEach(id => { if (!psCursos.some(c => c.id === id)) psSel.delete(id); });
    psDibujarLista();
    psRender();
}

const psCurso = id => psCursos.find(c => c.id === id);

function psReciben(c) {
    const sinPagados = document.getElementById('ps-pagados').checked;
    return c.alumnos.filter(a => a.estado === 'ok' || (a.estado === 'pagado' && !sinPagados));
}

function psConteos(c) {
    const n = { becado: 0, pagado: 0, sin_numero: 0 };
    c.alumnos.forEach(a => { if (n[a.estado] !== undefined) n[a.estado]++; });
    return n;
}

function psDibujarLista() {
    const areas = [];
    psCursos.forEach(c => { let g = areas.find(a => a.area === c.area); if (!g) areas.push(g = { area: c.area, cursos: [] }); g.cursos.push(c); });
    document.getElementById('ps-cursos').innerHTML = areas.map(g => `
        <section class="ps-grupo" data-area="${escapeHtml(g.area || '')}">
            <header class="ps-grupo-cab">
                <label class="ps-check"><input type="checkbox" class="ps-sel-area" onchange="psMarcarArea(this)"> ${escapeHtml(PS_AREAS[g.area] || g.area || 'Sin área')}</label>
                <span class="ps-chip">Nº cliente: ${g.cursos[0].cliente}</span>
            </header>
            <ul class="ps-cursos-lista">${g.cursos.map(psFilaCurso).join('')}</ul>
        </section>`).join('');
    psFiltrar();
}

function psFilaCurso(c) {
    return `<li class="ps-curso" data-id="${c.id}">
        <div class="ps-curso-fila">
            <label class="ps-check ps-curso-nombre"><input type="checkbox" class="ps-sel" value="${c.id}" onchange="psMarcar(${c.id}, this.checked)">
                <span><span class="ps-nombre">${escapeHtml(c.nombre)}</span><small class="ps-sub"></small></span></label>
            <span class="ps-importe">$ <input type="number" min="1" step="0.01" value="${c.importe}" aria-label="Importe de ${escapeHtml(c.nombre)}"
                oninput="psImporte(${c.id}, this.value)"></span>
            <button type="button" class="ps-abrir" onclick="psAbrir(${c.id})" aria-expanded="false" title="Ver alumnos del curso" aria-label="Ver alumnos de ${escapeHtml(c.nombre)}">
                <svg class="ic"><use href="#i-chevron"/></svg></button>
        </div>
        <div class="ps-alumnos" hidden></div>
    </li>`;
}

function psMarcar(id, on) {
    on ? psSel.add(id) : psSel.delete(id);
    psRender();
}

function psMarcarArea(el) {
    el.closest('.ps-grupo').querySelectorAll('.ps-sel').forEach(x => { x.checked = el.checked; el.checked ? psSel.add(+x.value) : psSel.delete(+x.value); });
    psRender();
}

function psImporte(id, v) {
    const c = psCurso(id);
    const n = parseFloat(v);
    c.importeElegido = n > 0 ? n : c.importe;
    psRender();
}

function psAbrir(id) {
    psAbiertos.has(id) ? psAbiertos.delete(id) : psAbiertos.add(id);
    psRender();
}

function psFiltrar() {
    const q = (document.getElementById('ps-filtro').value || '').trim().toLowerCase();
    document.querySelectorAll('.ps-curso').forEach(li => {
        const c = psCurso(+li.dataset.id);
        const porNombre = !q || c.nombre.toLowerCase().includes(q) || (c.area || '').toLowerCase().includes(q);
        const porAlumno = q && c.alumnos.some(a => a.alumno.toLowerCase().includes(q) || (a.cliente || '').includes(q));
        li.hidden = !(porNombre || porAlumno);
        li.dataset.q = porAlumno && !porNombre ? q : '';
    });
    document.querySelectorAll('.ps-grupo').forEach(g => { g.hidden = ![...g.querySelectorAll('.ps-curso')].some(li => !li.hidden); });
    psRender();
}

// Filas de la planilla: un cupón por número de cliente (si cursa dos cursos elegidos, se suman)
function psFilas() {
    const filas = new Map();
    [...psSel].forEach(id => {
        const c = psCurso(id);
        psReciben(c).forEach(a => {
            const imp = a.personal || c.importeElegido;
            const f = filas.get(a.cliente);
            if (f) { f.importe += imp; f.cursos.push(a.etiqueta); }
            else filas.set(a.cliente, { cliente: a.cliente, tipo: a.tipo, alumno: a.alumno, cursos: [a.etiqueta], importe: imp, personal: !!a.personal });
        });
    });
    return [...filas.values()];
}

function psRender() {
    if (!psCursos.length) return;
    // Lista de cursos: marcas, subtítulos y alumnos desplegados
    document.querySelectorAll('.ps-curso').forEach(li => {
        const c = psCurso(+li.dataset.id);
        const on = psSel.has(c.id);
        li.classList.toggle('activo', on);
        li.querySelector('.ps-sel').checked = on;
        const rec = psReciben(c).length, n = psConteos(c);
        const extra = [n.becado && `${n.becado} becado${n.becado === 1 ? '' : 's'}`,
            n.pagado && `${n.pagado} con el año pagado`, n.sin_numero && `${n.sin_numero} sin número`].filter(Boolean);
        li.querySelector('.ps-sub').textContent = `${rec} cupón${rec === 1 ? '' : 'es'}` + (extra.length ? ' · ' + extra.join(' · ') : '');
        const abierto = psAbiertos.has(c.id) || !!li.dataset.q;
        const caja = li.querySelector('.ps-alumnos');
        li.querySelector('.ps-abrir').setAttribute('aria-expanded', abierto);
        li.classList.toggle('abierto', abierto);
        caja.hidden = !abierto;
        if (abierto) caja.innerHTML = psTablaAlumnos(c, li.dataset.q);
    });
    document.querySelectorAll('.ps-grupo').forEach(g => {
        const hijos = [...g.querySelectorAll('.ps-sel')];
        const a = g.querySelector('.ps-sel-area');
        a.checked = hijos.every(h => h.checked);
        a.indeterminate = !a.checked && hijos.some(h => h.checked);
    });

    // Panel de la planilla
    const filas = psFilas();
    const total = filas.reduce((s, f) => s + f.importe, 0);
    const ul = document.getElementById('ps-elegidos');
    const ids = [...psSel];
    if (!ids.length) {
        ul.innerHTML = '<li class="ps-vacio">Todavía no elegiste cursos.<br><span class="muted">Marcalos en la lista y se van sumando acá.</span></li>';
    } else {
        // los que ya estaban se actualizan; los nuevos entran con animación
        const previos = new Set([...ul.querySelectorAll('li[data-id]')].map(li => +li.dataset.id));
        ul.innerHTML = ids.map(id => {
            const c = psCurso(id), rec = psReciben(c);
            const sub = rec.reduce((s, a) => s + (a.personal || c.importeElegido), 0);
            return `<li data-id="${id}" class="${previos.has(id) ? '' : 'nuevo'}">
                <div><b>${escapeHtml(c.nombre)}</b><small>${rec.length} cupón${rec.length === 1 ? '' : 'es'} · ${fmtMoneda(c.importeElegido, 0)} c/u</small></div>
                <span class="ps-sub-total">${fmtMoneda(sub, 0)}</span>
                <button type="button" class="ps-quitar" onclick="psMarcar(${id}, false)" title="Quitar" aria-label="Quitar ${escapeHtml(c.nombre)}"><svg class="ic"><use href="#i-x"/></svg></button>
            </li>`;
        }).join('');
    }
    document.getElementById('ps-totales').innerHTML = ids.length ? `
        <div class="ps-total"><span>Total de la planilla</span><b>${fmtMoneda(total)}</b></div>
        <div><span>Cupones</span><b>${filas.length}</b></div>
        <div><span>Vencen</span><b>${document.getElementById('ps-vto').value ? fmtFecha(document.getElementById('ps-vto').value) : '—'}</b></div>` : '';
    const juntos = filas.filter(f => f.cursos.length > 1).length;
    const sinNum = ids.flatMap(id => psCurso(id).alumnos.filter(a => a.estado === 'sin_numero'));
    document.getElementById('ps-avisos').innerHTML =
        (juntos ? `<p class="ps-nota">${juntos} alumno${juntos === 1 ? ' cursa' : 's cursan'} dos de estos cursos: un solo cupón con la suma.</p>` : '') +
        (sinNum.length ? `<p class="ps-nota ps-nota-alerta">${sinNum.length} alumno${sinNum.length === 1 ? '' : 's'} sin número de cliente no van en la planilla (desplegá el curso para verlos).</p>` : '');
    document.getElementById('ps-descargar').disabled = !filas.length;
    document.getElementById('ps-btn-vista').disabled = !filas.length;
    if (!document.getElementById('ps-vista').hidden) psDibujarVista(filas, total);
}

function psTablaAlumnos(c, q) {
    const sinPagados = document.getElementById('ps-pagados').checked;
    let lista = c.alumnos;
    if (q) lista = lista.filter(a => a.alumno.toLowerCase().includes(q) || (a.cliente || '').includes(q));
    if (!lista.length) return '<p class="muted" style="margin:0.4rem 0">No hay alumnos en este curso.</p>';
    return `<table class="ps-mini"><tbody>${lista.map(a => {
        const queda = a.estado === 'ok' || (a.estado === 'pagado' && !sinPagados);
        const [txt, cls] = PS_ESTADOS[a.estado] || [];
        return `<tr class="${queda ? '' : 'fuera'}">
            <td class="num">${a.cliente || '—'}</td>
            <td>${escapeHtml(a.alumno)}${a.etiqueta !== c.nombre ? ` <span class="muted">${escapeHtml(a.etiqueta)}</span>` : ''}</td>
            <td class="num">${queda ? fmtMoneda(a.personal || c.importeElegido, 0) : ''}</td>
            <td>${txt ? `<span class="badge ${cls}" title="${escapeHtml(a.motivo || '')}">${txt}</span>` : ''}${a.personal && queda ? '<span class="badge" title="Monto personalizado del alumno">Monto propio</span>' : ''}</td>
        </tr>`; }).join('')}</tbody></table>`;
}

function psToggleVista() {
    const v = document.getElementById('ps-vista');
    v.hidden = !v.hidden;
    document.getElementById('ps-btn-vista').innerHTML = `<svg class="ic"><use href="#i-eye"/></svg>${v.hidden ? 'Ver planilla' : 'Ocultar planilla'}`;
    if (!v.hidden) { psRender(); v.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
}

function psDibujarVista(filas, total) {
    const vto = document.getElementById('ps-vto').value;
    const orden = [...filas].sort((a, b) => a.cursos[0].localeCompare(b.cursos[0]) || a.alumno.localeCompare(b.alumno));
    document.getElementById('ps-vista').innerHTML = `
        <div class="ps-vista-cab"><b>Así queda el Excel</b><span class="muted">${filas.length} filas · ${fmtMoneda(total)}</span></div>
        <div class="ps-tabla"><table>
            <thead><tr><th>Nro Cliente</th><th>1º Vto</th><th style="text-align:right">1º Monto</th><th>Alumno</th><th>Curso</th></tr></thead>
            <tbody>${orden.map(f => `<tr><td class="num"><b>${f.cliente}</b> <span class="muted">${f.tipo}</span></td><td>${vto ? fmtFecha(vto) : ''}</td>
                <td class="num" style="text-align:right">${fmtMoneda(f.importe)}</td><td>${escapeHtml(f.alumno)}</td><td>${escapeHtml(f.cursos.join(' + '))}</td></tr>`).join('')}</tbody>
        </table></div>`;
}

function psPedido() {
    return {
        vencimiento: document.getElementById('ps-vto').value,
        cursos: [...psSel].map(id => ({ curso_id: id, importe: psCurso(id).importeElegido })),
        excluir_pagados: document.getElementById('ps-pagados').checked,
    };
}

async function psDescargar() {
    const p = psPedido();
    if (!p.vencimiento) { toast('Poné la fecha del 1º vencimiento', 'error'); document.getElementById('ps-vto').focus(); return; }
    if (!p.cursos.length) { toast('Elegí al menos un curso', 'error'); return; }
    const btn = document.getElementById('ps-descargar');
    btn.disabled = true;
    try {
        const res = await fetch('/api/cupones-siro/planilla/excel', {
            method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p),
        });
        if (!res.ok) { let d = {}; try { d = await res.json(); } catch {} throw new Error(d.detail || 'No se pudo generar la planilla'); }
        const nombre = (/filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '') || [])[1] || 'cupones_siro.xlsx';
        const url = URL.createObjectURL(await res.blob());
        const a = Object.assign(document.createElement('a'), { href: url, download: nombre });
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        toast('Planilla descargada. Subila en SIRO para generar los cupones.');
    } catch (e) { toast(e.message, 'error'); }
    finally { btn.disabled = false; }
}

// =========================================================
// --- PEDIDOS DE MATERIALES (formulario público /pedidos) ---
// =========================================================
const PDX_ESTADOS = { nuevo: 'Nuevo', en_revision: 'En revisión', presupuestando: 'Pidiendo presupuestos', aprobado: 'Aprobado',
    comprado: 'Comprado', entregado: 'Entregado', rechazado: 'Rechazado' };
const PDX_FILTROS = [['abiertos', 'Abiertos'], ['nuevo', 'Nuevos'], ['en_revision', 'En revisión'], ['presupuestando', 'Pidiendo presupuestos'],
    ['aprobado', 'Aprobados'], ['comprado', 'Comprados'], ['entregado', 'Entregados'], ['rechazado', 'Rechazados'], ['', 'Todos']];
const PDX_UNIDADES = ['Unidad', 'Caja', 'Paquete', 'Resma', 'Bolsa', 'Rollo', 'Juego', 'Par', 'Docena', 'Metro', 'Metro²',
    'Litro', 'Kilo', 'Gramo', 'Hora', 'Servicio', 'Otra'];
let pdxFiltro = 'abiertos';
let pdxLista = [];
const pdxSel = new Set();
let pdxActual = null;   // pedido abierto en el modal
let pdxEditando = false;

function pdxEstadoBadge(e) {
    const cls = { nuevo: 'badge-pdx-nuevo', en_revision: 'badge-pdx-rev', presupuestando: 'badge-pdx-pres', aprobado: 'badge-pdx-ok',
        comprado: 'badge-pdx-ok', entregado: 'badge-activa', rechazado: 'badge-pdx-no' }[e] || '';
    return `<span class="badge ${cls}">${escapeHtml(PDX_ESTADOS[e] || e)}</span>`;
}
const pdxCant = n => Number(n).toLocaleString('es-AR', { maximumFractionDigits: 2 });

async function actualizarBadgePedidos() {
    try {
        const c = await api('/api/pedidos/contador');
        const b = document.getElementById('side-badge-pedidos');
        if (b) { b.textContent = c.nuevos; b.hidden = !c.nuevos; }
        return c;
    } catch { return null; }
}

async function cargarPedidos() {
    document.getElementById('pdx-url').textContent = location.origin + '/pedidos';
    document.getElementById('pdx-estados').innerHTML = PDX_FILTROS.map(([k, t]) =>
        `<button type="button" class="chip ${k === pdxFiltro ? 'chip-activo' : ''}" onclick="pdxFiltrar('${k}')">${t}${k === 'nuevo' ? ' <span class="side-badge" id="pdx-badge-nuevos" hidden></span>' : ''}</button>`).join('');
    try {
        pdxLista = await api('/api/pedidos/' + (pdxFiltro ? '?estado=' + pdxFiltro : ''));
    } catch (e) { toast(e.message, 'error'); pdxLista = []; }
    const c = await actualizarBadgePedidos();
    const bn = document.getElementById('pdx-badge-nuevos');
    if (bn && c) { bn.textContent = c.nuevos; bn.hidden = !c.nuevos; }
    pintarPedidos();
}

function pdxFiltrar(k) { pdxFiltro = k; cargarPedidos(); }

function pintarPedidos() {
    const q = normTxt(document.getElementById('pdx-filtro').value.trim());
    const lista = pdxLista.filter(p => !q || normTxt([p.numero, p.solicitante, p.cargo, p.sector, p.resumen].join(' ')).includes(q));
    const hoy = hoyISO();
    document.getElementById('body-pedidos').innerHTML = lista.map(p => {
        const vencido = p.necesario_para && p.necesario_para < hoy && !['entregado', 'rechazado'].includes(p.estado);
        return `<tr class="pdx-fila ${p.estado === 'nuevo' ? 'pdx-nuevo' : ''}" onclick="if(!event.target.closest('.pdx-chk'))verPedido(${p.id})" tabindex="0"
                onkeydown="if(event.key==='Enter')verPedido(${p.id})">
            <td class="pdx-chk"><input type="checkbox" ${pdxSel.has(p.id) ? 'checked' : ''} onchange="pdxMarcar(${p.id}, this.checked)" aria-label="Seleccionar el pedido ${p.numero}"></td>
            <td class="num"><b>${p.numero}</b></td>
            <td class="num">${fmtFecha(p.creado.slice(0, 10))}</td>
            <td>${escapeHtml(p.solicitante)}${p.cargo ? `<br><small class="muted">${escapeHtml(p.cargo)}</small>` : ''}</td>
            <td>${escapeHtml(p.sector)}</td>
            <td><b>${p.n_items}</b> <span class="muted">· ${escapeHtml(p.resumen)}</span></td>
            <td>${p.urgente ? '<span class="badge badge-pdx-no">Urgente</span> ' : ''}${p.necesario_para ? `<span class="${vencido ? 'pdx-vencido' : ''}">${fmtFecha(p.necesario_para)}</span>` : (p.urgente ? '' : '<span class="muted">—</span>')}</td>
            <td>${pdxEstadoBadge(p.estado)}</td></tr>`;
    }).join('') || `<tr><td colspan="8" class="muted" style="text-align:center;padding:1.6rem">${pdxLista.length ? 'Ningún pedido coincide con la búsqueda.'
        : 'No hay pedidos en esta lista. Compartí el enlace del formulario con los profesores y el personal.'}</td></tr>`;
    pdxActualizarSeleccion();
}

function pdxMarcar(id, on) { on ? pdxSel.add(id) : pdxSel.delete(id); pdxActualizarSeleccion(); }
function pdxMarcarTodos(on) { pdxLista.forEach(p => on ? pdxSel.add(p.id) : pdxSel.delete(p.id)); pintarPedidos(); }
function pdxLimpiarSeleccion() { pdxSel.clear(); pintarPedidos(); }
function pdxActualizarSeleccion() {
    const n = pdxSel.size;
    document.getElementById('pdx-seleccion').hidden = !n;
    document.getElementById('pdx-sel-txt').innerHTML = `<b>${n}</b> pedido${n === 1 ? '' : 's'} seleccionado${n === 1 ? '' : 's'}: sus productos van juntos en un solo PDF.`;
    const todos = document.getElementById('pdx-todos');
    todos.checked = pdxLista.length > 0 && pdxLista.every(p => pdxSel.has(p.id));
}

// ---------------------------------------------------------------- detalle
async function verPedido(id) {
    try { pdxActual = await api('/api/pedidos/' + id); } catch (e) { return toast(e.message, 'error'); }
    pdxEditando = false;
    pdxPintarModal();
    const ov = document.getElementById('modal-overlay');
    ov.querySelector('.modal').classList.add('modal-ancho');
    ov.style.display = 'flex';
}

function pdxDetalleItem(it) {
    return [['Marca', it.marca], ['Modelo', it.modelo], ['Color', it.color], ['Medida', it.tamanio], ['Características', it.caracteristicas]]
        .filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(' · ');
}

function pdxPintarModal() {
    const p = pdxActual, esAdmin = usuarioActual.rol === 'admin';
    const tipo = { materiales: 'Materiales', servicio: 'Servicio', ambos: 'Materiales y servicio' }[p.tipo] || p.tipo;
    const items = pdxEditando ? pdxTablaEditable(p.items) : `<div class="pdx-items"><table><thead><tr><th>#</th><th>Producto o servicio</th>
        <th style="text-align:right">Cantidad</th><th>Unidad</th></tr></thead><tbody>${p.items.map((it, i) => `<tr>
            <td class="muted">${i + 1}</td>
            <td><b>${escapeHtml(it.producto)}</b>${pdxDetalleItem(it) ? `<div class="pdx-det">${escapeHtml(pdxDetalleItem(it))}</div>` : ''}${it.descripcion ? `<div class="pdx-det pdx-desc">${escapeHtml(it.descripcion)}</div>` : ''}</td>
            <td class="num" style="text-align:right"><b>${pdxCant(it.cantidad)}</b></td><td>${escapeHtml(it.unidad)}</td></tr>`).join('')}</tbody></table></div>`;
    document.getElementById('modal-content').innerHTML = `
        <div class="pdx-cab">
            <div><h2 style="margin:0">Pedido N° ${p.numero}</h2>
                <p class="muted" style="margin:0.15rem 0 0">Recibido el ${fmtFechaHora(p.creado)} · ${escapeHtml(tipo)}${p.urgente ? ' · <span class="badge badge-pdx-no">Urgente</span>' : ''}</p></div>
            <label class="pdx-estado">Estado
                <select id="pdx-estado" ${esAdmin ? '' : 'disabled'}>${Object.entries(PDX_ESTADOS).map(([k, t]) => `<option value="${k}" ${k === p.estado ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        </div>
        <div class="pdx-bloques">
            <div class="pdx-bloque"><h4>Pedido por</h4>
                <p><b>${escapeHtml(p.solicitante)}</b>${p.cargo ? `<br><span class="muted">${escapeHtml(p.cargo)}</span>` : ''}</p>
                ${p.email ? `<p><a href="mailto:${escapeHtml(p.email)}?subject=${encodeURIComponent('Pedido de materiales N° ' + p.numero)}">${escapeHtml(p.email)}</a></p>` : ''}
                ${p.telefono ? `<p>${escapeHtml(p.telefono)}</p>` : ''}</div>
            <div class="pdx-bloque"><h4>Destino</h4>
                <p><b>${escapeHtml(p.sector)}</b></p>
                <p>${p.necesario_para ? `Lo necesita para el <b>${fmtFecha(p.necesario_para)}</b>` : '<span class="muted">Sin fecha límite</span>'}</p>
                ${p.motivo ? `<p class="pdx-motivo">${escapeHtml(p.motivo)}</p>` : ''}</div>
        </div>
        <div class="pdx-items-cab"><h4 style="margin:0">Productos (${p.items.length})</h4>
            ${esAdmin && !pdxEditando ? '<button type="button" class="btn btn-ghost btn-sm" onclick="pdxEditar(true)"><svg class="ic"><use href="#i-pencil"/></svg>Corregir productos</button>' : ''}</div>
        ${items}
        <label for="pdx-notas" style="display:block;margin-top:1rem">Notas internas <span class="muted">(no las ve quien hizo el pedido)</span></label>
        <textarea id="pdx-notas" rows="3" maxlength="3000" ${esAdmin ? '' : 'disabled'} placeholder="Ej.: pedí presupuesto a Ferretería X y Y el 15/10…">${escapeHtml(p.notas || '')}</textarea>
        <div class="form-actions pdx-acciones">
            ${esAdmin ? `<button class="btn btn-ghost pdx-borrar" onclick="borrarPedido(${p.id})"><svg class="ic"><use href="#i-trash"/></svg>Eliminar</button>` : ''}
            <span style="flex:1"></span>
            <button class="btn btn-outline" onclick="pdfPresupuesto([pdxActual])"><svg class="ic"><use href="#i-download"/></svg>PDF para presupuesto</button>
            ${esAdmin ? `<button class="btn btn-primary" onclick="guardarPedido()">Guardar cambios</button>` : ''}
        </div>`;
}

function pdxTablaEditable(items) {
    const campo = (i, c, v, ph = '', ancho = '') => `<input type="text" data-i="${i}" data-c="${c}" value="${escapeHtml(v ?? '')}" placeholder="${ph}" ${ancho}>`;
    return `<div class="pdx-edit" id="pdx-edit">${items.map((it, i) => `<div class="pdx-edit-it">
        <div class="pdx-edit-fila">${campo(i, 'producto', it.producto, 'Producto o servicio', 'class="pdx-e-prod" aria-label="Producto"')}
            ${campo(i, 'cantidad', pdxCant(it.cantidad), 'Cant.', 'class="pdx-e-cant" inputmode="decimal" aria-label="Cantidad"')}
            <select data-i="${i}" data-c="unidad" aria-label="Unidad">${PDX_UNIDADES.concat(PDX_UNIDADES.includes(it.unidad) ? [] : [it.unidad]).map(u => `<option ${u === it.unidad ? 'selected' : ''}>${escapeHtml(u)}</option>`).join('')}</select>
            <button type="button" class="btn btn-ghost btn-sm" onclick="pdxQuitarItem(${i})" aria-label="Quitar"><svg class="ic"><use href="#i-trash"/></svg></button></div>
        <div class="pdx-edit-fila pdx-edit-det">${campo(i, 'marca', it.marca, 'Marca')}${campo(i, 'modelo', it.modelo, 'Modelo')}${campo(i, 'color', it.color, 'Color')}${campo(i, 'tamanio', it.tamanio, 'Medida')}</div>
        <div class="pdx-edit-fila">${campo(i, 'caracteristicas', it.caracteristicas, 'Características')}</div>
        <div class="pdx-edit-fila"><textarea data-i="${i}" data-c="descripcion" rows="1" placeholder="Descripción adicional">${escapeHtml(it.descripcion || '')}</textarea></div>
    </div>`).join('')}
    <div class="pdx-edit-btns"><button type="button" class="btn btn-ghost btn-sm" onclick="pdxAgregarItem()"><svg class="ic"><use href="#i-plus"/></svg>Agregar producto</button>
        <button type="button" class="btn btn-ghost btn-sm" onclick="pdxEditar(false)">Cancelar corrección</button></div></div>`;
}

function pdxLeerEdicion() {
    const box = document.getElementById('pdx-edit');
    if (!box) return pdxActual.items;
    const items = pdxActual.items.map(it => ({ ...it }));
    box.querySelectorAll('[data-i]').forEach(el => {
        let v = el.value;
        if (el.dataset.c === 'cantidad') v = Number(String(v).trim().replace(/\./g, '').replace(',', '.'));
        items[+el.dataset.i][el.dataset.c] = v;
    });
    return items;
}

function pdxEditar(on) {
    if (on === false) { pdxEditando = false; return verPedido(pdxActual.id); }
    pdxActual.notas = document.getElementById('pdx-notas').value;
    pdxEditando = true;
    pdxPintarModal();
}
function pdxAgregarItem() {
    pdxActual.items = pdxLeerEdicion();
    pdxActual.notas = document.getElementById('pdx-notas').value;
    pdxActual.items.push({ producto: '', cantidad: 1, unidad: 'Unidad' });
    pdxPintarModal();
}
function pdxQuitarItem(i) {
    pdxActual.items = pdxLeerEdicion();
    pdxActual.notas = document.getElementById('pdx-notas').value;
    if (pdxActual.items.length === 1) return toast('El pedido tiene que tener al menos un producto', 'error');
    pdxActual.items.splice(i, 1);
    pdxPintarModal();
}

async function guardarPedido() {
    const cuerpo = { estado: document.getElementById('pdx-estado').value, notas: document.getElementById('pdx-notas').value };
    if (pdxEditando) {
        const items = pdxLeerEdicion().map(it => {
            const o = {};
            ['producto', 'marca', 'modelo', 'color', 'tamanio', 'caracteristicas', 'unidad', 'descripcion'].forEach(k => { o[k] = (it[k] || '').toString().trim() || null; });
            o.cantidad = it.cantidad;
            return o;
        });
        const mal = items.findIndex(it => !it.producto || !(it.cantidad > 0));
        if (mal >= 0) return toast(`Revisá el producto ${mal + 1}: falta el nombre o la cantidad`, 'error');
        cuerpo.items = items.map(it => ({ ...it, unidad: it.unidad || 'Unidad' }));
    }
    try {
        pdxActual = await api('/api/pedidos/' + pdxActual.id, { method: 'PUT', body: JSON.stringify(cuerpo) });
        pdxEditando = false;
        pdxPintarModal();
        toast('Pedido guardado');
        cargarPedidos();
    } catch (e) { toast(e.message, 'error'); }
}

async function borrarPedido(id) {
    if (!confirm(`¿Eliminar el pedido N° ${pdxActual.numero}? No se puede deshacer.`)) return;
    try {
        await api('/api/pedidos/' + id, { method: 'DELETE' });
        pdxSel.delete(id);
        cerrarModal();
        toast('Pedido eliminado');
        cargarPedidos();
    } catch (e) { toast(e.message, 'error'); }
}

// ---------------------------------------------------------------- PDF para pedir presupuestos
// Solo los productos: no lleva los datos de quien hizo el pedido ni el sector.
async function pdfPresupuestoSeleccion() {
    try {
        const pedidos = await Promise.all([...pdxSel].sort((a, b) => a - b).map(id => api('/api/pedidos/' + id)));
        await pdfPresupuesto(pedidos);
    } catch (e) { toast(e.message, 'error'); }
}

async function pdfPresupuesto(pedidos) {
    if (typeof window.jspdf === 'undefined') return toast('No se pudo cargar el generador de PDF', 'error');
    if (pdxEditando && pedidos.length === 1 && pedidos[0] === pdxActual) return toast('Guardá primero la corrección de los productos', 'error');
    const items = pedidos.flatMap(p => p.items);
    if (!items.length) return toast('No hay productos para cotizar', 'error');
    let apai = {};
    try { apai = await (await fetch('/api/publico/apai')).json(); } catch { }
    const fechas = pedidos.map(p => p.necesario_para).filter(Boolean).sort();
    const refs = pedidos.map(p => p.numero).join(', ');
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight();
    const logo = await _imagenLogo();

    doc.setFillColor(21, 35, 59); doc.rect(0, 0, W, 30, 'F');
    doc.setFillColor(160, 30, 34); doc.rect(0, 30, W, 1.4, 'F');
    if (logo) { doc.setFillColor(255, 255, 255); doc.circle(21, 15, 9.5, 'F'); doc.addImage(logo, 'PNG', 12.5, 6.5, 17, 17); }
    doc.setTextColor(255, 255, 255); doc.setFont('helvetica', 'bold'); doc.setFontSize(17);
    doc.text('Solicitud de presupuesto', 36, 14);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(10); doc.setTextColor(200, 214, 234);
    doc.text(apai.razon_social || 'Asociación de Padres y Alumnos del I.N.A.C.', 36, 21);
    doc.setFontSize(9);
    doc.text(`Fecha: ${fmtFecha(hoyISO())}`, W - 14, 14, { align: 'right' });
    doc.text(`Ref.: pedido${pedidos.length > 1 ? 's' : ''} N° ${refs}`.slice(0, 60), W - 14, 21, { align: 'right' });

    // Datos de la Asociación (a nombre de quién se presupuesta)
    let y = 40;
    doc.setTextColor(91, 107, 128); doc.setFontSize(8.5); doc.setFont('helvetica', 'bold');
    doc.text('PRESUPUESTO A NOMBRE DE', 14, y);
    doc.setFont('helvetica', 'normal'); doc.setTextColor(30, 41, 59); doc.setFontSize(10);
    const datos = [apai.razon_social, apai.cuit ? 'CUIT ' + apai.cuit : null, apai.condicion_iva, apai.domicilio].filter(Boolean);
    doc.text(datos.slice(0, 2).join('  ·  '), 14, y + 6);
    if (datos.length > 2) doc.text(datos.slice(2).join('  ·  '), 14, y + 11.5);
    y += datos.length > 2 ? 18 : 13;
    if (fechas.length) {
        doc.setFillColor(253, 243, 230); doc.roundedRect(14, y - 4.5, W - 28, 8, 1.5, 1.5, 'F');
        doc.setTextColor(180, 83, 9); doc.setFont('helvetica', 'bold'); doc.setFontSize(9.5);
        doc.text(`Se necesita para el ${fmtFecha(fechas[0])}`, 17, y + 0.8);
        doc.setFont('helvetica', 'normal');
        y += 9;
    }

    const detalle = it => [pdxDetalleItem(it), it.descripcion].filter(Boolean).join('\n');
    doc.autoTable({
        startY: y + 2, margin: { left: 14, right: 14 }, theme: 'grid',
        head: [['#', 'Producto o servicio', 'Cant.', 'Unidad', 'Precio unit.', 'Subtotal']],
        body: items.map((it, i) => [String(i + 1), { content: it.producto + (detalle(it) ? '\n' + detalle(it) : ''), producto: it.producto },
            pdxCant(it.cantidad), it.unidad, '', '']),
        foot: [['', '', '', '', 'TOTAL', '']],
        styles: { fontSize: 9.5, cellPadding: 2.4, textColor: [30, 41, 59], lineColor: [210, 218, 230], lineWidth: 0.2, valign: 'top' },
        headStyles: { fillColor: [21, 35, 59], textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 9 },
        footStyles: { fillColor: [243, 245, 249], textColor: [21, 35, 59], fontStyle: 'bold', halign: 'right' },
        alternateRowStyles: { fillColor: [248, 250, 252] },
        columnStyles: { 0: { cellWidth: 9, halign: 'center', textColor: [120, 130, 145] }, 1: { cellWidth: 'auto' },
            2: { cellWidth: 16, halign: 'right', fontStyle: 'bold' }, 3: { cellWidth: 20 }, 4: { cellWidth: 26 }, 5: { cellWidth: 26 } },
        didParseCell: d => {  // el nombre en negrita y el detalle más chico debajo
            if (d.section === 'body' && d.column.index === 1 && d.cell.raw && d.cell.raw.producto) d.cell.styles.fontStyle = 'normal';
        },
        willDrawCell: d => {
            if (d.section === 'body' && d.column.index === 1 && d.cell.raw && d.cell.raw.producto) {
                d.cell.text = [];  // se dibuja a mano en didDrawCell
            }
        },
        didDrawCell: d => {
            if (d.section !== 'body' || d.column.index !== 1 || !d.cell.raw || !d.cell.raw.producto) return;
            const x = d.cell.x + 2.4, ancho = d.cell.width - 4.8;
            let yy = d.cell.y + 2.4 + 3.2;
            doc.setFont('helvetica', 'bold'); doc.setFontSize(9.5); doc.setTextColor(21, 35, 59);
            const nom = doc.splitTextToSize(d.cell.raw.producto, ancho);
            doc.text(nom, x, yy); yy += nom.length * 4.1;
            const det = d.cell.raw.content.slice(d.cell.raw.producto.length).trim();
            if (det) {
                doc.setFont('helvetica', 'normal'); doc.setFontSize(8.5); doc.setTextColor(91, 107, 128);
                doc.text(doc.splitTextToSize(det, ancho), x, yy);
            }
        },
    });

    y = doc.lastAutoTable.finalY + 8;
    if (y > H - 40) { doc.addPage(); y = 20; }
    doc.setFont('helvetica', 'bold'); doc.setFontSize(9.5); doc.setTextColor(21, 35, 59);
    doc.text('Por favor, en el presupuesto indicar:', 14, y);
    doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(60, 72, 90);
    ['Precio unitario y total de cada producto (aclarar si incluye IVA).', 'Plazo de entrega y si incluye envío.',
        'Forma de pago y validez del presupuesto.', 'Si ofrecen una marca o modelo alternativo, detallarlo.']
        .forEach((t, i) => doc.text('•  ' + t, 17, y + 6 + i * 5));

    const paginas = doc.internal.getNumberOfPages();
    for (let i = 1; i <= paginas; i++) {
        doc.setPage(i);
        doc.setDrawColor(226, 232, 240); doc.line(14, H - 13, W - 14, H - 13);
        doc.setFontSize(8); doc.setTextColor(140, 150, 165);
        doc.text(apai.razon_social || 'APAI', 14, H - 8);
        doc.text(`Página ${i} de ${paginas}`, W - 14, H - 8, { align: 'right' });
    }
    doc.save(`solicitud_presupuesto_${pedidos.map(p => p.numero).join('_').slice(0, 40)}.pdf`);
}

// =========================================================
// --- EXCEL MENSUAL PARA LA CONTADORA (formato de la planilla modelo) ---
// =========================================================
const XC_DESTINOS = { Oficina: 'Gtos. de Oficina', Infraestructura: 'Infraestructura', Escuela: 'Gtos. de la Escuela', Honorarios: 'Honorarios' };

function abrirExcelContadora() {
    // por defecto, el mes del filtro de la pantalla (o el mes anterior, que es el que se rinde)
    const fm = document.getElementById('gasto-f-mes').value, fa = document.getElementById('gasto-f-anio').value;
    const hoy = new Date(), ant = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
    const mes = +(fm || ant.getMonth() + 1), anio = +(fa || ant.getFullYear());
    const anios = [];
    for (let a = hoy.getFullYear(); a >= 2025; a--) anios.push(a);
    document.getElementById('modal-content').innerHTML = `
        <h2 style="margin-top:0">Excel para la contadora</h2>
        <p class="muted" style="margin-top:-0.4rem">Las facturas del mes (por la fecha de la factura) clasificadas por destino, con el formato de siempre:
        hoja TOTALES y una hoja por destino con su total. En PAGOS va la fecha en que se pagó cada una.</p>
        <div class="xc-filtros">
            <div><label for="xc-mes">Mes</label><select id="xc-mes" onchange="xcVista()">${MESES.map((m, i) => `<option value="${i + 1}" ${i + 1 === mes ? 'selected' : ''}>${m}</option>`).join('')}</select></div>
            <div><label for="xc-anio">Año</label><select id="xc-anio" onchange="xcVista()">${anios.map(a => `<option ${a === anio ? 'selected' : ''}>${a}</option>`).join('')}</select></div>
        </div>
        <div id="xc-vista"><p class="muted">Calculando…</p></div>
        <div class="form-actions"><button class="btn btn-primary" id="xc-bajar" onclick="xcDescargar()" disabled><svg class="ic"><use href="#i-download"/></svg>Descargar Excel</button></div>`;
    const ov = document.getElementById('modal-overlay');
    ov.querySelector('.modal').classList.remove('modal-ancho');
    ov.style.display = 'flex';
    xcVista();
}

function xcParams() {
    return `anio=${document.getElementById('xc-anio').value}&mes=${document.getElementById('xc-mes').value}`;
}

async function xcVista() {
    const caja = document.getElementById('xc-vista');
    try {
        const r = await api('/api/gastos/excel-contadora/vista?' + xcParams());
        const lista = (t, xs) => `<details class="xc-det"><summary>${t}</summary><ul>${xs.slice(0, 40).map(g =>
            `<li>${fmtFecha(g.fecha)} · ${escapeHtml(g.razon_social || 'Sin proveedor')} · ${fmtMoneda(g.importe)}</li>`).join('')}</ul></details>`;
        caja.innerHTML = r.cantidad ? `
            <table class="xc-tabla"><thead><tr><th>Hoja</th><th style="text-align:right">Facturas</th><th style="text-align:right">Total</th></tr></thead>
            <tbody>${r.por_destino.map(d => `<tr><td>${XC_DESTINOS[d.categoria] || d.categoria}</td><td class="num" style="text-align:right">${d.cantidad}</td>
                <td class="num" style="text-align:right">${fmtMoneda(d.total)}</td></tr>`).join('')}</tbody>
            <tfoot><tr><td>TOTAL</td><td class="num" style="text-align:right">${r.por_destino.reduce((s, d) => s + d.cantidad, 0)}</td><td class="num" style="text-align:right">${fmtMoneda(r.total)}</td></tr></tfoot></table>
            ${r.sin_destino.length ? `<div class="ps-aviso"><b>${r.sin_destino.length} factura${r.sin_destino.length === 1 ? '' : 's'} sin destino</b>: no suman en ninguna hoja;
                van en la hoja «A REVISAR». Asignales un destino antes de mandar el Excel.${lista('Ver cuáles', r.sin_destino)}</div>` : ''}
            ${r.sin_revisar.length ? `<p class="xc-nota">${r.sin_revisar.length} llegaron por el portal de proveedores y todavía no se revisaron: suman en su hoja y también se listan en «A REVISAR».</p>` : ''}
            ${r.sin_pagar ? `<p class="xc-nota">${r.sin_pagar} todavía no tienen el pago registrado: salen con la fecha y el medio de pago vacíos.</p>` : ''}`
            : '<p class="muted">No hay facturas en ese mes.</p>';
        document.getElementById('xc-bajar').disabled = !r.cantidad;
    } catch (e) { caja.innerHTML = `<p class="muted">${escapeHtml(e.message)}</p>`; }
}

async function xcDescargar() {
    const btn = document.getElementById('xc-bajar');
    btn.disabled = true;
    try {
        const res = await fetch('/api/gastos/excel-contadora?' + xcParams(), { credentials: 'same-origin' });
        if (!res.ok) { let d = {}; try { d = await res.json(); } catch {} throw new Error(d.detail || 'No se pudo generar el Excel'); }
        const nombre = (/filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '') || [])[1] || 'Gastos.xlsx';
        const url = URL.createObjectURL(await res.blob());
        const a = Object.assign(document.createElement('a'), { href: url, download: nombre });
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        toast(`Descargado: ${nombre}`);
    } catch (e) { toast(e.message, 'error'); }
    finally { btn.disabled = false; }
}

// =========================================================
// --- FACTURAS DESDE UN PDF ESCANEADO (QR + OCR en el navegador) ---
// =========================================================
// Cada página se dibuja con pdf.js; se busca el QR de AFIP (jsQR) y se reconoce el texto con
// Tesseract.js (en esta computadora, sin costo). Al servidor va solo el texto: lo interpreta,
// une facturas de varias hojas, marca duplicados y sugiere la hoja del Excel. Después se revisa y
// se registra cada factura con el alta normal de gastos (con la página como comprobante).
const ESC = { archivos: [], filas: [], imagenes: {}, cancelado: false };
const ESC_TIPOS = ['Factura A', 'Factura B', 'Factura C', 'Tique Factura A', 'Tique Factura B', 'Tique', 'Nota de Crédito', 'Recibo', 'Comprobante'];
const ESC_HOJAS = { Oficina: 'Gtos. de Oficina', Infraestructura: 'Infraestructura', Escuela: 'Gtos. de la Escuela', Honorarios: 'Honorarios' };

function escAbrir() {
    const p = document.getElementById('esc-panel');
    p.hidden = false;
    const hoy = new Date(), ant = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
    const sm = document.getElementById('esc-mes'), sa = document.getElementById('esc-anio');
    if (!sm.options.length) {
        sm.innerHTML = MESES.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('');
        for (let a = hoy.getFullYear(); a >= hoy.getFullYear() - 1; a--) sa.innerHTML += `<option>${a}</option>`;
        sm.value = ant.getMonth() + 1; sa.value = ant.getFullYear();
        const zona = document.getElementById('esc-zona');
        ['dragenter', 'dragover'].forEach(ev => zona.addEventListener(ev, e => { e.preventDefault(); zona.classList.add('sobre'); }));
        ['dragleave', 'drop'].forEach(ev => zona.addEventListener(ev, () => zona.classList.remove('sobre')));
        zona.addEventListener('drop', e => {
            e.preventDefault();
            document.getElementById('esc-archivos').files = e.dataTransfer.files;
            escElegidos();
        });
    }
    p.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function escCerrar() {
    if (ESC.filas.some(f => f.sel && !f.ok) && !confirm('Hay facturas leídas sin registrar. ¿Cerrar igual?')) return;
    ESC.cancelado = true;
    document.getElementById('esc-panel').hidden = true;
}

function escElegidos() {
    const fs = [...document.getElementById('esc-archivos').files].filter(f => /pdf$/i.test(f.type) || /\.pdf$/i.test(f.name));
    ESC.archivos = fs;
    document.getElementById('esc-zona-txt').textContent = fs.length ? fs.map(f => f.name).join(', ') : 'Elegí el PDF escaneado';
    document.getElementById('esc-leer').disabled = !fs.length;
}

function escCancelar() { ESC.cancelado = true; }

function escEstado(txt, frac) {
    document.getElementById('esc-estado').textContent = txt;
    if (frac != null) document.getElementById('esc-barra').style.width = Math.round(frac * 100) + '%';
}

async function escCargarTesseract() {
    if (window.Tesseract) return;
    await new Promise((ok, mal) => {
        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
        s.onload = ok; s.onerror = () => mal(new Error('No se pudo cargar el lector de texto. Revisá la conexión a internet.'));
        document.head.appendChild(s);
    });
}

async function escLeer() {
    if (!ESC.archivos.length) return;
    if (typeof pdfjsLib === 'undefined') return toast('No se pudo cargar el lector de PDF. Recargá la página.', 'error');
    const anio = +document.getElementById('esc-anio').value, mes = +document.getElementById('esc-mes').value;
    ESC.cancelado = false; ESC.filas = []; ESC.imagenes = {};
    document.getElementById('esc-paso1').hidden = true;
    document.getElementById('esc-resultado').hidden = true;
    document.getElementById('esc-progreso').hidden = false;
    let worker = null;
    try {
        const docs = [];
        for (const f of ESC.archivos) docs.push({ f, pdf: await pdfjsLib.getDocument({ data: await f.arrayBuffer() }).promise });
        const total = docs.reduce((s, d) => s + d.pdf.numPages, 0);
        escEstado('Preparando el lector de texto (la primera vez descarga unos 15 MB)…', 0.01);
        await escCargarTesseract();
        worker = await Promise.race([Tesseract.createWorker('spa', 1),
            new Promise((_, mal) => setTimeout(() => mal(new Error('El lector de texto no respondió. Revisá la conexión y probá de nuevo.')), 120000))]);
        let hechas = 0, n = 0;
        const t0 = Date.now();
        const cv = document.createElement('canvas');
        const ctx = cv.getContext('2d', { willReadFrequently: true });
        for (const d of docs) {
            const paginas = [];
            for (let i = 1; i <= d.pdf.numPages; i++) {
                if (ESC.cancelado) throw new Error('cancelado');
                n++;
                const resta = hechas ? Math.round((Date.now() - t0) / hechas * (total - hechas) / 1000) : null;
                escEstado(`Leyendo la página ${hechas + 1} de ${total}${resta ? ` · faltan unos ${resta > 90 ? Math.round(resta / 60) + ' min' : resta + ' s'}` : ''}…`, hechas / total);
                const page = await d.pdf.getPage(i);
                const vp = page.getViewport({ scale: Math.min(4, 1654 / page.getViewport({ scale: 1 }).width) });  // ~200 ppp
                cv.width = Math.round(vp.width); cv.height = Math.round(vp.height);
                ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, cv.width, cv.height);
                // intent 'print': dibuja aunque la pestaña quede en segundo plano (el modo pantalla se pausa)
                await page.render({ canvasContext: ctx, viewport: vp, intent: 'print' }).promise;
                const qr = _jsQRdesdeFuente(cv, cv.width, cv.height);
                const { data } = await worker.recognize(cv);
                ESC.imagenes[n] = { url: escMiniatura(cv), archivo: d.f.name, pagina: i };
                paginas.push({ n, texto: (data.text || '').slice(0, 30000), qr });
                hechas++;
            }
            escEstado(`Interpretando las facturas de ${d.f.name}…`, hechas / total);
            const r = await api('/api/escaneo-facturas/analizar', { method: 'POST', body: JSON.stringify({ archivo: d.f.name, anio, mes, paginas }) });
            r.facturas.forEach(f => ESC.filas.push(escFila(f, d.f.name)));
        }
        escPintar();
    } catch (e) {
        if (e.message !== 'cancelado') toast(e.message || 'No se pudo leer el PDF', 'error');
        document.getElementById('esc-paso1').hidden = false;
    } finally {
        if (worker) worker.terminate().catch(() => {});
        document.getElementById('esc-progreso').hidden = true;
    }
}

function escMiniatura(cv) {
    const ancho = 1100, f = Math.min(1, ancho / cv.width);
    const c = document.createElement('canvas');
    c.width = Math.round(cv.width * f); c.height = Math.round(cv.height * f);
    c.getContext('2d').drawImage(cv, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.72);
}

function escFila(f, archivo) {
    const d = f.datos, s = f.sugerencia || {};
    const esFactura = f.tipo_pagina === 'factura';
    return {
        paginas: f.paginas, archivo, tipo_pagina: f.tipo_pagina, nota: f.nota, con_qr: f.con_qr,
        duplicado: f.duplicado, repetida: f.repetida_en_pdf, fuera: f.fuera_del_mes,
        faltan: f.faltan, dudosos: f.dudosos, fuentes: f.fuentes,
        sel: esFactura && !f.duplicado && !f.repetida_en_pdf,
        v: {
            fecha: d.fecha || '', tipo: d.tipo || '', punto_venta: d.punto_venta || '', numero: d.numero || '',
            cuit: d.cuit || '', razon_social: d.razon_social || '', importe: d.importe != null ? fmtNumero(Math.abs(d.importe)) : '',
            concepto: '', rubro: s.rubro || '', categoria: s.categoria || '',
        },
        concepto_sug: s.concepto || '', ok: false, error: null,
    };
}

function escPintar() {
    const fs = ESC.filas;
    const nFact = fs.filter(f => f.tipo_pagina === 'factura').length;
    const completas = fs.filter(f => f.tipo_pagina === 'factura' && !f.faltan.length).length;
    const dups = fs.filter(f => f.duplicado || f.repetida).length, otras = fs.filter(f => f.tipo_pagina !== 'factura').length;
    const caja = document.getElementById('esc-resultado');
    caja.hidden = false;
    caja.innerHTML = `
        <div class="imp-resumen esc-resumen">
            <div><b>${nFact}</b><span>facturas encontradas</span></div>
            <div><b>${completas}</b><span>con todos los datos</span></div>
            <div><b>${fs.filter(f => f.con_qr).length}</b><span>con QR de AFIP (exactas)</span></div>
            <div class="${dups || otras ? 'alerta' : ''}"><b>${dups + otras}</b><span>duplicadas o que no son facturas</span></div>
        </div>
        <p class="muted esc-leyenda"><span class="esc-c esc-dudoso"></span> dato corregido o calculado: revisalo ·
            <span class="esc-c esc-falta"></span> no se pudo leer · Tocá la imagen para verla grande.</p>
        <div class="esc-lista">${fs.map((f, i) => escItem(f, i)).join('')}</div>
        <div class="esc-pie">
            <span class="muted" id="esc-cuenta"></span>
            <button type="button" class="btn btn-outline" onclick="escOtroPdf()">Leer otro PDF</button>
            <button type="button" class="btn btn-primary btn-3d" id="esc-registrar" onclick="escRegistrar()"><svg class="ic"><use href="#i-check"/></svg>Registrar</button>
        </div>`;
    escContar();
    caja.querySelectorAll('[data-i]').forEach(el => el.addEventListener('input', escCambio));
    caja.querySelectorAll('select[data-i], input[type=checkbox][data-i]').forEach(el => el.addEventListener('change', escCambio));
}

function escItem(f, i) {
    const img = ESC.imagenes[f.paginas[0]];
    const cls = c => f.faltan.includes({ cuit: 'CUIT', fecha: 'fecha', numero: 'número', importe: 'total' }[c]) ? 'esc-falta' : f.dudosos.includes(c) ? 'esc-dudoso' : '';
    const campo = (c, label, extra = '') => `<div class="esc-f ${extra}"><label>${label}</label><input type="text" data-i="${i}" data-c="${c}" value="${escapeHtml(f.v[c])}" class="${cls(c)}"></div>`;
    const badges = [
        f.con_qr ? '<span class="badge badge-activa">QR de AFIP</span>' : '<span class="badge">Leída por OCR</span>',
        f.duplicado ? `<span class="badge badge-pdx-no">Ya está cargada (${fmtFecha(f.duplicado.fecha)}, ${fmtMoneda(f.duplicado.importe)})</span>` : '',
        f.repetida ? `<span class="badge badge-pdx-no">Repetida en el PDF (igual a la pág. ${f.repetida})</span>` : '',
        f.tipo_pagina !== 'factura' ? `<span class="badge badge-sin">${f.tipo_pagina === 'vacia' ? 'Página en blanco' : 'No parece una factura'}</span>` : '',
        f.fuera ? '<span class="badge badge-sin">Fecha de otro mes</span>' : '',
        f.nota ? `<span class="badge">${escapeHtml(f.nota)}</span>` : '',
    ].join(' ');
    return `<div class="esc-item ${f.sel ? '' : 'esc-off'} ${f.ok ? 'esc-ok' : ''}" id="esc-it-${i}">
        <button type="button" class="esc-mini" onclick="escVerImagen(${i})" aria-label="Ver la página ${f.paginas.join(', ')} en grande">
            ${img ? `<img src="${img.url}" alt="" loading="lazy">` : ''}<small>Pág. ${f.paginas.join('-')}</small></button>
        <div class="esc-cuerpo">
            <div class="esc-top"><label class="ps-check"><input type="checkbox" data-i="${i}" data-c="sel" ${f.sel ? 'checked' : ''} ${f.ok ? 'disabled' : ''}> Registrar</label>
                ${badges}<span class="esc-msg" id="esc-msg-${i}">${f.ok ? '✓ Registrada' : f.error ? escapeHtml(f.error) : ''}</span></div>
            <div class="esc-campos">
                <div class="esc-f"><label>Fecha</label><input type="date" data-i="${i}" data-c="fecha" value="${f.v.fecha}" class="${cls('fecha')}"></div>
                <div class="esc-f"><label>Tipo</label><input type="text" list="esc-tipos" data-i="${i}" data-c="tipo" value="${escapeHtml(f.v.tipo)}"></div>
                ${campo('punto_venta', 'Pto. venta', 'esc-corto')}${campo('numero', 'Número')}
                ${campo('cuit', 'CUIT')}${campo('razon_social', 'Razón social', 'esc-ancho')}
                ${campo('importe', 'Total $')}
                <div class="esc-f"><label>Hoja del Excel</label><select data-i="${i}" data-c="categoria" class="${f.v.categoria ? '' : 'esc-vacio'}"><option value="">— elegir —</option>
                    ${Object.entries(ESC_HOJAS).map(([k, t]) => `<option value="${k}" ${f.v.categoria === k ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
                <div class="esc-f esc-ancho"><label>Concepto</label><input type="text" data-i="${i}" data-c="concepto" value="${escapeHtml(f.v.concepto)}" placeholder="${escapeHtml(f.concepto_sug || 'Qué se compró')}"></div>
                ${campo('rubro', 'Rubro')}
            </div>
        </div>
    </div>`;
}

function escCambio(e) {
    const el = e.target, f = ESC.filas[+el.dataset.i], c = el.dataset.c;
    if (c === 'sel') { f.sel = el.checked; el.closest('.esc-item').classList.toggle('esc-off', !f.sel); escContar(); return; }
    f.v[c] = el.value;
    el.classList.remove('esc-dudoso', 'esc-falta', 'esc-vacio');
}

function escContar() {
    const n = ESC.filas.filter(f => f.sel && !f.ok).length;
    const total = ESC.filas.filter(f => f.sel && !f.ok).reduce((s, f) => s + (parseImporte(f.v.importe) || 0), 0);
    document.getElementById('esc-cuenta').innerHTML = n ? `<b>${n}</b> factura${n === 1 ? '' : 's'} para registrar · ${fmtMoneda(total)}` : 'No hay facturas elegidas.';
    const b = document.getElementById('esc-registrar');
    b.disabled = !n;
    b.innerHTML = `<svg class="ic"><use href="#i-check"/></svg>Registrar ${n} factura${n === 1 ? '' : 's'}`;
}

function escVerImagen(i) {
    const f = ESC.filas[i];
    document.getElementById('modal-content').innerHTML = `<h3 style="margin-top:0">${escapeHtml(f.archivo)} · página ${f.paginas.join(' y ')}</h3>
        <div class="esc-grande">${f.paginas.map(n => ESC.imagenes[n] ? `<img src="${ESC.imagenes[n].url}" alt="Página ${n}">` : '').join('')}</div>`;
    const ov = document.getElementById('modal-overlay');
    ov.querySelector('.modal').classList.add('modal-ancho');
    ov.style.display = 'flex';
}

function escOtroPdf() {
    if (ESC.filas.some(f => f.sel && !f.ok) && !confirm('Hay facturas leídas sin registrar. ¿Leer otro PDF igual?')) return;
    ESC.filas = []; ESC.imagenes = {};
    document.getElementById('esc-resultado').hidden = true;
    document.getElementById('esc-paso1').hidden = false;
    document.getElementById('esc-archivos').value = '';
    escElegidos();
}

async function escRegistrar() {
    const pendientes = ESC.filas.map((f, i) => ({ f, i })).filter(x => x.f.sel && !x.f.ok);
    const btn = document.getElementById('esc-registrar');
    btn.disabled = true;
    let bien = 0, mal = 0;
    for (const { f, i } of pendientes) {
        const msg = document.getElementById('esc-msg-' + i);
        const importe = parseImporte(f.v.importe);
        if (!f.v.fecha || !(importe > 0)) {
            f.error = 'Falta la fecha o el total'; msg.textContent = f.error; msg.className = 'esc-msg error'; mal++; continue;
        }
        if (!f.v.razon_social.trim()) {
            f.error = 'Falta la razón social'; msg.textContent = f.error; msg.className = 'esc-msg error'; mal++; continue;
        }
        msg.textContent = 'Registrando…'; msg.className = 'esc-msg';
        let adjunto = null;
        const img = ESC.imagenes[f.paginas[0]];
        if (img) {
            try {
                const blob = await (await fetch(img.url)).blob();
                adjunto = await subirComprobante(new File([blob], `factura_${(f.v.cuit || 'escaneada')}_${f.v.numero || f.paginas[0]}.jpg`, { type: 'image/jpeg' }));
            } catch { /* sin Storage: se registra igual, sin la imagen */ }
        }
        const nc = /cr[eé]dito/i.test(f.v.tipo);
        const body = {
            fecha: f.v.fecha, tipo_comprobante: f.v.tipo || null, punto_venta: f.v.punto_venta || null, numero: f.v.numero || null,
            cuit: f.v.cuit || null, razon_social: f.v.razon_social || null, importe: nc ? -Math.abs(importe) : importe,
            concepto: f.v.concepto || null, rubro: f.v.rubro || null, categoria: f.v.categoria || null, adjunto_url: adjunto,
            notas: `Cargada desde ${f.archivo} (pág. ${f.paginas.join('-')})`.slice(0, 400),
        };
        try {
            await api('/api/gastos/', { method: 'POST', body: JSON.stringify(body) });
            f.ok = true; f.error = null; bien++;
            msg.textContent = '✓ Registrada'; msg.className = 'esc-msg ok';
            const it = document.getElementById('esc-it-' + i);
            it.classList.add('esc-ok');
            it.querySelector('input[data-c=sel]').disabled = true;
        } catch (e) {
            f.error = e.message; msg.textContent = e.message; msg.className = 'esc-msg error'; mal++;
        }
    }
    escContar();
    toast(`${bien} factura${bien === 1 ? '' : 's'} registrada${bien === 1 ? '' : 's'}${mal ? ` · ${mal} con problemas (revisalas)` : ''}`, mal ? 'error' : 'success');
    proveedoresCache = [];
    cargarGastos();
}

// =========================================================
// --- AVISO DE VERSIÓN NUEVA ---
// =========================================================
// Si se publica una actualización con la pantalla abierta, el código viejo sigue en memoria
// (botones que ya no coinciden con el servidor). Se compara la versión cada tanto y al volver a la pestaña.
let _versionInicial = null;
async function revisarVersion() {
    try {
        const v = (await (await fetch('/api/version', { cache: 'no-store' })).json()).version;
        if (!_versionInicial) { _versionInicial = v; return; }
        if (v !== _versionInicial && !document.getElementById('aviso-version')) {
            const d = document.createElement('div');
            d.id = 'aviso-version';
            d.className = 'aviso-version';
            d.setAttribute('role', 'status');
            d.innerHTML = `<span><b>Hay una versión nueva del sistema.</b> Recargá para usarla.</span>
                <button type="button" class="btn btn-primary btn-sm" onclick="location.reload()">Recargar</button>`;
            document.body.appendChild(d);
        }
    } catch { /* sin conexión: se vuelve a probar después */ }
}
revisarVersion();
setInterval(revisarVersion, 5 * 60 * 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) revisarVersion(); });

// =========================================================
// --- COMPRAS POR UN ENCARGADO (rendición de transferencias) ---
// =========================================================
// El banco no le paga al proveedor sino a la persona que compró (reintegro o adelanto): la transferencia
// se vincula con una o varias facturas de cualquier proveedor, a nombre de APAI.
let REND = { mov: null, data: null, encargados: [], sel: new Set() };

async function abrirEncargados() {
    let lista = [];
    try { lista = await api('/api/conciliacion/encargados'); } catch (e) { return toast(e.message, 'error'); }
    document.getElementById('modal-content').innerHTML = `
        <h2 style="margin-top:0">Encargados de compras</h2>
        <p class="muted" style="margin-top:-0.4rem">Personas que compran para APAI (administración, profesores) y a las que se les transfiere desde el
        banco, para reintegrarles lo que pagaron o como adelanto. Con el CUIT/CUIL, sus transferencias se reconocen solas en la conciliación.</p>
        <table class="rend-enc"><thead><tr><th>Nombre</th><th>CUIT / CUIL</th><th>Activo</th><th></th></tr></thead><tbody>
        ${lista.map(e => `<tr><td><input type="text" id="enc-n-${e.id}" value="${escapeHtml(e.nombre)}" aria-label="Nombre"></td>
            <td><input type="text" id="enc-c-${e.id}" value="${escapeHtml(e.cuit || '')}" inputmode="numeric" placeholder="Sin CUIT" aria-label="CUIT"></td>
            <td><input type="checkbox" id="enc-a-${e.id}" ${e.activo ? 'checked' : ''} aria-label="Activo"></td>
            <td class="rend-acc"><button class="btn btn-sm" onclick="guardarEncargado(${e.id})">Guardar</button>
                <button class="btn btn-sm btn-ghost" onclick="borrarEncargado(${e.id})" aria-label="Eliminar"><svg class="ic"><use href="#i-trash"/></svg></button></td></tr>`).join('')
        || '<tr><td colspan="4" class="muted">Todavía no hay encargados cargados.</td></tr>'}
        <tr class="rend-nuevo"><td><input type="text" id="enc-n-0" placeholder="Nombre y apellido" aria-label="Nombre del encargado nuevo"></td>
            <td><input type="text" id="enc-c-0" placeholder="CUIT/CUIL" inputmode="numeric" aria-label="CUIT del encargado nuevo"></td>
            <td></td><td><button class="btn btn-sm btn-primary" onclick="guardarEncargado(0)"><svg class="ic"><use href="#i-plus"/></svg>Agregar</button></td></tr>
        </tbody></table>`;
    const ov = document.getElementById('modal-overlay');
    ov.querySelector('.modal').classList.add('modal-ancho');
    ov.style.display = 'flex';
}

async function guardarEncargado(id) {
    const body = { nombre: document.getElementById('enc-n-' + id).value, cuit: document.getElementById('enc-c-' + id).value || null,
        activo: id ? document.getElementById('enc-a-' + id).checked : true };
    try {
        await api('/api/conciliacion/encargados' + (id ? '/' + id : ''), { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) });
        toast(id ? 'Encargado actualizado' : 'Encargado agregado');
        abrirEncargados();
        cargarConciliacion();
    } catch (e) { toast(e.message, 'error'); }
}

async function borrarEncargado(id) {
    if (!confirm('¿Eliminar este encargado?')) return;
    try { toast((await api('/api/conciliacion/encargados/' + id, { method: 'DELETE' })).mensaje); abrirEncargados(); }
    catch (e) { toast(e.message, 'error'); }
}

function htmlEstadoRendicion(m) {
    const r = m.rendicion;
    const quien = r.encargado ? escapeHtml(r.encargado.nombre) : 'encargado';
    if (m.conciliado) {
        return `<span class="conc-ok">✓ rendida</span> vía <b>${quien}</b>
            <span style="color:var(--text-muted)">· ${r.facturas} factura${r.facturas === 1 ? '' : 's'}${r.cerrada ? ' · cerrada con nota' : ''}</span>`;
    }
    return `<span class="conc-pend rend-pend">● a rendir</span> <b>${quien}</b>
        <span style="color:var(--text-muted)">· rendido ${fmtMoneda(r.rendido)} · falta ${fmtMoneda(r.saldo)}</span>`;
}

async function abrirRendicion(movId) {
    try {
        const [data, encargados] = await Promise.all([api(`/api/conciliacion/${movId}/rendicion`), api('/api/conciliacion/encargados')]);
        REND = { mov: movId, data, encargados: encargados.filter(e => e.activo || (data.encargado && e.id === data.encargado.id)), sel: new Set() };
        pintarRendicion();
        const ov = document.getElementById('modal-overlay');
        ov.querySelector('.modal').classList.add('modal-ancho');
        ov.style.display = 'flex';
    } catch (e) { toast(e.message, 'error'); }
}

function pintarRendicion() {
    const d = REND.data, m = d.movimiento;
    const q = normTxt((document.getElementById('rend-buscar') || {}).value || '');
    const disp = d.disponibles.filter(g => !q || normTxt([g.razon_social, g.concepto, g.numero, g.cuit].join(' ')).includes(q));
    const sumaSel = d.disponibles.filter(g => REND.sel.has(g.id)).reduce((s, g) => s + g.importe, 0);
    const saldoTras = d.saldo - sumaSel;
    const encSel = (document.getElementById('rend-enc') || {}).value || (d.encargado ? d.encargado.id : '');
    document.getElementById('modal-content').innerHTML = `
        <h2 style="margin-top:0">Rendición de una transferencia a un encargado</h2>
        <p class="muted" style="margin-top:-0.4rem">${fmtFecha(m.fecha)} · ${escapeHtml(m.razon_social || m.descripcion || '')}${m.cuit ? ' · CUIT ' + escapeHtml(m.cuit) : ''}</p>
        <div class="rend-cab">
            <div><label for="rend-enc">Encargado que compró</label>
                <select id="rend-enc"><option value="">— elegir —</option>${REND.encargados.map(e => `<option value="${e.id}" ${String(e.id) === String(encSel) ? 'selected' : ''}>${escapeHtml(e.nombre)}</option>`).join('')}</select>
                <button type="button" class="btn btn-link btn-sm" onclick="cerrarModal();abrirEncargados()">Cargar o editar encargados</button></div>
            <div class="rend-nums">
                <div><span>Transferido</span><b>${fmtMoneda(d.transferido)}</b></div>
                <div><span>Rendido</span><b>${fmtMoneda(d.rendido)}</b></div>
                <div class="${Math.abs(d.saldo) > 1 ? 'rend-falta' : 'rend-ok'}"><span>${d.saldo >= 0 ? 'Falta rendir' : 'Se le debe al encargado'}</span><b>${fmtMoneda(Math.abs(d.saldo))}</b></div>
            </div>
        </div>
        ${d.cerrada ? `<p class="ps-aviso">Dada por rendida: ${escapeHtml(d.nota || '')} <button class="btn btn-sm" onclick="cerrarRendicion(false)">Reabrir</button></p>` : ''}
        <h4 style="margin:0.8rem 0 0.3rem">Facturas rendidas con esta transferencia</h4>
        <table class="rend-tabla"><tbody>${d.vinculadas.map(g => `<tr><td>${fmtFecha(g.fecha)}</td><td><b>${escapeHtml(g.razon_social || '—')}</b>
            <br><small class="muted">${escapeHtml([g.tipo, g.numero, g.concepto].filter(Boolean).join(' · '))}</small></td>
            <td class="num">${fmtMoneda(g.importe)}</td><td><button class="btn btn-sm btn-ghost" onclick="quitarDeRendicion(${g.id})">Quitar</button></td></tr>`).join('')
            || '<tr><td colspan="4" class="muted">Todavía ninguna. Elegí abajo las facturas que se pagaron con esta plata.</td></tr>'}</tbody></table>
        <div class="rend-disp-cab"><h4 style="margin:0">Facturas sin pagar</h4>
            <input type="search" id="rend-buscar" placeholder="Buscar proveedor, concepto o número…" oninput="pintarRendicion()" value="${escapeHtml((document.getElementById('rend-buscar') || {}).value || '')}"></div>
        <div class="rend-disp"><table class="rend-tabla"><tbody>${disp.map(g => `<tr class="${REND.sel.has(g.id) ? 'rend-sel' : ''}">
            <td><input type="checkbox" ${REND.sel.has(g.id) ? 'checked' : ''} onchange="rendSel(${g.id}, this.checked)" aria-label="Elegir"></td>
            <td>${fmtFecha(g.fecha)}</td><td><b>${escapeHtml(g.razon_social || '—')}</b><br><small class="muted">${escapeHtml([g.tipo, g.numero, g.concepto].filter(Boolean).join(' · '))}</small></td>
            <td class="num">${fmtMoneda(g.importe)}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">No hay facturas sin pagar' + (q ? ' con esa búsqueda' : '') + '. Cargala primero en Gastos.</td></tr>'}</tbody></table></div>
        <div class="form-actions rend-pie">
            <span class="muted">${REND.sel.size ? `${REND.sel.size} elegida${REND.sel.size === 1 ? '' : 's'} · ${fmtMoneda(sumaSel)} · después ${saldoTras >= 0 ? 'falta' : 'sobra'} ${fmtMoneda(Math.abs(saldoTras))}` : ''}</span>
            <span style="flex:1"></span>
            ${!d.cerrada && d.vinculadas.length && Math.abs(d.saldo) > 1 ? '<button class="btn btn-outline" onclick="cerrarRendicion(true)">Dar por rendida…</button>' : ''}
            <button class="btn btn-primary" onclick="confirmarRendicion()" ${REND.sel.size ? '' : 'disabled'}>Vincular ${REND.sel.size || ''} factura${REND.sel.size === 1 ? '' : 's'}</button>
        </div>`;
    const b = document.getElementById('rend-buscar');
    if (q && b) { b.focus(); b.setSelectionRange(b.value.length, b.value.length); }
}

function rendSel(id, on) { on ? REND.sel.add(id) : REND.sel.delete(id); pintarRendicion(); }

async function confirmarRendicion() {
    const enc = document.getElementById('rend-enc').value;
    if (!enc) return toast('Elegí el encargado que hizo la compra', 'error');
    try {
        await api(`/api/conciliacion/${REND.mov}/rendicion`, { method: 'POST', body: JSON.stringify({ encargado_id: +enc, gasto_ids: [...REND.sel] }) });
        toast('Facturas vinculadas a la transferencia');
        await abrirRendicion(REND.mov);
        cargarConciliacion();
    } catch (e) { toast(e.message, 'error'); }
}

async function quitarDeRendicion(gastoId) {
    if (!confirm('¿Quitar esta factura de la rendición? Vuelve a quedar sin pagar.')) return;
    try { await api(`/api/conciliacion/${REND.mov}/rendicion/${gastoId}`, { method: 'DELETE' }); await abrirRendicion(REND.mov); cargarConciliacion(); }
    catch (e) { toast(e.message, 'error'); }
}

async function cerrarRendicion(cerrar) {
    let nota = null;
    if (cerrar) {
        nota = prompt('¿Por qué se da por rendida? (ej.: devolvió el vuelto en efectivo, se le debe la diferencia)');
        if (!nota) return;
    }
    try {
        await api(`/api/conciliacion/${REND.mov}/rendicion/cerrar`, { method: 'POST', body: JSON.stringify({ cerrar, nota }) });
        await abrirRendicion(REND.mov);
        cargarConciliacion();
    } catch (e) { toast(e.message, 'error'); }
}

// Desde Gastos: la factura se pagó con una transferencia a un encargado
async function pagoPorEncargado(gastoId, movId, encId) {
    try {
        await api(`/api/conciliacion/${movId}/rendicion`, { method: 'POST', body: JSON.stringify({ encargado_id: encId, gasto_ids: [gastoId] }) });
        toast('Factura vinculada a la transferencia al encargado');
        cerrarModal();
        cargarGastos();
    } catch (e) { toast(e.message, 'error'); }
}
