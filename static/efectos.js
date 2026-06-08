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

        // Motor del header: la helice gira en bucle (arranca suave, sube a maxima,
        // frena suave y vuelve a empezar)
        if (window.gsap && document.getElementById('header-helice')) {
            window.gsap.to('#header-helice', {
                rotation: '+=1080',     // 3 vueltas por ciclo
                duration: 2.6,
                ease: 'power2.inOut',   // acelera y desacelera suave
                repeat: -1,             // bucle infinito
                repeatDelay: 0.35,      // breve pausa al detenerse antes de rearrancar
            });
        }
    }

    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();
