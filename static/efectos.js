// ===================================================================
//  Efectos visuales: tilt 3D en botones de accion + parallax (GSAP)
// ===================================================================

// --- Botones .btn-3d: destello al hacer click (la presion 3D la hace el CSS con :active) ---
(function () {
    document.addEventListener('click', function (e) {
        const btn = e.target.closest ? e.target.closest('.btn-3d') : null;
        if (!btn) return;
        btn.classList.remove('pulse');
        void btn.offsetWidth;   // reinicia la animacion
        btn.classList.add('pulse');
        setTimeout(() => btn.classList.remove('pulse'), 520);
    });
})();

// --- GSAP: animaciones de entrada por seccion + parallax suave ---
(function () {
    function animarSeccion() {
        if (!window.gsap) return;
        const sec = document.querySelector('.section.active');
        if (!sec) return;
        // Solo animar elementos VISIBLES (no los formularios ocultos con display:none)
        const items = Array.from(sec.querySelectorAll('.card, .kpi-card, .chart-card'))
            .filter(el => el.offsetParent !== null);
        if (!items.length) return;
        // clearProps solo de lo animado (no tocar 'display' ni otros estilos)
        window.gsap.from(items, {
            opacity: 0, y: 18, duration: 0.4, stagger: 0.05,
            ease: 'power2.out', clearProps: 'opacity,transform',
        });
    }

    function init() {
        // Animar la seccion al cambiar de pestaña
        document.querySelectorAll('.nav-btn').forEach(b =>
            b.addEventListener('click', () => setTimeout(animarSeccion, 20))
        );
        // Animacion inicial
        setTimeout(animarSeccion, 100);

        // Motor del header: la helice gira en bucle en 3 fases
        // 3s acelera -> 5s a maxima velocidad -> 3s frena hasta detenerse -> repite
        if (window.gsap && document.getElementById('header-helice')) {
            const tl = window.gsap.timeline({ repeat: -1, repeatDelay: 0.6 });
            tl.to('#header-helice', { rotation: '+=540', duration: 3, ease: 'power2.in' });    // acelera
            tl.to('#header-helice', { rotation: '+=1800', duration: 5, ease: 'none' });        // maxima
            tl.to('#header-helice', { rotation: '+=540', duration: 3, ease: 'power2.out' });   // frena
        }
    }

    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();
