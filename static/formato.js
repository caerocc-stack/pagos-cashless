// ===================================================================
//  Formatos unificados de APAI Pay
//  - Importes: $ 1.234.567,89 (es-AR), también MIENTRAS se escriben
//  - Fechas: dd/mm/aaaa (también en los campos de fecha)
//  - Horas: siempre en hora de Argentina (America/Argentina/Buenos_Aires)
// ===================================================================
const TZ_AR = 'America/Argentina/Buenos_Aires';

// ---------- fechas ----------

// "Hoy" en Argentina como AAAA-MM-DD (toISOString() da la fecha UTC: después de las 21 hs ya es mañana)
function hoyISO() { return isoDeFecha(new Date()); }

function isoDeFecha(d) {
    return new Intl.DateTimeFormat('en-CA', { timeZone: TZ_AR, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
}

// '2026-07-15' -> '15/07/2026'
function fmtFecha(iso) {
    if (!iso) return '-';
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : String(iso);
}

// Fecha y hora -> 'dd/mm/aaaa HH:MM' en hora argentina.
// El servidor guarda la hora argentina SIN zona: se respeta tal cual (no se reconvierte).
function fmtFechaHora(valor, conSegundos = false) {
    if (!valor) return '-';
    const s = String(valor);
    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) {
        const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
        if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}${conSegundos && m[6] ? ':' + m[6] : ''}`;
    }
    const d = valor instanceof Date ? valor : new Date(s);
    if (isNaN(d)) return s;
    const p = Object.fromEntries(new Intl.DateTimeFormat('es-AR', {
        timeZone: TZ_AR, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }).formatToParts(d).map(x => [x.type, x.value]));
    return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}${conSegundos ? ':' + p.second : ''}`;
}

function ahoraAR(conSegundos = false) { return fmtFechaHora(new Date(), conSegundos); }

// ---------- importes ----------

function fmtNumero(n, dec = 2) {
    return Number(n || 0).toLocaleString('es-AR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
// $1.234,56 · negativos: -$1.234,56 (nunca "$-1.234,56")
function fmtMoneda(n, dec = 2) {
    const v = Number(n || 0);
    return (v < 0 ? '-$' : '$') + fmtNumero(Math.abs(v), dec);
}

// Texto escrito por el usuario ('1.234,5' / '1234.5' / '$ 1.234') -> número JS, o NaN
function parseImporte(txt) {
    let s = String(txt ?? '').replace(/[^\d,.\-]/g, '');
    if (!s) return NaN;
    if (s.includes(',')) s = s.replace(/\./g, '').replace(',', '.');      // formato argentino
    else if ((s.match(/\./g) || []).length > 1 || /\.\d{3}$/.test(s)) s = s.replace(/\./g, '');  // 1.234.567
    return parseFloat(s);
}

// ---------- campos de importe con separador de miles en vivo ----------
const _protoValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

function _formatearEnVivo(txt) {
    let limpio = String(txt).replace(/[^\d,\-]/g, '');
    const neg = limpio.startsWith('-');
    limpio = limpio.replace(/-/g, '');
    let [ent, ...resto] = limpio.split(',');
    let dec = resto.join('').slice(0, 2);
    ent = ent.replace(/^0+(?=\d)/, '');
    const conPuntos = ent.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const tieneComa = limpio.includes(',');
    return (neg ? '-' : '') + conPuntos + (tieneComa ? ',' + dec : '');
}

function convertirCampoImporte(el) {
    if (el.dataset.importe) return;
    el.dataset.importe = '1';
    const def = el.getAttribute('value');
    el.type = 'text';
    el.setAttribute('inputmode', 'decimal');
    el.setAttribute('autocomplete', 'off');
    el.classList.add('input-importe');
    // .value devuelve SIEMPRE el número "crudo" (1234.56) para que el resto del código no cambie;
    // la pantalla muestra 1.234,56
    Object.defineProperty(el, 'value', {
        configurable: true,
        get() {
            const n = parseImporte(_protoValue.get.call(this));
            return isNaN(n) ? '' : String(n);
        },
        set(v) {
            if (v === '' || v === null || v === undefined) { _protoValue.set.call(this, ''); return; }
            const n = typeof v === 'number' ? v : parseImporte(v);
            _protoValue.set.call(this, isNaN(n) ? '' : fmtNumero(n, Number.isInteger(n) ? 0 : 2));
        },
    });
    if (def !== null && def !== '') el.value = def;
    el.addEventListener('input', () => {
        const antes = _protoValue.get.call(el);
        const pos = el.selectionStart ?? antes.length;
        const digitosAntes = antes.slice(0, pos).replace(/[^\d,]/g, '').length;
        const nuevo = _formatearEnVivo(antes);
        _protoValue.set.call(el, nuevo);
        // Reubicar el cursor después de la misma cantidad de dígitos
        let cuenta = 0, i = 0;
        while (i < nuevo.length && cuenta < digitosAntes) { if (/[\d,]/.test(nuevo[i])) cuenta++; i++; }
        try { el.setSelectionRange(i, i); } catch {}
    });
    el.addEventListener('blur', () => {
        const n = parseImporte(_protoValue.get.call(el));
        if (!isNaN(n)) _protoValue.set.call(el, fmtNumero(n, Number.isInteger(n) ? 0 : 2));
    });
}

// Campos que son importes de dinero (no cantidades como meses o año)
const SELECTOR_IMPORTES = [
    'input[type="number"][id*="monto"]', 'input[type="number"][id*="importe"]',
    '#cur-cuota', '#cur-matricula', '#cur-cuota-ant', '#al-deuda-ant', '#al-cuota-personalizada',
    'input[data-importe-auto]',
].join(',');

// ---------- campos de fecha dd/mm/aaaa ----------
// El <input type="date"> original queda oculto como "fuente de verdad" (valor AAAA-MM-DD, eventos
// onchange intactos). Se muestra al lado un campo de texto dd/mm/aaaa con botón de calendario.

function convertirCampoFecha(el) {
    if (el.dataset.fechaAr) return;
    el.dataset.fechaAr = '1';
    const wrap = document.createElement('span');
    wrap.className = 'fecha-ar';
    const vis = document.createElement('input');
    vis.type = 'text';
    vis.inputMode = 'numeric';
    vis.placeholder = 'dd/mm/aaaa';
    vis.maxLength = 10;
    vis.autocomplete = 'off';
    vis.className = 'fecha-ar-texto';
    if (el.id) vis.id = el.id + '-ar';
    if (el.required) { vis.required = true; el.required = false; }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fecha-ar-btn';
    btn.setAttribute('aria-label', 'Abrir calendario');
    btn.innerHTML = '<svg class="ic"><use href="#i-calendar"/></svg>';
    el.parentNode.insertBefore(wrap, el);
    wrap.append(vis, btn, el);
    el.classList.add('fecha-ar-nativo');
    el.tabIndex = -1;
    el.setAttribute('aria-hidden', 'true');
    // Reapuntar el <label> al campo visible
    if (el.id) document.querySelectorAll(`label[for="${el.id}"]`).forEach(l => l.htmlFor = vis.id);

    const mostrar = () => { vis.value = el.value ? fmtFecha(_protoValue.get.call(el)) : ''; };
    Object.defineProperty(el, 'value', {
        configurable: true,
        get() { return _protoValue.get.call(this); },
        set(v) { _protoValue.set.call(this, v || ''); mostrar(); },
    });
    mostrar();
    el.addEventListener('change', mostrar);
    el.addEventListener('input', mostrar);
    btn.addEventListener('click', () => {
        try { el.showPicker(); } catch { el.focus(); el.click(); }
    });
    vis.addEventListener('input', () => {
        const d = vis.value.replace(/\D/g, '').slice(0, 8);
        vis.value = d.length > 4 ? `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`
                  : d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
        if (d.length === 8) aplicar();
        else if (!d.length) { _protoValue.set.call(el, ''); el.dispatchEvent(new Event('change', { bubbles: true })); }
    });
    vis.addEventListener('blur', () => { if (vis.value && !aplicar()) vis.setCustomValidity('Fecha inválida: usá dd/mm/aaaa'); });
    function aplicar() {
        const m = vis.value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        const iso = m ? `${m[3]}-${m[2]}-${m[1]}` : '';
        const d = iso ? new Date(iso + 'T12:00:00') : null;
        if (!d || isNaN(d) || isoDeFecha(d) !== iso) return false;
        vis.setCustomValidity('');
        if (_protoValue.get.call(el) !== iso) {
            _protoValue.set.call(el, iso);
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return true;
    }
    // Al resetear el formulario, refrescar lo visible
    const form = el.closest('form');
    if (form) form.addEventListener('reset', () => setTimeout(mostrar, 0));
}

// ---------- tablas: scroll horizontal en pantallas chicas ----------
function envolverTabla(t) {
    if (t.parentElement && t.parentElement.classList.contains('tabla-wrap')) return;
    const w = document.createElement('div');
    w.className = 'tabla-wrap';
    t.parentNode.insertBefore(w, t);
    w.appendChild(t);
}

// ---------- aplicar a todo lo que hay y a lo que se agregue después ----------
function mejorarCampos(raiz = document) {
    raiz.querySelectorAll(SELECTOR_IMPORTES).forEach(convertirCampoImporte);
    raiz.querySelectorAll('input[type="date"]').forEach(convertirCampoFecha);
    raiz.querySelectorAll('table').forEach(envolverTabla);
}

(function () {
    const iniciar = () => {
        mejorarCampos();
        // Los modales y formularios que se arman con JavaScript también se mejoran solos
        new MutationObserver(muts => {
            for (const m of muts) for (const n of m.addedNodes) {
                if (n.nodeType !== 1) continue;
                if (n.matches && (n.matches(SELECTOR_IMPORTES) || n.matches('input[type="date"]') || n.matches('table'))) mejorarCampos(n.parentNode || document);
                else if (n.querySelector && n.querySelector(`${SELECTOR_IMPORTES},input[type="date"],table`)) mejorarCampos(n);
            }
        }).observe(document.body, { childList: true, subtree: true });
    };
    if (document.readyState !== 'loading') iniciar();
    else document.addEventListener('DOMContentLoaded', iniciar);
})();

// Medios de pago del reporte de cobranzas SIRO, con nombres que entiendan las familias
const CANALES = { LK: 'Red Link', PF: 'Pago Fácil', RP: 'Rapipago', TQR: 'Pago con QR', BPC: 'Pago Mis Cuentas (Banelco)',
    PC: 'Pago Mis Cuentas', PMC: 'Pago Mis Cuentas', CE: 'Cobro Express', BP: 'Bapro Pagos', DEB: 'Débito automático' };
function nombreCanal(p) {  // p = {canal, via}
    if (p.via === 'efectivo') return 'Efectivo en la Asociación';
    return CANALES[(p.canal || '').toUpperCase()] || (p.canal ? 'Pago SIRO (' + p.canal + ')' : 'Pago registrado');
}


// ---------------------------------------------------------------- estado de cuenta (sistema y portal)
const MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
const _escCC = s => (s == null ? '' : String(s)).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// Una ficha por matrícula y por cuota, con su estado (pagada, adeudada, a vencer…)
function htmlCuotasGrid(e) {
    if (!e.items || !e.items.length) return '';
    if (e.cursos && e.cursos.length > 1) {  // un bloque por curso
        return e.cursos.map(c => `<div class="cc-curso"><b>${_escCC(c.nombre)}</b>
            <span class="${c.deuda > 0 ? 'cc-curso-mal' : 'cc-curso-ok'}">${c.deuda > 0 ? _escCC(c.detalle_deuda) + ' · ' + fmtMoneda(c.deuda) : 'Al día'}</span></div>`
            + _gridItems(c.items, true)).join('');
    }
    return _gridItems(e.items, false);
}

function _gridItems(items, sinSufijo) {
    let primera = true;
    return '<div class="cc-grid">' + items.map(it => {
        let est = it.estado;
        if (est === 'a_vencer') { est = primera ? 'a_vencer' : 'futura'; primera = false; }
        const concepto = sinSufijo ? it.concepto.replace(/ \(.*\)$/, '') : it.concepto;
        const nombre = it.es_matricula ? 'Matrícula' : it.examen ? 'Examen ' + MESES_CORTOS[it.mes - 1]
            : (items.length > 2 ? MESES_CORTOS[it.mes - 1] : concepto);
        const dia = f => fmtFecha(f).slice(0, 5);  // 12/10
        const pagos = it.pagos || [];
        const ultimo = pagos.length ? pagos[pagos.length - 1].fecha : null;
        let det = { pagada: it.prepaga ? 'Pagada antes' : it.examen && !it.instancia_id ? 'Pagó ' + dia(ultimo) + '<br>sin instancia' : (ultimo ? 'Pagó ' + dia(ultimo) : 'Pagada'),
            parcial: 'Falta ' + fmtMoneda(it.saldo), adeudada: 'Debe ' + fmtMoneda(it.saldo),
            a_vencer: 'Vence ' + dia(it.vence), futura: 'Pendiente' }[est];
        if (est === 'parcial' && ultimo) det += `<br>Pagó ${fmtMoneda(it.pagado)}`;
        const atraso = it.con_atraso && (est === 'pagada' || est === 'parcial');
        const titulo = [it.concepto, 'vence ' + fmtFecha(it.vence)]
            .concat(pagos.map(x => `pagó ${fmtMoneda(x.importe)} (proceso ${fmtFecha(x.fecha)})`)).join(' · ');
        return `<div class="cc-item cc-${est}${atraso ? ' cc-atraso' : ''}" title="${_escCC(titulo)}">
            <b>${_escCC(nombre)}</b><small>${det}</small>${atraso ? '<em class="cc-tarde">Con atraso</em>' : ''}</div>`;
    }).join('') + '</div>' + htmlLeyendaCuotas();
}

function htmlLeyendaCuotas() {
    return `<div class="cc-leyenda" aria-hidden="true">
        <span><i class="cc-pagada"></i>Pagada</span><span><i class="cc-pagada cc-atraso"></i>Pagada con atraso</span>
        <span><i class="cc-adeudada"></i>Adeudada</span><span><i class="cc-parcial"></i>Pago parcial</span>
        <span><i class="cc-a_vencer"></i>Próxima a vencer</span><span><i class="cc-futura"></i>Pendiente</span></div>`;
}

// "Cuotas adeudadas: 2 · Monto total: $90.000 · Meses sin pago: agosto y septiembre"
function htmlResumenDeuda(e) {
    const prox = e.proximo ? `Próximo vencimiento: <b>${_escCC(e.proximo.concepto)}</b>, ${fmtMoneda(e.proximo.importe)}, vence el <b>${fmtFecha(e.proximo.vence)}</b>.` : '';
    if (!(e.deuda_total > 0)) {
        const ex = e.examenes_pagos ? ` Exámenes pagados en el año: <b>${e.examenes_pagos}</b>.` : '';
        return `<div class="cc-resumen cc-ok"><b>Al día.</b> No hay cuotas vencidas sin pagar.${ex} ${prox}</div>`;
    }
    // Deuda del año en curso y de años anteriores, cada una en su bloque, para que no se confundan
    const anio = e.anio || new Date().getFullYear();
    const deudaAnio = Math.max((e.deuda_total || 0) - (e.deuda_anterior || 0), 0);
    const meses = (e.meses_adeudados || []);
    const lista = meses.length ? (meses.length === 1 ? meses[0] : meses.slice(0, -1).join(', ') + ' y ' + meses[meses.length - 1]) : '';
    const porCurso = e.cursos && e.cursos.length > 1
        ? '<div>' + e.cursos.filter(c => c.deuda > 0).map(c => `<b>${_escCC(c.nombre)}</b>: ${_escCC(c.detalle_deuda.replace(/^Debe /, 'debe '))} (${fmtMoneda(c.deuda)})`).join('<br>') + '</div>' : '';
    const detAnio = [];
    if (e.cuotas_adeudadas) detAnio.push(`<div>${e.cuotas_adeudadas === 1 ? '1 cuota adeudada' : e.cuotas_adeudadas + ' cuotas adeudadas'} de ${anio}</div>`);
    if (e.matricula_adeudada > 0) detAnio.push(`<div>Matrícula ${anio} adeudada: <b>${fmtMoneda(e.matricula_adeudada)}</b></div>`);
    detAnio.push(porCurso || (lista ? `<div>Meses sin pago: <b>${_escCC(lista)}</b></div>` : ''));
    const bloqueAnio = deudaAnio > 0
        ? `<div class="cc-deuda-bloque"><span class="cc-deuda-tit">Año en curso (${anio})</span>
            <span class="cc-deuda-monto">${fmtMoneda(deudaAnio)}</span>${detAnio.join('')}</div>`
        : `<div class="cc-deuda-bloque cc-deuda-cero"><span class="cc-deuda-tit">Año en curso (${anio})</span>
            <span class="cc-deuda-monto">Al día</span><div>No debe cuotas de ${anio}</div></div>`;
    const bloqueAnt = e.deuda_anterior > 0
        ? `<div class="cc-deuda-bloque"><span class="cc-deuda-tit">Años anteriores (hasta ${anio - 1})</span>
            <span class="cc-deuda-monto">${fmtMoneda(e.deuda_anterior)}</span><div>Saldo pendiente de ciclos lectivos anteriores</div></div>` : '';
    return `<div class="cc-resumen cc-mal">
        <div class="cc-deuda-grid">${bloqueAnio}${bloqueAnt}</div>
        <div class="cc-deuda-total"><span>Deuda total</span><b>${fmtMoneda(e.deuda_total)}</b></div>
        ${prox ? `<div class="cc-prox">${prox}</div>` : ''}</div>`;
}

// Pagos del año: un renglón por cada cuota que pagó cada pago, con su fecha de proceso. Si un pago cubre la
// cuota del mes y una vieja (o dos pagos en el mismo mes), cada cuota va en su línea y las viejas se marcan.
function htmlPagosImputados(pagos, cursos = null) {
    if (!pagos || !pagos.length) return '<p class="muted" style="padding:0.75rem 0">Todavía no hay pagos registrados este año.</p>';
    const elegir = cursos && cursos.length > 1 && typeof imputarPagoCurso === 'function';
    return '<ul class="cc-pagos">' + pagos.slice().reverse().map(p => {
        const pagado = p.fecha_pago && p.fecha_pago !== p.fecha ? ` · pagado el ${fmtFecha(p.fecha_pago)}` : '';
        const medio = `${_escCC(nombreCanal(p))}${pagado}`;
        const sel = elegir ? `<label class="cc-imp">Imputar a: <select onchange="imputarPagoCurso(${p.id}, this.value)">
            <option value="">automático (por mes e importe)</option>${cursos.map(c => `<option value="${c.curso_id}" ${p.curso_id === c.curso_id ? 'selected' : ''}>${_escCC(c.nombre)}</option>`).join('')}
            </select></label>` : '';
        const lineas = (p.detalle && p.detalle.length) ? p.detalle : [{ concepto: p.imputado_a || 'Pago', importe: p.importe }];
        const varias = lineas.length > 1;
        return lineas.map((d, i) => {
            const marca = d.atrasada ? '<span class="cc-tag cc-tag-atraso">Cuota atrasada</span>'
                : d.adelanto ? '<span class="cc-tag cc-tag-adelanto">Adelanto</span>'
                : d.tipo === 'a_favor' ? '<span class="cc-tag">Saldo a favor</span>'
                : d.tipo === 'examen' ? '<span class="cc-tag cc-tag-examen">Examen</span>' : '';
            const ultima = i === lineas.length - 1;
            return `<li class="${varias ? 'cc-parte' : ''}${varias && ultima ? ' cc-parte-fin' : ''}">
                <div><b>${fmtFecha(p.fecha)}</b> · ${_escCC(d.concepto)} ${marca}
                <div class="cc-imp">${medio}${varias ? ` · parte de un pago de ${fmtMoneda(p.importe)}` : ''}</div>${i === 0 ? sel : ''}</div>
                <span class="cc-monto">${fmtMoneda(d.importe)}</span></li>`;
        }).join('');
    }).join('') + '</ul>';
}

function copiarTexto(t, aviso = 'Copiado') {
    const ok = () => { if (typeof toast === 'function') toast(aviso); };
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(ok).catch(() => {});
}

// Cupón de pago de SIRO con todas las formas de pago (QR, botón de pago, código electrónico, código de barras)
function htmlCupon(c) {
    if (c.origen !== 'siro_pdf') {  // cupones generados por el sistema: solo el enlace
        return `<div class="cupon" style="grid-template-columns:1fr"><div><h4>${_escCC(c.concepto || 'Cupón de pago')}</h4>
            <div class="cupon-venc"><div>Importe<b>${fmtMoneda(c.monto)}</b></div><div>Generado<b>${fmtFecha((c.fecha || '').slice(0, 10))}</b></div></div>
            ${c.url ? `<a class="btn btn-primary" href="${_escCC(c.url)}" target="_blank" rel="noopener noreferrer">Abrir cupón</a>` : ''}</div></div>`;
    }
    const venc = c.vencimientos.map((v, i) => `<div>${['1er', '2do', '3er'][i]} vencimiento · ${fmtFecha(v.fecha)}<b>${fmtMoneda(v.importe)}</b></div>`).join('');
    const cod = c.codigo_pago ? `<div class="cupon-cod">Código de pago electrónico: <code>${_escCC(c.codigo_pago)}</code>
        <button class="btn btn-sm btn-ghost" onclick="copiarTexto('${_escCC(c.codigo_pago)}','Código copiado')">Copiar</button></div>` : '';
    const barras = c.barras_imagen || c.codigo_barras ? `<div class="cupon-barras">
        ${c.barras_imagen ? `<img src="${_escCC(c.barras_imagen)}" alt="Código de barras del cupón">` : ''}
        ${c.codigo_barras ? `<code>${_escCC(c.codigo_barras)}</code>` : ''}</div>` : '';
    return `<div class="cupon">
        <div class="cupon-qr">${c.qr ? `<img src="${_escCC(c.qr)}" alt="QR para pagar con billetera virtual"><small>Escaneá el QR desde Mercado Pago, MODO, Cuenta DNI, Ualá u otra billetera</small>` : '<small>Sin QR</small>'}</div>
        <div>
            <h4>${_escCC(c.concepto || 'Cupón de pago')}</h4>
            <div class="cupon-venc">${venc}</div>
            ${cod}
            ${barras}
            <div class="cupon-acciones">
                ${c.pago_url ? `<a class="btn btn-primary" href="${_escCC(c.pago_url)}" target="_blank" rel="noopener noreferrer">Pagar online (tarjeta o DEBIN)</a>` : ''}
                ${c.codigo_barras ? `<button class="btn btn-outline" onclick="copiarTexto('${_escCC(c.codigo_barras)}','Número del código de barras copiado')">Copiar código de barras</button>` : ''}
            </div>
            <details class="cupon-como"><summary>¿Cómo pago?</summary><ul>
                <li><b>Billetera virtual</b> (Mercado Pago, MODO, Cuenta DNI, Ualá, Naranja X, Personal Pay): escaneá el QR.</li>
                <li><b>Online con tarjeta o DEBIN</b>: botón «Pagar online», o entrá a siropagos.bancoroela.com.ar y poné el código de pago electrónico.</li>
                <li><b>Home banking</b>: en Link Pagos buscá «BANCO ROELA SIRO» (rubro Administraciones y consorcios) o en Pago Mis Cuentas «BANCO ROELA SIRO» (rubro Consorcios), con el código de pago electrónico.</li>
                <li><b>Efectivo</b> (Rapipago, Pago Fácil, Bancor, Cobro Express, Provincia NET, Pronto Pago, Multipagos y otros): mostrá el código de barras, o decí que pagás a «Banco Roela SIRO» e indicá el código de pago electrónico.</li>
            </ul></details>
        </div></div>`;
}
