# Auditoría de Seguridad y Rendimiento — APAI Pay

Análisis de todas las capas (infraestructura, backend y frontend), plan de remediación
priorizado, cambios aplicados y recomendaciones de mantenimiento.

---

## 1. Resumen ejecutivo

Se auditó la plataforma completa. Se encontraron **2 vulnerabilidades críticas**, **3 altas**
y varias medias/bajas. Las más sensibles ya fueron **corregidas en el código**. Quedan
**3 acciones manuales** a cargo del administrador (sección 6) que son obligatorias antes de
operar con datos reales.

---

## 2. Hallazgos y estado

| Sev. | Hallazgo | Capa | Estado |
|------|----------|------|--------|
| 🔴 Crítica | **API sin autenticación**: `/api/alumnos`, `/api/tarjetas`, `/api/operaciones`, `/api/cupones` se podían usar sin iniciar sesión (leer DNI/emails, cobrar, recargar, enviar cupones, borrar alumnos). | Backend | ✅ Resuelto |
| 🔴 Crítica | **Clave de firma de tokens (SECRET_KEY) fija en el código**: permitía falsificar sesiones de cualquier usuario. | Backend | ✅ Resuelto |
| 🟠 Alta | **Contraseña de admin por defecto** (`apai2024`) visible en el historial de git. | Backend | ⚠️ Mitigado — requiere cambio manual (sección 6) |
| 🟠 Alta | **Token accesible por JavaScript** (cookie sin `HttpOnly`): un XSS podía robar la sesión. | Backend | ✅ Resuelto (`HttpOnly`) |
| 🟠 Alta | **XSS almacenado en el frontend**: nombres/datos se insertaban como HTML sin escapar. | Frontend | ✅ Resuelto (escape de HTML) |
| 🟡 Media | **CORS abierto** (`*`) junto con credenciales. | Backend | ✅ Resuelto (origen restringido) |
| 🟡 Media | **Faltaban encabezados HSTS y CSP**. | Backend | ✅ Resuelto |
| 🟡 Media | **Inyección/rotura por comillas en botón Eliminar** (apellidos con apóstrofe). | Frontend | ✅ Resuelto |
| 🔵 Baja | Límite de intentos de login en memoria (se reinicia al reiniciar el servicio). | Backend | 📋 Recomendación |
| 🔵 Baja | Dependencias sin versión fija (riesgo de cambios sorpresivos). | Infra | 📋 Recomendación |
| 🔵 Baja | Contraseña de la base de datos débil y compartida. | Infra | ⚠️ Rotar (sección 6) |

---

## 3. Puertos y accesos

La plataforma corre sobre servicios administrados (Render + Supabase); no hay servidores
propios con puertos abiertos a internet. Superficie de exposición real:

| Servicio | Puerto / acceso | Quién entra | Estado |
|----------|-----------------|-------------|--------|
| Aplicación web (Render) | HTTPS 443 (único expuesto a internet) | Público, pero detrás de login | ✅ Forzado HTTPS + HSTS |
| Base de datos (Supabase) | 6543 (pooler), con usuario y contraseña | Solo el backend y el backup | ✅ No expuesta al público; requiere credenciales |
| SMTP saliente | 25/465/587 | — | ✅ No se usa (Render los bloquea); el email sale por API HTTPS |
| Panel Render / Supabase / GitHub | Web con login propio | Administrador | ⚠️ Activar 2FA en las tres cuentas |

**Cambios documentados de acceso:**
- API de datos y operaciones: de **acceso anónimo** → **requiere sesión iniciada**.
- CORS: de **cualquier origen** → **solo orígenes autorizados** (variable `APP_ORIGIN`).
- Cookie de sesión: de **legible por JS** → **HttpOnly + Secure + SameSite=Lax**.

---

## 4. Cambios aplicados (documentados)

1. **Autenticación global** en los routers de alumnos, tarjetas, operaciones y cupones
   (`Depends(get_current_user)` a nivel de router).
2. **SECRET_KEY** sin valor fijo: se toma del entorno; si falta, se genera una aleatoria por
   proceso (segura) y se avisa por consola.
3. **Cookie de sesión** con `HttpOnly`, `Secure` y `SameSite=Lax`. El token ya no viaja en el
   cuerpo de la respuesta de login.
