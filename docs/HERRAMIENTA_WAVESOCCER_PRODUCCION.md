# Herramienta de importación y recuperación de WaveSoccer

## Estado y alcance

La herramienta es `python -m negocio.wavesoccer_release`: independiente de Flask, no llama a create_app ni ejecuta migraciones al abrir la base. El bloqueo de `load-wavesoccer --apply` en producción permanece intacto. No se realizaron commit, push, despliegues ni conexiones a producción para estas pruebas.

Trabaja sobre SQLite existente con el esquema esperado, procesa los 505 registros del manifiesto y rechaza equivalencias ambiguas. Sin `--apply`, tanto import como recover trabajan sobre una copia en memoria y no escriben en el destino. Abrir una base inexistente es un error: no se crea una base vacía por equivocación.

La carga real requiere conjuntamente:

- `--apply`.
- `--confirm-database` igual a la ruta absoluta resuelta de la base.
- `--confirm 'IMPORTAR 505'` o `--confirm 'RECUPERAR ID_EJECUCION'`.
- `--backup` con un archivo SQLite independiente (no un tar.gz).
- `--backup-sha256` con el hash contrastado con la copia externa.
- `--backup-verified`: declaración del operador de que guardó y verificó la copia externa.
- `--writes-paused`: declaración del operador de que las escrituras están pausadas.
- En Render, `--production`, ruta exacta `/var/data/jerseysaurios/tienda.sqlite3` y `JERSEY_ENV=production`.

## Resultados comprobados en esta preparación

- Suite completa: **52 pruebas aprobadas**, incluido el bloqueo original del cargador local en producción.
- Ensayo real del CLI sobre una copia temporal de `tienda.sqlite3` extraída del respaldo descargado de Render: 505 registros; simulación de 505 categorías nuevas, aplicación de 505, repetición con cero inserciones y recuperación de las 505 categorías creadas mediante desactivación.
- Integridad SQLite y claves foráneas correctas; las tablas de negocio quedaron intactas. También se probaron pagos y cambios de stock posteriores a la importación en bases sintéticas, conservados al recuperar.
- Probados respaldo ausente/corrupto/desactualizado, hash incorrecto, confirmaciones ausentes, esquema inesperado, equivalencias ambiguas, error a mitad de importación y cambios inesperados por triggers: rechazo o rollback sin cargas parciales.
- Recuperación rechazada ante productos asignados, categorías editadas o hijos ajenos.
- `git diff --check` pasó. Hashes del respaldo original descargado y la base local habitual idénticos antes y después del ensayo. No hubo conexión a Render, commit, push ni despliegue.

## Controles y auditoría

Las dos declaraciones no activan mantenimiento ni comprueban por sí mismas la existencia de una copia fuera de Render. Es responsabilidad del operador cumplirlas. La herramienta sí verifica SHA-256, integridad y claves foráneas del respaldo y que esquema y todas sus filas coincidan con la base actual, bajo BEGIN IMMEDIATE. Si hubo un nuevo pedido/pago entre el respaldo y la carga, exige uno reciente. No se debe falsear estas declaraciones ni desactivar JERSEY_ENV.

Se usa una transacción para categorías, procedencias y auditoría. Antes del commit se comparan completas todas las tablas ajenas a la carga y las categorías anteriores, y se comprueba integridad. Un fallo revierte toda la ejecución. La tabla `wavesoccer_import_runs` registra identificador, fecha, hash del manifiesto, hash del respaldo, filas completas de categorías nuevas y estado. No contiene clientes ni contraseñas. Repetir una carga crea una nueva entrada de auditoría, pero cero categorías duplicadas.

## Ensayo en local

Usar solo una copia aislada del respaldo de Render, con permisos privados, por ejemplo `/tmp/ensayo-jerseysaurios/copia.sqlite3`. No usar la base habitual ni sobrescribir el respaldo original. El archivo descargado originalmente es un tar.gz: extraer únicamente el miembro `tienda.sqlite3` a la carpeta de ensayo.

```bash
.venv/bin/python -m negocio.wavesoccer_release import \
  --database /tmp/ensayo-jerseysaurios/copia.sqlite3

.venv/bin/python -m negocio.wavesoccer_release backup \
  --database /tmp/ensayo-jerseysaurios/copia.sqlite3 \
  --output /tmp/ensayo-jerseysaurios/antes.sqlite3
```

El segundo comando devuelve backup, sha256 y verified. No sobrescribe archivos existentes y los crea con permisos 0600. El directorio de destino debe existir.

