# Diagnóstico y plan de publicación de categorías

Este documento recoge el diagnóstico previo a la publicación. La preparación del commit local en `feature/catalogo-wavesoccer` se documenta en [REVISION_GITHUB_WAVESOCCER.md](REVISION_GITHUB_WAVESOCCER.md). No se ejecutaron push, deploy ni escrituras en Render. No se reemplazó ninguna base de datos.

## Diagnóstico comprobado

| Elemento | Resultado |
| --- | --- |
| Repositorio local y remoto GitHub | https://github.com/saulcortes788-dev/Jerseysaurios.git |
| Rama base y rama conectada en Render | main |
| Commit base y main consultado directamente en GitHub | bb1e1e2ae28461b6445f4f77c553208ee8fbeae2 |
| Último despliegue consultado en Render | dep-dbfqull9fdbs739rhvig; estado live; mismo commit |
| Servicio | https://jerseysaurios.onrender.com/ |
| Panel | https://dashboard.render.com/web/srv-dbfquld9fdbs739rht40 |
| Workspace autorizado | My Workspace |
| Despliegue automático | autoDeploy=yes, autoDeployTrigger=commit |
| Disco persistente | jerseysaurios-datos; 1 GB; /var/data |
| Instancias | 1; Gunicorn con un worker |
| Motor de datos de la aplicación | SQLite, no PostgreSQL |
| Ruta efectiva de SQLite comunicada por el propietario desde Render | /var/data/jerseysaurios/tienda.sqlite3 |
| Ruta efectiva de imágenes comunicada por el propietario desde Render | /var/data/jerseysaurios/uploads |
| Datos locales | data/tienda.sqlite3; no se deben transferir a producción |

El disco y el servicio se consultaron nuevamente por el plugin Render. Las rutas efectivas proceden de las comprobaciones anteriores del propietario; el conector no expone las variables ni el filesystem. Antes de ejecutar la futura carga se volverán a comprobar las rutas, permisos y espacio libre desde Shell. La persistencia depende de que los archivos permanezcan bajo /var/data; no equivale a tener una copia externa de respaldo.

El despliegue automático está configurado en Render sobre la rama de GitHub. Un push o merge en main puede publicar. La revisión actual de GitHub encontró cero workflows y cero webhooks de repositorio. Render mantiene previews desactivadas. No se auditaron automatizaciones externas ajenas a estas configuraciones.

La carga actual contiene las 505 filas del propietario. Se aplica manualmente y no forma parte del arranque, build o pre-deploy. El comando `load-wavesoccer --apply` sigue rechazando PRODUCTION. Ya se preparó la herramienta independiente `python -m negocio.wavesoccer_release`, ensayada únicamente en copias aisladas. Los comandos exactos y controles están en [HERRAMIENTA_WAVESOCCER_PRODUCCION.md](HERRAMIENTA_WAVESOCCER_PRODUCCION.md). Publicar el código por sí solo no publicará los datos.

## Protección de archivos

Se revisaron 72 archivos versionados o candidatos visibles a Git. No se detectaron rutas de bases, respaldos, archivos .env privados ni patrones reconocidos de claves privadas/tokens en ese conjunto. Tampoco se encontraron rutas privadas en el historial Git local disponible. Esto es una revisión de patrones y rutas, no una garantía absoluta de ausencia de secretos.

`.gitignore` excluye data/, backups/, dist/, .env, .env.*, SQLite, logs y .venv; permite .env.example. El ejemplo contiene nombres de configuración, sin SECRET_KEY real. No hay cambios preparados en staging. Se añadieron reglas generales para respaldos tar.gz/tgz/bak, otras bases SQLite y claves privadas fuera de las carpetas habituales; aun así, los respaldos deben mantenerse fuera del repositorio.

Antes del futuro commit se seleccionarán archivos explícitamente; no usar `git add .`. Conjunto previsto: negocio/wavesoccer.py, negocio/wavesoccer_catalog.json, negocio/commands.py, tests/test_wavesoccer.py, scripts/empaquetar_codigo.py, listado_wavesoccer_nuevo.txt, README.md y los informes de docs/. Cualquier herramienta nueva de carga/recuperación se añadirá solo tras revisión. Los otros archivos de listado e instrucciones del propietario no son necesarios para ejecutar el cargador y se revisarán por separado.

Volver a revisar `git diff --cached --name-status` y `git diff --cached` antes del commit. Nunca incluir la base local ni la copia descargada de Render, aunque gzip e integridad hayan pasado. Conservar SECRET_KEY y los usuarios actuales.

## Procedimiento futuro, en orden