4. **Encabezados de seguridad**: se agregó `Strict-Transport-Security` (HSTS) y
   `Content-Security-Policy` (CSP) además de los ya existentes (anti-clickjacking, nosniff).
5. **CORS** restringido a `APP_ORIGIN` (por defecto, solo mismo origen).
6. **Frontend**: función `escapeHtml()` aplicada a todos los datos de usuario que se muestran
   (alumnos, movimientos, búsquedas, fichas); botón Eliminar sin interpolar texto en el HTML.
7. **Contraseña inicial** configurable por entorno (`ADMIN_PASSWORD`) y ya no se imprime en los logs.
8. **Rendimiento**: índices en `movimientos(alumno_id)`, `movimientos(created_at)`,
   `alumnos(curso)` y `alumnos(area)`; reciclado de conexiones a la base.

---

## 5. Plan de remediación (por prioridad)

- **Fase 1 — Crítico (HECHO):** cerrar la API, blindar la clave de tokens, cookie HttpOnly, escape XSS.
- **Fase 2 — A cargo del administrador (PENDIENTE, ver sección 6):** definir SECRET_KEY,
  cambiar la contraseña de admin, rotar la contraseña de la base.
- **Fase 3 — Mejoras recomendadas:** fijar versiones de dependencias, límite de intentos
  persistente, monitoreo de logs, 2FA en los paneles.

---

## 6. Acciones obligatorias del administrador (en Render / Supabase)

1. **Definir `SECRET_KEY`** en Render → Environment: un texto largo y aleatorio (40+ caracteres).
   Sin esto, las sesiones se cierran en cada reinicio del servicio.
2. **Cambiar la contraseña de admin** al primer ingreso (Mi cuenta → Cambiar contraseña).
   La clave por defecto figura en el historial del repo: **debe reemplazarse**.
3. **Rotar la contraseña de la base de datos** en Supabase (la actual es débil y fue compartida).
   Luego actualizar `DATABASE_URL` en Render y en el secret de GitHub (para el backup).
4. *(Opcional)* Definir `APP_ORIGIN` con la URL del sistema si en el futuro se accede desde otro dominio.
5. *(Recomendado)* Activar **verificación en 2 pasos** en Render, Supabase y GitHub.

---

## 7. Análisis de rendimiento

| Punto | Estado | Detalle |
|-------|--------|---------|
| Listado de alumnos | ✅ Óptimo | Carga alumnos + saldo en una sola consulta (`joinedload`), evita N+1. |
| Importación masiva | ✅ Óptimo | Inserción en bloque; antes hacía 600+ consultas (timeout), ahora 1. |
| Historial y reportes | ✅ Mejorado | Índices nuevos en `movimientos` aceleran las consultas por alumno y por fecha. |
| Envío de cuota por área/curso | ✅ Mejorado | Índices en `alumnos(area, curso)`. |
| Conexiones a la base | ✅ Mejorado | `pool_pre_ping` + `pool_recycle` evitan errores por conexiones caídas. |
| Arranque en frío (Render free) | 🔵 Limitación | El plan gratuito "duerme" tras 15 min; la primera carga puede tardar ~30 s. Se resuelve con un plan pago o un "ping" periódico. |

---

## 8. Recomendaciones de mantenimiento

- **Backups:** ya hay copia automática diaria (GitHub Actions) + descarga manual. Verificar
  cada tanto que el backup se genere (pestaña Actions).
- **Contraseñas:** rotar la clave de admin y de la base cada 6-12 meses; usar claves largas.
- **Usuarios:** crear un usuario por operador (no compartir el de admin) para saber quién hizo cada cobro.
- **Dependencias:** una vez estable, fijar versiones en `requirements.txt` y revisarlas 1-2 veces al año.
- **Logs:** revisar los logs de Render ante cualquier comportamiento raro.
- **Datos sensibles:** no compartir credenciales por chat/mail; cargarlas siempre como variables de entorno.
- **Saldos:** controlar periódicamente que el "Saldo total en el sistema" esté respaldado por el dinero en el banco.
- **Revisión de seguridad:** repetir esta auditoría una vez al año o ante cambios grandes.

---

*Elaborado por Carlos Cambareri.*
