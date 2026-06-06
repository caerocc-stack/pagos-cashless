const API = '';
let alumnosCache = [];

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
                    <span class="buscador-nombre">${a.apellido}, ${a.nombre}</span>
                    <span class="buscador-detalle"> - ${a.legajo} - ${a.curso}</span>
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
    filtrarAlumnos();
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
            <td>${a.legajo}</td>
            <td>${a.dni}</td>
            <td>${a.apellido}</td>
            <td>${a.nombre}</td>
            <td>${a.curso}</td>
            <td class="${clsSaldo}">$${saldo.toLocaleString('es-AR', {minimumFractionDigits: 2})}</td>
            <td>
                <button class="btn btn-sm" onclick="verAlumno(${a.id})">Ver</button>
                <button class="btn btn-sm" onclick="editarAlumno(${a.id})">Editar</button>
                <button class="btn btn-sm btn-danger" onclick="eliminarAlumno(${a.id}, '${a.apellido}, ${a.nombre}')">Eliminar</button>
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
    ['al-legajo', 'al-dni', 'al-nombre', 'al-apellido', 'al-curso', 'al-email'].forEach(id =>
        document.getElementById(id).value = ''
    );
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

async function eliminarAlumno(id, nombre) {
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

async function verAlumno(id) {
    try {
        const a = await api(`/api/alumnos/${id}`);
        const movs = await api(`/api/operaciones/historial/${id}?limite=10`);
        const tarjetas = await api(`/api/tarjetas/alumno/${id}`);

        let html = `<h3>${a.apellido}, ${a.nombre}</h3>
            <p><strong>Legajo:</strong> ${a.legajo} | <strong>DNI:</strong> ${a.dni} | <strong>Curso:</strong> ${a.curso}</p>
            <p><strong>Email:</strong> ${a.email || '<span style="color:#94a3b8">sin email</span>'} | <strong>Cód. SIRO:</strong> ${a.codigo_siro || '-'}</p>
            <p style="font-size:1.5rem;margin:1rem 0" class="saldo-positivo"><strong>Saldo: $${Number(a.saldo).toLocaleString('es-AR', {minimumFractionDigits:2})}</strong></p>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:1rem">
                <button class="btn btn-red btn-sm" onclick="generarPDFAlumno(${a.id})">📄 PDF para padres</button>
                <button class="btn btn-success btn-sm" onclick="compartirWhatsAppAlumno(${a.id})">Compartir WhatsApp</button>
                <button class="btn btn-outline btn-sm" onclick="compartirEmailAlumno(${a.id})">Enviar por Email</button>
            </div>`;

        html += '<h4>Tarjetas</h4>';
        if (tarjetas.length === 0) {
            html += '<p style="color:#94a3b8">Sin tarjetas asignadas</p>';
        } else {
            html += tarjetas.map(t =>
                `<span class="badge ${t.activa ? 'badge-activa' : 'badge-inactiva'}">${t.uid} — ${t.activa ? 'Activa' : 'Inactiva'}</span> `
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
                    <td class="tipo-${m.tipo}">${m.tipo}</td>
                    <td class="${monto >= 0 ? 'saldo-positivo' : ''}" style="${monto < 0 ? 'color:#ef4444' : ''}">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
                    <td>${m.descripcion || ''}</td>
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
                operador: document.getElementById('op-recarga-operador').value,
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
                operador: document.getElementById('op-reintegro-operador').value,
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

async function abrirConfigEmail() {
    try {
        const cfg = await api('/api/config/email');
        const lbl = 'display:block;margin-bottom:0.25rem;font-size:0.85rem;color:#5b6b80;font-weight:500';
        const inp = 'width:100%;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:0.75rem';
        const html = `
            <h3>Mensaje del email del cupón</h3>
            <p style="color:#5b6b80;font-size:0.85rem;margin-bottom:0.75rem">
                Podés usar estos comodines (se reemplazan solos): <br>
                <code>{alumno}</code> <code>{nombre}</code> <code>{apellido}</code>
                <code>{monto}</code> <code>{legajo}</code> <code>{curso}</code>
            </p>
            <label style="${lbl}">Asunto</label>
            <input type="text" id="cfg-asunto" style="${inp}" value="${(cfg.asunto || '').replace(/"/g, '&quot;')}">
            <label style="${lbl}">Mensaje</label>
            <textarea id="cfg-mensaje" style="${inp};min-height:200px;font-family:inherit;resize:vertical">${cfg.mensaje || ''}</textarea>
            <button class="btn btn-primary" style="width:100%" onclick="guardarConfigEmail()">Guardar mensaje</button>`;
        document.getElementById('modal-content').innerHTML = html;
        document.getElementById('modal-overlay').style.display = 'flex';
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function guardarConfigEmail() {
    const asunto = document.getElementById('cfg-asunto').value.trim();
    const mensaje = document.getElementById('cfg-mensaje').value.trim();
    if (!asunto || !mensaje) return toast('Completá el asunto y el mensaje', 'error');
    try {
        const res = await api('/api/config/email', {
            method: 'POST',
            body: JSON.stringify({ asunto, mensaje }),
        });
        toast(res.mensaje);
        cerrarModal();
    } catch (err) {
        toast(err.message, 'error');
    }
}

async function enviarCupon(e) {
    e.preventDefault();
    const alumnoId = document.getElementById('cupon-alumno').value;
    const monto = parseFloat(document.getElementById('cupon-monto').value);
    const div = document.getElementById('cupon-resultado');
    if (!alumnoId) return toast('Seleccioná un alumno', 'error');
    if (!monto || monto <= 0) return toast('Ingresá un monto válido', 'error');
    try {
        const res = await api('/api/cupones/recarga', {
            method: 'POST',
            body: JSON.stringify({ alumno_id: parseInt(alumnoId), monto }),
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

async function ejecutarTransferencia(e) {
    e.preventDefault();
    try {
        const res = await api('/api/operaciones/transferencia', {
            method: 'POST',
            body: JSON.stringify({
                uid_origen: document.getElementById('op-transf-origen').value,
                uid_destino: document.getElementById('op-transf-destino').value,
                monto: parseFloat(document.getElementById('op-transf-monto').value),
                operador: document.getElementById('op-transf-operador').value,
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
        const alumno = m.apellido ? `${m.apellido}, ${m.nombre}` : '';
        return `<tr>
            <td>${fecha}</td>
            <td>${alumno}</td>
            <td>${m.curso || ''}</td>
            <td class="tipo-${m.tipo}">${m.tipo}</td>
            <td style="color:${monto >= 0 ? '#16a34a' : '#a01e22'};font-weight:600">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
            <td>${m.descripcion || ''}</td>
            <td>${m.operador || ''}</td>
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

async function cobroEjecutar() {
    const uid = document.getElementById('cobro-uid-actual').value;
    const monto = parseFloat(document.getElementById('cobro-monto').value);
    const desc = document.getElementById('cobro-desc').value;
    const operador = document.getElementById('cobro-operador').value;

    if (!monto || monto <= 0) return toast('Ingresa un monto valido', 'error');
    if (!operador) return toast('Ingresa el nombre del operador', 'error');

    if (!uid) {
        toast('Este alumno no tiene tarjeta asociada. Usa la seccion Tarjetas para emitir una.', 'error');
        return;
    }

    try {
        const res = await api('/api/operaciones/cobro', {
            method: 'POST',
            body: JSON.stringify({ uid, monto, descripcion: desc, operador }),
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
    const inp = 'width:100%;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:0.75rem';
    const lbl = 'display:block;margin-bottom:0.25rem;font-size:0.85rem;color:#5b6b80;font-weight:500';
    const html = `
        <h3>Mi cuenta</h3>

        <div style="background:#f7f9fc;border-radius:10px;padding:1rem;margin-bottom:1.25rem">
            <p style="font-weight:600;color:#15233b;margin-bottom:0.75rem">Datos de la cuenta</p>
            <label style="${lbl}">Nombre para mostrar</label>
            <input type="text" id="mc-nombre" style="${inp}" value="${(usuarioActual.nombre || '').replace(/"/g, '&quot;')}">
            <label style="${lbl}">Nombre de usuario (para iniciar sesión)</label>
            <input type="text" id="mc-username" style="${inp}" value="${(usuarioActual.username || '').replace(/"/g, '&quot;')}" autocomplete="off">
            <small style="color:#94a3b8">Con este usuario vas a entrar la próxima vez.</small>
            <button class="btn btn-primary" style="width:100%;margin-top:0.75rem" onclick="guardarCuenta()">Guardar datos</button>
        </div>

        <div style="background:#f7f9fc;border-radius:10px;padding:1rem;margin-bottom:1.25rem">
            <p style="font-weight:600;color:#15233b;margin-bottom:0.75rem">Cambiar contraseña</p>
            <label style="${lbl}">Contraseña actual</label>
            <input type="password" id="cp-actual" style="${inp}" autocomplete="off">
            <label style="${lbl}">Contraseña nueva</label>
            <input type="password" id="cp-nueva" style="${inp}" autocomplete="off">
            <label style="${lbl}">Repetir contraseña nueva</label>
            <input type="password" id="cp-repetir" style="${inp}" autocomplete="off">
            <button class="btn btn-primary" style="width:100%" onclick="guardarPassword()">Cambiar contraseña</button>
        </div>

        <div style="background:#f7f9fc;border-radius:10px;padding:1rem">
            <p style="font-weight:600;color:#15233b;margin-bottom:0.75rem">Probar envío de email</p>
            <label style="${lbl}">Enviar un email de prueba a</label>
            <input type="email" id="te-destino" style="${inp}" placeholder="tucorreo@ejemplo.com" autocomplete="off">
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

// --- INIT ---
cargarUsuario();
cargarAlumnos();
cargarMovimientosGenerales();
