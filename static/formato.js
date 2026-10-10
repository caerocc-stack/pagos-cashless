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
