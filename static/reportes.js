// ===================================================================
//  REPORTES, ESTADISTICAS, EXPORTACION Y PDF
// ===================================================================

// --- Logo en base64 (para membrete de PDFs) ---
let logoDataURL = null;
(async function cargarLogo() {
    try {
        const res = await fetch('/static/logo.png');
        const blob = await res.blob();
        logoDataURL = await new Promise(r => {
            const fr = new FileReader();
            fr.onload = () => r(fr.result);
            fr.readAsDataURL(blob);
        });
    } catch (e) { /* sin logo, no critico */ }
})();

// --- Helpers ---
function fmt(n) {
    return Number(n).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtCorto(n) {
    return Number(n).toLocaleString('es-AR', { maximumFractionDigits: 0 });
}
function traducirTipo(t) {
    const map = {
        consumo: 'Consumo', recarga: 'Recarga', reintegro: 'Reintegro',
        transferencia_in: 'Transf. recibida', transferencia_out: 'Transf. enviada',
    };
    return map[t] || t;
}
function paramsFecha() {
    const desde = document.getElementById('rep-desde').value;
    const hasta = document.getElementById('rep-hasta').value;
    const p = new URLSearchParams();
    if (desde) p.set('desde', desde);
    if (hasta) p.set('hasta', hasta);
    return p.toString() ? '?' + p.toString() : '';
}

// --- Rango rapido de fechas ---
function rangoRapido(dias) {
    const hasta = new Date();
    const desde = new Date();
    document.getElementById('rep-hasta').value = hasta.toISOString().slice(0, 10);
    if (dias === 0) {
        document.getElementById('rep-desde').value = '2024-01-01';
    } else {
        desde.setDate(desde.getDate() - dias);
        document.getElementById('rep-desde').value = desde.toISOString().slice(0, 10);
    }
    cargarReportes();
}

// --- Charts (referencias para destruir antes de redibujar) ---
let chartCurso = null, chartOps = null, chartDiario = null;

const COLORES = {
    navy: '#15233b', red: '#a01e22', sky: '#3d7fc4', green: '#16a34a',
    amber: '#d97706', purple: '#8b5cf6', steel: '#5a6b82',
};
const PALETA = ['#3d7fc4', '#a01e22', '#16a34a', '#d97706', '#8b5cf6', '#5a6b82', '#0891b2', '#db2777', '#65a30d', '#9333ea'];

let datosReporteActual = { resumen: null, porCurso: [], topAlumnos: [] };

// --- Cargar todos los reportes ---
async function cargarReportes() {
    // Prefijar rango por defecto (ultimos 30 dias) si esta vacio
    const inpDesde = document.getElementById('rep-desde');
    const inpHasta = document.getElementById('rep-hasta');
    if (!inpDesde.value && !inpHasta.value) {
        const hoy = new Date();
        const hace30 = new Date();
        hace30.setDate(hace30.getDate() - 30);
        inpHasta.value = hoy.toISOString().slice(0, 10);
        inpDesde.value = hace30.toISOString().slice(0, 10);
    }
    const q = paramsFecha();
    try {
        const [resumen, porCurso, diario, topAlumnos] = await Promise.all([
            api('/api/reportes/resumen' + q),
            api('/api/reportes/por-curso' + q),
            api('/api/reportes/diario?dias=30'),
            api('/api/reportes/top-alumnos?limite=10' + (q ? '&' + q.slice(1) : '')),
        ]);
        datosReporteActual = { resumen, porCurso, topAlumnos };
        renderKPIs(resumen);
        renderChartCurso(porCurso);
        renderChartOps(resumen);
        renderChartDiario(diario);
        renderTablaPorCurso(porCurso);
        renderTopAlumnos(topAlumnos);
    } catch (err) {
        toast('Error al cargar reportes: ' + err.message, 'error');
    }
}

function renderKPIs(r) {
    const html = `
        <div class="kpi-card kpi-green">
            <div class="kpi-label">Recargas</div>
            <div class="kpi-valor">$${fmtCorto(r.recargas.monto)}</div>
            <div class="kpi-sub">${r.recargas.cantidad} operaciones</div>
        </div>
        <div class="kpi-card kpi-red">
            <div class="kpi-label">Consumos (ventas)</div>
            <div class="kpi-valor">$${fmtCorto(r.consumos.monto)}</div>
            <div class="kpi-sub">${r.consumos.cantidad} ventas</div>
        </div>
        <div class="kpi-card kpi-amber">
            <div class="kpi-label">Reintegros</div>
            <div class="kpi-valor">$${fmtCorto(r.reintegros.monto)}</div>
            <div class="kpi-sub">${r.reintegros.cantidad} operaciones</div>
        </div>
        <div class="kpi-card kpi-navy">
            <div class="kpi-label">Ticket promedio</div>
            <div class="kpi-valor">$${fmtCorto(r.ticket_promedio)}</div>
            <div class="kpi-sub">por venta</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Saldo en el sistema</div>
            <div class="kpi-valor">$${fmtCorto(r.saldo_total_sistema)}</div>
            <div class="kpi-sub">${r.alumnos_con_saldo} alumnos con saldo</div>
        </div>
        <div class="kpi-card kpi-navy">
            <div class="kpi-label">Total alumnos</div>
            <div class="kpi-valor">${r.total_alumnos}</div>
            <div class="kpi-sub">registrados</div>
        </div>`;
    document.getElementById('kpi-grid').innerHTML = html;
}

function renderChartCurso(datos) {
    const ctx = document.getElementById('chart-curso');
    if (chartCurso) chartCurso.destroy();
    const top = datos.slice(0, 10);
    chartCurso = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top.map(d => d.curso),
            datasets: [{
                label: 'Consumo ($)',
                data: top.map(d => d.total_consumo),
                backgroundColor: COLORES.sky,
                borderRadius: 5,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { ticks: { callback: v => '$' + fmtCorto(v) } } },
        },
    });
}

