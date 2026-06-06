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
            </td>
        </tr>`;
    }).join('');
}

document.getElementById('buscar-alumno').addEventListener('input', filtrarAlumnos);
document.getElementById('filtro-curso').addEventListener('change', filtrarAlumnos);

function mostrarFormAlumno() {
    document.getElementById('form-alumno').style.display = 'block';
    document.getElementById('form-alumno-titulo').textContent = 'Nuevo Alumno';
    document.getElementById('alumno-edit-id').value = '';
    ['al-legajo', 'al-dni', 'al-nombre', 'al-apellido', 'al-curso'].forEach(id =>
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

async function verAlumno(id) {
    try {
        const a = await api(`/api/alumnos/${id}`);
        const movs = await api(`/api/operaciones/historial/${id}?limite=10`);
        const tarjetas = await api(`/api/tarjetas/alumno/${id}`);

        let html = `<h3>${a.apellido}, ${a.nombre}</h3>
            <p><strong>Legajo:</strong> ${a.legajo} | <strong>DNI:</strong> ${a.dni} | <strong>Curso:</strong> ${a.curso}</p>
            <p style="font-size:1.5rem;margin:1rem 0" class="saldo-positivo"><strong>Saldo: $${Number(a.saldo).toLocaleString('es-AR', {minimumFractionDigits:2})}</strong></p>`;

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
                const fecha = new Date(m.created_at).toLocaleString('es-AR');
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

async function cargarHistorial() {
    const alumnoId = document.getElementById('hist-alumno').value;
    if (!alumnoId) return toast('Selecciona un alumno', 'error');
    try {
        const movs = await api(`/api/operaciones/historial/${alumnoId}`);
        document.getElementById('body-historial').innerHTML = movs.map(m => {
            const fecha = new Date(m.created_at).toLocaleString('es-AR');
            const monto = Number(m.monto);
            return `<tr>
                <td>${fecha}</td>
                <td class="tipo-${m.tipo}">${m.tipo}</td>
                <td style="color:${monto >= 0 ? '#16a34a' : '#ef4444'}">$${monto.toLocaleString('es-AR', {minimumFractionDigits:2})}</td>
                <td>${m.descripcion || ''}</td>
                <td>${m.operador || ''}</td>
            </tr>`;
        }).join('') || '<tr><td colspan="5" style="text-align:center;color:#94a3b8">Sin movimientos</td></tr>';
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
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);

        const div = document.getElementById('resultado-import');
        div.style.display = 'block';
        div.innerHTML = `
            <p><strong>Alumnos creados:</strong> ${data.creados}</p>
            ${data.errores.length > 0 ? `<p><strong>Errores (${data.errores.length}):</strong></p><ul>${data.errores.map(e => `<li>${e}</li>`).join('')}</ul>` : ''}
        `;
        toast(`Importacion completa: ${data.creados} alumnos creados`);
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

// --- SESION ---
async function cargarUsuario() {
    try {
        const user = await api('/api/auth/me');
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

// --- INIT ---
cargarUsuario();
cargarAlumnos();