Todas las acciones externas de esta sección están pendientes de autorización. Los comandos se documentan, no se ejecutaron.

### 1. Preparar una carga remota explícita y ensayarla

Preparar localmente una herramienta revisada que mantenga PRODUCTION activo y requiera confirmación de la ruta exacta de SQLite y de la intención de aplicar. Debe tener simulación por defecto, rechazar una base inexistente o con esquema inesperado, validar las 505 filas y el manifiesto, comprobar claves foráneas, respaldar antes de escribir y bloquear operaciones concurrentes mediante BEGIN IMMEDIATE.

Reutilizar apply_catalog, sin borrar/reconstruir tablas existentes ni reasignar productos. Solo añadir ramas faltantes en shop_categories y la tabla de procedencia category_sources, conservando IDs y datos anteriores. Reutilizar las diez raíces existentes y sus equivalencias; conservar categorías inactivas. No crear datos de productos ni sustituir SQLite por un archivo local.

Añadir un registro privado de ejecución con los IDs creados y los cambios de procedencia, para permitir recuperación selectiva. Comparar todas las filas de las tablas de negocio antes y después dentro de la ventana sin escrituras; contar filas por sí solo no basta. La cantidad de categorías nuevas será la diferencia real del servidor, no necesariamente las 438 de la base local.

**La herramienta ya está implementada localmente y aún no está desplegada.** Su sintaxis y procedimientos exactos están en el manual enlazado. No ejecutar JERSEY_ENV=local en Render ni editar/eliminar el bloqueo actual para eludirlo. No usar un script improvisado que llame a apply_catalog saltándose controles.

Descargar un respaldo reciente de producción por SSH, manteniéndolo privado, y ensayar en una carpeta local aislada: abrir una copia, simular, aplicar, comparar tablas completas, verificar todos los enlaces y repetir para confirmar cero duplicados. La copia de ensayo nunca debe apuntar al DATA_DIR local habitual ni al servidor. Ejecutar la suite completa y probar los rechazos del nuevo modo de producción.

### 2. Publicar primero para revisión en GitHub

Usar la rama local `feature/catalogo-wavesoccer`; su push sigue pendiente de autorización. Revisar que Render siga conectado a main, sin previews ni integraciones que publiquen esa rama. Preparar un commit con archivos explícitos, subir únicamente esa rama y abrir la revisión. Esto permite revisar código sin actualizar main. No cambiar el repositorio remoto.

Antes de fusionar a main, en Render → servicio → Settings → Auto-Deploy, elegir Off, tras autorización. Volver a consultar el servicio y verificar que quedó desactivado y que no hay despliegues en cola. No confiar únicamente en una frase de skip en el commit. Mantener Off durante la publicación y revisar que una sincronización de Blueprint no reactive el valor predeterminado; cualquier cambio necesario al Blueprint se prepara y valida antes de fusionar.

Solo después de la revisión aprobada, fusionar a main manteniendo apagado el despliegue automático. Confirmar el SHA exacto y que todavía sigue live la versión anterior. No desplegar todavía si falta el ensayo o la herramienta de carga.

### 3. Ventana de mantenimiento y respaldo reciente

Acordar una ventana sin pedidos, pagos, inventario, usuarios ni cambios administrativos. Bloquear efectivamente las escrituras externas y administrativas, dejar terminar transacciones en curso y comprobar que la consola autorizada siga disponible. No basta con cambiar el banner de la tienda. No suspender la instancia que necesita montar el disco.

En la Shell del servicio activo comprobar:

```bash
printenv JERSEY_DATA_DIR
ls -l /var/data/jerseysaurios/tienda.sqlite3
df -h /var/data
python -m flask --app wsgi:app backup-data
```

Esperado DATA_DIR: /var/data/jerseysaurios. Ante ruta distinta, espacio insuficiente o error de respaldo, detener la publicación. Registrar la ruta y hora del respaldo nuevo. backup-data usa SQLite backup y copia uploads: impedir escrituras durante la copia para consistencia conjunta. No usar `cp` de una SQLite abierta como método de respaldo.

Descargar la copia con el SSH ya configurado; sustituir RUTA_REAL y NOMBRE_NUEVO por los del respaldo recién creado. Ejecutar en la computadora, con destino privado fuera del proyecto:

```bash
(umask 077; ssh -T -i ~/.ssh/id_ed25519 srv-dbfquld9fdbs739rht40@ssh.oregon.render.com 'cat RUTA_REAL' > NOMBRE_NUEVO.tar.gz.part)
```