function renderChartOps(r) {
    const ctx = document.getElementById('chart-ops');
    if (chartOps) chartOps.destroy();
    chartOps = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Consumos', 'Recargas', 'Reintegros', 'Transferencias'],
            datasets: [{
                data: [r.consumos.monto, r.recargas.monto, r.reintegros.monto, r.transferencias.monto],
                backgroundColor: [COLORES.red, COLORES.green, COLORES.amber, COLORES.sky],
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
        },
    });
}

function renderChartDiario(datos) {
    const ctx = document.getElementById('chart-diario');
    if (chartDiario) chartDiario.destroy();
    chartDiario = new Chart(ctx, {
        type: 'line',
        data: {
            labels: datos.map(d => {
                const [y, m, dd] = d.dia.split('-');
                return `${dd}/${m}`;
            }),
            datasets: [{
                label: 'Consumo diario ($)',
                data: datos.map(d => d.total),
                borderColor: COLORES.red,
                backgroundColor: 'rgba(160,30,34,0.1)',
                fill: true, tension: 0.3, pointRadius: 3,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { ticks: { callback: v => '$' + fmtCorto(v) } } },
        },
    });
}

function renderTablaPorCurso(datos) {
    document.getElementById('body-por-curso').innerHTML = datos.map(d => `
        <tr>
            <td><strong>${d.curso}</strong></td>
            <td class="saldo-positivo">$${fmt(d.total_consumo)}</td>
            <td>${d.cantidad_operaciones}</td>
            <td>${d.alumnos_compradores} / ${d.alumnos_curso}</td>
            <td>$${fmt(d.promedio_por_alumno)}</td>
        </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;color:#94a3b8">Sin datos en el período</td></tr>';
}

function renderTopAlumnos(datos) {
    document.getElementById('body-top-alumnos').innerHTML = datos.map((a, i) => `
        <tr>
            <td><strong>${i + 1}</strong></td>
            <td>${a.apellido}, ${a.nombre}</td>
            <td>${a.curso}</td>
            <td>${a.legajo}</td>
            <td class="saldo-positivo">$${fmt(a.total_consumo)}</td>
            <td>${a.cantidad}</td>
        </tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:#94a3b8">Sin datos en el período</td></tr>';
}

// --- Descargar archivo autenticado (Excel / Backup) ---
async function descargarArchivo(url, fallbackName) {
    try {
        toast('Generando archivo...', 'success');
        const res = await fetch(url, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Error al generar el archivo');
        const blob = await res.blob();
        const cd = res.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename=([^;]+)/);
        const name = m ? m[1].trim().replace(/"/g, '') : fallbackName;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
    } catch (err) {
        toast(err.message, 'error');
    }
}

function exportarReporte(tipo) {
    const q = paramsFecha();
    const sep = q ? '&' : '?';
    descargarArchivo(`/api/reportes/exportar-excel${q}${sep}tipo=${tipo}`, `${tipo}.xlsx`);
}

function descargarBackup() {
    if (!confirm('Descargar un backup completo de toda la base de datos (alumnos, tarjetas, saldos y movimientos) en Excel?')) return;
    descargarArchivo('/api/admin/backup', 'backup_apai.xlsx');
}

// --- Membrete comun para PDFs ---
function membretePDF(doc, subtitulo) {
    if (logoDataURL) {
        try { doc.addImage(logoDataURL, 'PNG', 14, 10, 22, 22); } catch (e) {}
    }
    doc.setFontSize(15); doc.setTextColor(21, 35, 59); doc.setFont(undefined, 'bold');
    doc.text('APAI - Pagos Cashless', 40, 18);
    doc.setFontSize(8.5); doc.setTextColor(120); doc.setFont(undefined, 'normal');
    doc.text('Asociación de Padres y Alumnos del I.N.A.C', 40, 24);
    doc.setDrawColor(160, 30, 34); doc.setLineWidth(0.8); doc.line(14, 33, 196, 33);
    doc.setFontSize(13); doc.setTextColor(21, 35, 59); doc.setFont(undefined, 'bold');
    doc.text(subtitulo, 14, 42);
    doc.setFont(undefined, 'normal');
}

function pieDePagina(doc) {
    const paginas = doc.internal.getNumberOfPages();
    for (let i = 1; i <= paginas; i++) {
        doc.setPage(i);
        doc.setFontSize(7.5); doc.setTextColor(150);
        doc.text(`APAI Pagos Cashless — Generado el ${new Date().toLocaleString('es-AR', { hour12: false })}`, 14, 290);
        doc.text(`Página ${i} de ${paginas}`, 180, 290);
    }
}

// --- PDF de movimientos de un alumno (para padres) ---
async function construirPDFAlumno(id) {
    const a = await api(`/api/alumnos/${id}`);
    const movs = await api(`/api/operaciones/historial/${id}?limite=200`);
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();

    membretePDF(doc, 'Comprobante de Movimientos');

    doc.setFontSize(10); doc.setTextColor(40);
    doc.text(`Alumno: ${a.apellido}, ${a.nombre}`, 14, 51);
    doc.text(`Legajo: ${a.legajo}     DNI: ${a.dni}     Curso: ${a.curso}`, 14, 57);

    doc.setFontSize(12); doc.setTextColor(22, 163, 74); doc.setFont(undefined, 'bold');
    doc.text(`Saldo actual: $${fmt(a.saldo)}`, 14, 66);
    doc.setFont(undefined, 'normal');

    const rows = movs.map(m => [
        new Date(m.created_at).toLocaleString('es-AR', { hour12: false }),
        traducirTipo(m.tipo),
        `$${fmt(m.monto)}`,
        m.descripcion || '',
    ]);

    doc.autoTable({
        startY: 72,
        head: [['Fecha', 'Tipo', 'Monto', 'Descripción']],
        body: rows.length ? rows : [['—', 'Sin movimientos', '—', '—']],
        headStyles: { fillColor: [21, 35, 59], textColor: 255, fontSize: 9 },
        styles: { fontSize: 8, cellPadding: 2 },
        alternateRowStyles: { fillColor: [240, 245, 250] },
        columnStyles: { 2: { halign: 'right' } },
        margin: { left: 14, right: 14 },
    });

    pieDePagina(doc);
    return { doc, a };
}

async function generarPDFAlumno(id) {
    try {
        const { doc, a } = await construirPDFAlumno(id);
        doc.save(`movimientos_${a.apellido}_${a.legajo}.pdf`);
        toast('PDF generado');
    } catch (err) {
        toast('Error al generar PDF: ' + err.message, 'error');
    }
}

async function compartirArchivoOFallback(doc, a, canal) {
    const blob = doc.output('blob');
    const nombre = `movimientos_${a.apellido}_${a.legajo}.pdf`;
    const file = new File([blob], nombre, { type: 'application/pdf' });
    const texto = `Movimientos de ${a.nombre} ${a.apellido} (${a.curso}). Saldo actual: $${fmt(a.saldo)}. APAI Pagos Cashless.`;

    // Intento de compartir nativo con archivo adjunto (funciona en celulares)
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
            await navigator.share({ files: [file], title: 'Movimientos APAI', text: texto });
            return;
        } catch (e) { /* usuario cancelo, sigo al fallback */ }
    }

    // Fallback escritorio: descargar PDF y abrir canal con texto (adjuntar manual)
    doc.save(nombre);
    if (canal === 'whatsapp') {
        toast('PDF descargado. Adjuntalo en el chat de WhatsApp.', 'success');
        window.open(`https://wa.me/?text=${encodeURIComponent(texto)}`, '_blank');
    } else if (canal === 'email') {
        toast('PDF descargado. Adjuntalo al correo.', 'success');
        const asunto = `Movimientos APAI - ${a.apellido}, ${a.nombre}`;
        window.open(`mailto:?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(texto + '\n\n(Adjuntar el PDF descargado)')}`, '_blank');
    }
}

async function compartirWhatsAppAlumno(id) {
    try {
        const { doc, a } = await construirPDFAlumno(id);
        await compartirArchivoOFallback(doc, a, 'whatsapp');
    } catch (err) {
        toast('Error: ' + err.message, 'error');
    }
}

async function compartirEmailAlumno(id) {
    try {
        const { doc, a } = await construirPDFAlumno(id);
        await compartirArchivoOFallback(doc, a, 'email');
    } catch (err) {
        toast('Error: ' + err.message, 'error');
    }
}

// --- PDF del reporte general ---
async function exportarReportePDF() {
    try {
        if (!datosReporteActual.resumen) {
            await cargarReportes();
        }
        const r = datosReporteActual.resumen;
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF();

        membretePDF(doc, 'Reporte General de Operaciones');
        doc.setFontSize(9); doc.setTextColor(90);
        doc.text(`Período: ${r.desde} al ${r.hasta}`, 14, 50);

        // Resumen
        doc.autoTable({
            startY: 56,
            head: [['Concepto', 'Monto', 'Cantidad']],
            body: [
                ['Recargas', `$${fmt(r.recargas.monto)}`, r.recargas.cantidad],
                ['Consumos (ventas)', `$${fmt(r.consumos.monto)}`, r.consumos.cantidad],
                ['Reintegros', `$${fmt(r.reintegros.monto)}`, r.reintegros.cantidad],
                ['Transferencias', `$${fmt(r.transferencias.monto)}`, r.transferencias.cantidad],
                ['Saldo total en sistema', `$${fmt(r.saldo_total_sistema)}`, '-'],
                ['Ticket promedio (venta)', `$${fmt(r.ticket_promedio)}`, '-'],
                ['Total alumnos', r.total_alumnos, '-'],
                ['Alumnos con saldo', r.alumnos_con_saldo, '-'],
            ],
            headStyles: { fillColor: [21, 35, 59], textColor: 255 },
            styles: { fontSize: 9, cellPadding: 2.5 },
            columnStyles: { 1: { halign: 'right' }, 2: { halign: 'center' } },
            margin: { left: 14, right: 14 },
        });

        // Consumo por curso
        doc.setFontSize(12); doc.setTextColor(21, 35, 59); doc.setFont(undefined, 'bold');
        doc.text('Consumo por curso', 14, doc.lastAutoTable.finalY + 10);
        doc.setFont(undefined, 'normal');
        doc.autoTable({
            startY: doc.lastAutoTable.finalY + 14,
            head: [['Curso', 'Total', 'Operaciones', 'Compradores', 'Prom. x alumno']],
            body: datosReporteActual.porCurso.map(d => [
                d.curso, `$${fmt(d.total_consumo)}`, d.cantidad_operaciones,
                `${d.alumnos_compradores}/${d.alumnos_curso}`, `$${fmt(d.promedio_por_alumno)}`,
            ]),
            headStyles: { fillColor: [160, 30, 34], textColor: 255 },
            styles: { fontSize: 8, cellPadding: 2 },
            columnStyles: { 1: { halign: 'right' }, 4: { halign: 'right' } },
            margin: { left: 14, right: 14 },
        });

        // Top alumnos
        if (doc.lastAutoTable.finalY > 230) doc.addPage();
        doc.setFontSize(12); doc.setTextColor(21, 35, 59); doc.setFont(undefined, 'bold');
        doc.text('Top 10 alumnos que más consumen', 14, doc.lastAutoTable.finalY + 10);
        doc.setFont(undefined, 'normal');
        doc.autoTable({
            startY: doc.lastAutoTable.finalY + 14,
            head: [['#', 'Alumno', 'Curso', 'Total consumo', 'Operaciones']],
            body: datosReporteActual.topAlumnos.map((a, i) => [
                i + 1, `${a.apellido}, ${a.nombre}`, a.curso, `$${fmt(a.total_consumo)}`, a.cantidad,
            ]),
            headStyles: { fillColor: [21, 35, 59], textColor: 255 },
            styles: { fontSize: 8, cellPadding: 2 },
            columnStyles: { 3: { halign: 'right' } },
            margin: { left: 14, right: 14 },
        });

        pieDePagina(doc);
        doc.save(`reporte_general_${new Date().toISOString().slice(0, 10)}.pdf`);
        toast('Reporte PDF generado');
    } catch (err) {
        toast('Error al generar reporte: ' + err.message, 'error');
    }
}