Para ensayar la aplicación usar la misma sintaxis documentada más abajo, sin `--production`, con todas las rutas cambiadas a `/tmp/ensayo-jerseysaurios/` y el SHA de su respaldo. Para repetir o recuperar crear un respaldo nuevo del estado actual. Un respaldo anterior a la primera importación no sirve para una segunda operación si la base cambió.

## Publicación futura: pendiente de autorización

### 1. GitHub

La rama local preparada es `feature/catalogo-wavesoccer`. Revisar su estado antes de continuar:

```bash
git status --short
git switch feature/catalogo-wavesoccer
.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Seleccionar explícitamente los archivos de código, pruebas, manifiesto, listado e informes revisados. Nunca añadir SQLite, respaldos ni .env. La selección y el commit local se autorizan en la preparación de GitHub. Este bloque documenta el flujo completo; `git push` sigue pendiente de autorización y no se ejecutó:

```bash
git add .gitignore README.md negocio/commands.py negocio/wavesoccer.py \
  negocio/wavesoccer_catalog.json negocio/wavesoccer_release.py \
  tests/test_wavesoccer.py tests/test_wavesoccer_release.py \
  scripts/empaquetar_codigo.py listado_wavesoccer_nuevo.txt \
  docs/REVISION_WAVESOCCER.md docs/PLAN_PUBLICACION_WAVESOCCER.md \
  docs/HERRAMIENTA_WAVESOCCER_PRODUCCION.md docs/REVISION_GITHUB_WAVESOCCER.md
git diff --cached --name-status
git diff --cached
git commit -m "Preparar categorías WaveSoccer e importación auditada"
git push -u origin feature/catalogo-wavesoccer
```

Si el commit local ya existe, no volver a crearlo. Revisar su contenido antes de autorizar `git push`. Subir solo esa rama tras aprobar su contenido; Render debe seguir conectado a main y sin publicación de previews. En GitHub abrir un Pull Request de feature/catalogo-wavesoccer hacia main y no fusionarlo hasta completar la desactivación autorizada de Auto-Deploy y el ensayo de recuperación.

Antes de integrar a main: obtener autorización, cambiar Auto-Deploy a Off en Render y confirmar el valor y ausencia de despliegues pendientes. Si se gestiona con Blueprint, revisar que una sincronización no revierta ese ajuste. Después integrar el commit aprobado; no desplegar automáticamente.

### 2. Respaldo previo al despliegue

Acordar mantenimiento con bloqueo efectivo de pedidos y cambios administrativos, dejando accesible la Shell. Registrar el commit anterior. Desde la Shell activa, con el código anterior todavía publicado:

```bash
printenv JERSEY_DATA_DIR
df -h /var/data
python -m flask --app wsgi:app backup-data
```

Debe imprimir `/var/data/jerseysaurios`. Descargar y verificar el respaldo completo, como se hizo anteriormente: gzip, SHA-256 remoto/local e integridad de SQLite extraída en temporal. Este respaldo anterior al despliegue cubre las migraciones habituales del arranque de Flask. No reutilizar una copia antigua que omita pedidos posteriores.

Desplegar manualmente el SHA aprobado desde Render → Manual Deploy → Deploy a specific commit. Mantener mantenimiento y Auto-Deploy Off. Comprobar estado live, `/salud` y las rutas de SQLite e imágenes. Con un disco persistente el despliegue puede interrumpir temporalmente el servicio.

### 3. Simulación y respaldo SQLite inmediatamente anterior a la importación

Todos los comandos siguientes son FUTUROS, desde la Shell/SSH de la instancia ACTIVA que monta el disco; no desde build, pre-deploy, jobs separados o instancias efímeras. No cambiar JERSEY_ENV.

```bash
python -m negocio.wavesoccer_release import --production \
  --database /var/data/jerseysaurios/tienda.sqlite3
```

Revisar records=505, categorías propuestas, integrity=ok y business_data=intactos. Este número puede diferir del ensayo porque el servidor puede tener otras categorías. run_id de una simulación no se guarda y no debe usarse para recuperar.

Crear una copia nueva y registrar nombre/hash. Se presupone que `respaldos/` ya existe por el respaldo completo; si no existe, crearla de forma autorizada con permisos privados.

```bash
ws_backup="/var/data/jerseysaurios/respaldos/wavesoccer-$(date -u +%Y%m%dT%H%M%S).sqlite3"
python -m negocio.wavesoccer_release backup \
  --database /var/data/jerseysaurios/tienda.sqlite3 \
  --output "$ws_backup"