Comprobar que SSH finalizó con código 0, que el archivo no está vacío y que gzip -t pasa. Solo entonces renombrar .part a .tar.gz. Comparar SHA-256 remoto y local del archivo, extraer SQLite en temporal, abrirla y comprobar `PRAGMA integrity_check` y `PRAGMA foreign_key_check`. Inspeccionar también el contenido esperado del tar, sin publicar información de clientes. Mantener una copia externa protegida y verificar su apertura antes de continuar.

El respaldo anterior jerseysaurios-20261026T201419632798Z.tar.gz pasó gzip y comprobaciones SQLite comunicadas por el propietario. No sustituye al respaldo reciente de esta ventana, porque podrían existir pedidos nuevos.

### 4. Desplegar código y ejecutar la carga autorizada

En Render → Manual Deploy → Deploy a specific commit, desplegar el SHA aprobado y comprobar estado live. Con disco persistente habrá una interrupción de servicio; mantener la ventana de mantenimiento. Comprobar /salud y que DATA_DIR, DATABASE y UPLOAD_FOLDER siguen apuntando al disco.

No poner la carga SQLite en buildCommand ni preDeployCommand: esos entornos no montan el disco. Ejecutar la herramienta preparada en el paso 1 exclusivamente desde Shell/SSH de la instancia activa que monta /var/data; tampoco desde una instancia efímera ni un one-off job separado.

Primero simular contra la base real y revisar el número de inserciones y las equivalencias. Después ejecutar una única aplicación explícita, con un segundo respaldo inmediato previo y auditoría de IDs. Mantener el modo de producción y las claves actuales. Si falla una entrada, la transacción debe revertir toda la carga; investigar antes de reintentar.

El arranque de Flask conserva las migraciones habituales, que pueden escribir incluso durante una simulación CLI. Por eso el primer respaldo se obtiene antes de desplegar y se ensaya la versión nueva sobre una copia del esquema del servidor.

### 5. Validación antes de reabrir

- Confirmar 505 filas procesadas y diez grupos resueltos, con 172 equipos/selecciones y tipos correctos.
- Comparar todas las filas preexistentes de categorías y las tablas completas de products, orders, order_items, clients, admins, sales, payments, refunds, expenses, shop_settings, product_photos y site_sections cuando existan. Ninguna tabla de negocio debe cambiar durante la ventana.
- Integridad SQLite ok y cero errores de claves foráneas; fuentes y nuevas referencias correctas.
- Comprobar /salud, portada, menú, cada ruta resuelta del listado y acceso administrativo sin crear ventas/pedidos ficticios en producción. Los nombres y slugs reales pueden reutilizar los antiguos.
- Repetir la simulación: cero categorías nuevas.
- Guardar el informe privado de ejecución y un respaldo posterior. Reabrir escrituras y observar errores/latencia. Dejar auto-deploy Off hasta decidir expresamente reactivarlo.

## Recuperación

1. Si falla antes del commit de la transacción de categorías, rollback de esa transacción y ninguna restauración de base. Verificar integridad y datos antes de reabrir.
2. Si falla el código desplegado, volver al commit anterior aprobado sin restaurar datos. Ensayar previamente su compatibilidad con la tabla aditiva y las categorías nuevas. La reversión de código no revierte SQLite.
3. Si solo falla la organización de categorías, usar los IDs auditados para desactivar las ramas recién creadas. Revisar si recibieron productos o hijos antes de cualquier eliminación. No tocar raíces/equipos anteriores ni revertir IDs de forma masiva. Mantener pedidos y stock actuales.
4. Solo ante corrupción u otro daño que exija restauración completa: cerrar escrituras y conexiones, guardar primero una copia del estado fallido y sus archivos auxiliares, restaurar y validar el respaldo en una ubicación separada y preparar una sustitución controlada con autorización adicional. No copiar SQLite por encima de conexiones abiertas ni mezclar una base restaurada con archivos -wal/-shm antiguos.
5. Una restauración completa perdería las escrituras posteriores al respaldo: conciliar primero pedidos, pagos e inventario y obtener autorización. Esta es una contingencia, no el procedimiento de publicación. No restaurar la base local en Render.

## Fuentes actuales consultadas

- https://render.com/docs/deploys — auto-deploy, deploy manual por SHA y pre-deploy sin acceso al disco.
- https://render.com/docs/disks — persistencia bajo el montaje, acceso solo en runtime e interrupción al desplegar.
- https://render.com/docs/health-checks — comprobación de disponibilidad de la instancia.

Las versiones Markdown no fueron legibles mediante el lector; se consultaron las versiones HTML oficiales. El diagnóstico del servicio proviene de get_service/list_deploys del plugin Render; GitHub main se consultó con git ls-remote, sin cambios.
