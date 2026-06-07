// ===================================================================
//  Efectos visuales: tilt 3D en botones de accion + parallax (GSAP)
// ===================================================================

// --- Efecto 3D (tilt) en botones .btn-3d, con delegacion (sirve para botones dinamicos) ---
(function () {
    let actual = null;

    document.addEventListener('mousemove', function (e) {
        const btn = e.target.closest ? e.target.closest('.btn-3d') : null;
        if (btn) {
            const r = btn.getBoundingClientRect();
            const px = (e.clientX - r.left) / r.width - 0.5;
            const py = (e.clientY - r.top) / r.height - 0.5;
            btn.style.transform =
                `perspective(600px) rotateY(${px * 12}deg) rotateX(${-py * 12}deg) translateY(-2px) scale(1.02)`;
            actual = btn;
        } else if (actual) {
            actual.style.transform = '';
            actual = null;
        }
    });

    document.addEventListener('mousedown', function (e) {
        const btn = e.target.closest ? e.target.closest('.btn-3d') : null;
        if (btn) btn.style.transform += ' scale(0.97)';
    });
})();

// --- GSAP: animaciones de entrada por seccion + parallax suave ---
(function () {
    function animarSeccion() {
        if (!window.gsap) return;
        const sec = document.querySelector('.section.active');
        if (!sec) return;
        const items = sec.querySelectorAll('.card, .kpi-card, .chart-card, .cobro-card-tarjeta');
        if (!items.length) return;
        window.gsap.from(items, {
            opacity: 0, y: 18, duration: 0.4, stagger: 0.05,
            ease: 'power2.out', clearProps: 'all',
        });
    }

    function init() {
        // Animar la seccion al cambiar de pestaña
        document.querySelectorAll('.nav-btn').forEach(b =>
            b.addEventListener('click', () => setTimeout(animarSeccion, 20))
        );
        // Animacion inicial
        setTimeout(animarSeccion, 100);

        // Parallax suave del logo del header siguiendo el mouse
        if (window.gsap) {
            document.addEventListener('mousemove', function (e) {
                const x = e.clientX / window.innerWidth - 0.5;
                const y = e.clientY / window.innerHeight - 0.5;
                window.gsap.to('.header-logo', {
                    x: x * 12, y: y * 7, rotation: x * 10,
                    duration: 0.6, ease: 'power2.out',
                });
            });
        }
    }

    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();