sha256sum "$ws_backup"
```

Descargar ESE archivo a la computadora, fuera del repositorio, por SSH ya configurado. Ejemplo: sustituir RUTA_DEL_RESPALDO por el valor impreso de ws_backup y DESTINO_LOCAL por una ruta privada nueva:

```bash
(umask 077; ssh -T -i ~/.ssh/id_ed25519 \
  srv-dbfquld9fdbs739rht40@ssh.oregon.render.com \
  'cat RUTA_DEL_RESPALDO' > DESTINO_LOCAL.sqlite3.part)
```

Comprobar código 0 de SSH, archivo no vacío, SHA-256 idéntico al remoto, abrir copia con SQLite y ejecutar integrity_check y foreign_key_check. Solo entonces renombrar .part y declarar el respaldo verificado. La herramienta verifica el archivo del servidor: la existencia de la copia externa es una comprobación del operador.

### 4. Importación real, solo tras aprobación

En la misma Shell de Render, mantener `ws_backup` con la ruta anterior. Establecer `ws_sha` al hash que se contrastó fuera de Render (64 caracteres hexadecimales), sin comillas angulares:

```bash
ws_sha='SUSTITUIR_POR_SHA256_VERIFICADO'
python -m negocio.wavesoccer_release import --production \
  --database /var/data/jerseysaurios/tienda.sqlite3 \
  --apply --backup "$ws_backup" --backup-sha256 "$ws_sha" \
  --confirm-database /var/data/jerseysaurios/tienda.sqlite3 \
  --confirm 'IMPORTAR 505' --writes-paused --backup-verified
```

Si hay un pago/pedido nuevo, el respaldo ya no coincidirá y se cancelará sin carga parcial. No omitir la verificación: restablecer la pausa efectiva y generar otro respaldo.

Guardar el JSON del resultado en un lugar privado, especialmente run_id y manifest_sha256. La auditoría correspondiente también queda en SQLite en la misma transacción.

Validar antes de reabrir: 505 filas, categorías previas intactas, integridad ok, menú de diez grupos, equipos/tipos/temporadas del listado y `/salud`. Repetir la simulación del paso 3: debe proponer cero inserciones. No se necesitan productos ficticios para validar. Conservar el respaldo y la auditoría; reabrir escrituras tras aprobación. No reactivar Auto-Deploy sin decisión explícita.

## Recuperación selectiva

No borra categorías, productos, usuarios, pedidos, pagos, inventario ni procedencias. Desactiva solo los IDs creados por la ejecución seleccionada y mantiene sus filas e historial. No toca raíces/equipos reutilizados. Conserva incluso las escrituras de negocio posteriores a la importación.

Se cancela toda la recuperación si alguna categoría creada fue editada/eliminada, tiene productos/referencias nuevas o hijos ajenos. No intenta adivinar cómo separar esos cambios: requiere revisión manual. Las referencias nuevas de cualquier tabla con FK a categorías se comprueban; `category_sources` se conserva y se permite como procedencia propia. No detectarían referencias libres sin FK en módulos externos al proyecto; revisar cualquier futura extensión antes de usar la herramienta.

Primero simular (sustituir ID_EJECUCION por el run_id REAL aplicado):

```bash
python -m negocio.wavesoccer_release recover --production \
  --database /var/data/jerseysaurios/tienda.sqlite3 \
  --run-id ID_EJECUCION
```

Para aplicar: nueva ventana sin escrituras, crear y verificar un NUEVO respaldo del estado actual como en el paso 3; actualizar `ws_backup` y `ws_sha`. Ejecutar:

```bash
python -m negocio.wavesoccer_release recover --production \
  --database /var/data/jerseysaurios/tienda.sqlite3 \
  --run-id ID_EJECUCION --apply \
  --backup "$ws_backup" --backup-sha256 "$ws_sha" \
  --confirm-database /var/data/jerseysaurios/tienda.sqlite3 \
  --confirm 'RECUPERAR ID_EJECUCION' --writes-paused --backup-verified
```

Cambiar ID_EJECUCION tanto en --run-id como en la confirmación. Repetir recuperación de una ejecución recuperada no vuelve a modificar categorías. Reimportar no reactiva las categorías recuperadas: una reactivación exige revisión administrativa explícita.

Si falló una carga antes de commit, rollback automático; no restaurar la base. Si falló el código, revisar vuelta al commit anterior sin restauración SQLite. Restaurar toda una base implica pérdida de escrituras posteriores y requiere una autorización separada y conciliación; no es el mecanismo normal de recuperación de esta herramienta.
