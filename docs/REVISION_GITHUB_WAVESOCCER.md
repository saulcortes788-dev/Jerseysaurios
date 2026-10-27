# Preparación local para GitHub: WaveSoccer

Rama de trabajo: `feature/catalogo-wavesoccer`. Base: `main`, commit `bb1e1e2ae28461b6445f4f77c553208ee8fbeae2`, coincidente con main consultado en GitHub. El remoto se conserva: https://github.com/saulcortes788-dev/Jerseysaurios.git.

Esta preparación autoriza un commit LOCAL. No autoriza push, merge, deploy ni cambios en Render. El commit reúne únicamente código, listado de referencia, manifiesto, pruebas, documentación y reglas de exclusión. El identificador final se obtiene con `git log -1 --oneline`; main debe seguir apuntando al commit base.

## Contenido revisado

- Catálogo de 505 filas proporcionadas por el propietario: manifiesto JSON y listado de texto coincidentes, 172 equipos/selecciones en diez grupos. Sin productos, precios, inventario ni imágenes.
- Carga local idempotente con respaldo y bloqueo en producción.
- Herramienta independiente con simulación, confirmaciones, respaldo verificable, transacción y auditoría; recuperación selectiva por desactivación.
- Pruebas de navegación, conservación, integridad, fallos parciales y recuperación.
- Empaquetado del listado junto al código y manuales de operación.
- `.gitignore` reforzado para otras extensiones SQLite, respaldos y claves privadas fuera de las carpetas habituales.

Se revisaron los archivos candidatos completos y se ejecutó búsqueda de patrones de credenciales/rutas privadas. No se detectaron secretos reales ni datos privados de clientes en el conjunto seleccionado. Los datos artificiales de las pruebas no son usuarios ni credenciales de producción. Esta revisión de contenido y patrones no garantiza detectar todo formato posible de secreto.

No se incluyen `.env`, SQLite, respaldos, uploads, claves SSH, entorno virtual ni artefactos dist/. `.env.example` ya versionado contiene únicamente configuración de referencia, sin SECRET_KEY real. Los archivos `INSTRUCCIONES_listado_wavesoccer.md` y `listado_wavesoccer_codex.txt` se conservan localmente sin incluirlos en el commit: son material auxiliar que la herramienta no necesita.

## Validación

`python -m unittest discover -s tests -v`, usando `.venv/bin/python`: **52 pruebas aprobadas**. Se incluye el test que comprueba igualdad exacta entre las 505 filas del listado y el manifiesto que lee la importación. `git diff --check` pasó. El contenido preparado se vuelve a comprobar desde el índice de Git antes del commit.

## Riesgo de despliegue al subir esta rama

Consulta actual de solo lectura mediante el plugin Render:

- Servicio jerseysaurios conectado a `main`.
- AutoDeploy=yes, autoDeployTrigger=commit.
- Previews generation=off y pullRequestPreviewsEnabled=no.

Consulta de solo lectura de GitHub por su API: **cero workflows de Actions y cero webhooks de repositorio**. No hay workflows añadidos por este cambio. El conector GitHub falló; estas consultas se completaron mediante `gh api`. No se expusieron URLs de hooks ni secretos.

Con esa configuración, un push exclusivamente a `feature/catalogo-wavesoccer` no debería desplegar el servicio existente ni generar previews. No se pueden descartar automatizaciones externas no visibles en estas consultas ni cambios de configuración posteriores. Revalidar rama y previews inmediatamente antes del push si cambió la configuración.

Un merge/push a `main` sí puede desplegar automáticamente: antes de ese paso se requiere autorización y coordinar Auto-Deploy Off. Subir esta rama no importa datos por sí solo. La carga real en Render queda pendiente de autorización, mantenimiento, respaldo reciente verificado y ejecución explícita del manual.

## Pendientes

1. Aprobar el push de esta rama de revisión.
2. Revisar el Pull Request antes de autorizar merge a main.
3. Coordinar despliegue manual y auto-deploy, sin cambiar disco, rutas ni SECRET_KEY.
4. Obtener respaldo reciente y verificar su copia externa antes de la importación real.

No reemplazar la base de Render por la local. Las declaraciones --writes-paused y --backup-verified requieren cumplimiento real por parte del operador.
