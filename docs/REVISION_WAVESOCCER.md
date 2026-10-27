# Categorías WaveSoccer: implementación local de los 505 registros

## Resultado

Se procesaron las 505 filas de `listado_wavesoccer_nuevo.txt`, sin omitir filas ni descargar imágenes. El manifiesto `negocio/wavesoccer_catalog.json` conserva las cinco columnas de cada fila, incluyendo los campos vacíos y la URL general del proveedor. Las fuentes son las proporcionadas por el propietario; la fecha del manifiesto corresponde a la revisión del archivo, no a una verificación nueva de disponibilidad comercial.

Los diez grupos corresponden a categorías principales ya presentes. Se reutilizan sus IDs, nombres y slugs para conservar URLs, productos y navegación:

| Grupo del archivo | Categoría local conservada | Equipos/selecciones del listado |
| --- | --- | ---: |
| Liga MX / Expansión MX | Liga MX | 22 |
| LaLiga / Hypermotion | LaLiga | 41 |
| Premier League / Championship | Premier League | 10 |
| Serie A | Serie A | 8 |
| Bundesliga | Bundesliga | 6 |
| MLS | MLS | 30 |
| J1 League | Liga de Japón | 18 |
| LPF Argentina | Liga Argentina | 14 |
| Brasileirão | Brasileirão | 15 |
| Mundial 2026 | Mundial 2026 | 8 |

Hay 172 equipos o selecciones en el archivo. Los grupos del proveedor pueden incluir varias divisiones; no se afirma que todos sus equipos pertenezcan a primera división. Se mantienen también todas las categorías ajenas a estos diez grupos.

**La carga creó 438 categorías adicionales en la base local:** 105 equipos, 330 tipos y 3 temporadas. Las diez principales ya existían y se reutilizaron. La base pasó de 151 a 589 categorías en total, incluyendo las categorías anteriores y la carga parcial previa, que se conservaron. En una base diferente, la cantidad de inserciones dependerá de las ramas ya existentes.

Ejemplos navegables:

- `/categorias/liga-mx/america/authentic`
- `/categorias/mls/inter-miami/infantil`
- `/categorias/laliga/atletico-de-madrid/2024-25`
- `/categorias/mundial-2026/iran/infantil`

## Organización y duplicados

El árbol es liga → equipo → tipo cuando no se conoce temporada. Las únicas tres temporadas suministradas son 2024-25 para Mallorca, Oviedo y Atlético de Madrid, dentro de LaLiga. No se asigna esa temporada a los tipos sin fecha: esas ramas permanecen directamente bajo el equipo.

La búsqueda de categorías compara nombres normalizados sin diferencias de mayúsculas o acentos y utiliza equivalencias explícitas para los nombres anteriores del proveedor. Por ejemplo, Manchester City reutiliza MAN CITY; Real Salt Lake reutiliza REAL SALK LAKE. Estas equivalencias se limitan a la rama del mismo grupo. Se conservan los nombres y URLs existentes, aunque el proveedor los haya escrito de otra manera. No se fusionan ni eliminan registros existentes.

Se unifican «Portero infantil» con «Infantil portero» y «Short de portero»/«Portero short» con «Short portero». Las etiquetas Authentic y versión jugador se conservan separadas, pues el archivo no acredita que sean equivalentes. Los shorts se incluyen como tipos de prenda según las filas proporcionadas.

El menú y las páginas públicas ya leen el árbol de SQLite: no fue necesario cambiar sus plantillas. Las ramas nuevas aparecen automáticamente en el menú y muestran sus hijos y productos. Una categoría previamente inactiva sigue ocultando sus descendientes; la carga no la reactiva.

## Seguridad de datos y operación local

La carga es explícita, transaccional e idempotente. No se ejecuta al arrancar Flask ni crea productos, stock, precios o fotografías. Mantiene los registros de origen en la tabla aditiva `category_sources`, separados de las descripciones y créditos existentes. Una fuente de categoría no se presenta como URL exclusiva de un producto.

```bash
# Simular el catálogo en una copia de SQLite en memoria
.venv/bin/python -m flask --app app:create_app load-wavesoccer

# Aplicar en local, con respaldo previo de SQLite
.venv/bin/python -m flask --app app:create_app load-wavesoccer --apply
```

El segundo comando rechaza entornos con `PRODUCTION` activo. La inicialización habitual de Flask conserva sus migraciones anteriores: iniciar esta versión sobre un esquema antiguo sigue ejecutándolas aunque se use el comando de simulación.

Respaldo anterior a esta carga: `data/respaldo_antes_wavesoccer_20261027T045805967409Z.sqlite3`, con permisos 0600 y excluido de Git. Comparación contra ese respaldo: todas las categorías y fuentes anteriores conservadas, todas las tablas de negocio idénticas. SQLite: `integrity_check=ok`, sin errores de claves foráneas. Una segunda simulación devuelve cero categorías nuevas.

## Render y publicación pendiente

Repositorio comprobado mediante el plugin Render, con «My Workspace» autorizado por el propietario: https://github.com/saulcortes788-dev/Jerseysaurios, rama `main`. Servicio: https://dashboard.render.com/web/srv-dbfquld9fdbs739rht40. Commit consultado en estado live: `bb1e1e2ae28461b6445f4f77c553208ee8fbeae2`, coincidente con HEAD local al comenzar. No se cambió el remoto.

Render tiene despliegue automático por commit activado. **Un push a main puede publicar automáticamente:** no se ha hecho commit, push ni despliegue. Los cambios están preparados para revisión; publicar requiere coordinar ese ajuste antes de enviar cambios a main.

Disco confirmado: `jerseysaurios-datos`, 1 GB, montado en `/var/data`, una instancia. El propietario comprobó en la Shell de Render las rutas efectivas:

- DATA_DIR: `/var/data/jerseysaurios`
- DATABASE: `/var/data/jerseysaurios/tienda.sqlite3`
- UPLOAD_FOLDER: `/var/data/jerseysaurios/uploads`

El propietario generó y descargó fuera de Render `jerseysaurios-20261026T201419632798Z.tar.gz`, comprobó gzip y extrajo SQLite en una carpeta temporal: integridad `ok`, referencias sin errores. La carpeta uploads todavía no existía. No se ha ejecutado una restauración en producción.

Los datos de SQLite se excluyen de Git. Subir el código no transferirá las categorías locales al servidor, y el cargador no se ejecuta automáticamente ni permite aplicar en producción. Una futura publicación necesita un procedimiento de carga remota revisado y autorizado; no debe reemplazarse la base del servidor por la base local, porque se perderían cambios posteriores de pedidos/inventario. Obtener un respaldo reciente antes de esa futura carga.

## Archivos y validación

- `negocio/wavesoccer.py`: lector del listado, equivalencias y carga aditiva sin red.
- `negocio/wavesoccer_catalog.json`: las 505 filas del archivo original.
- `negocio/commands.py`: simulación/carga local con respaldo y bloqueo en producción.
- `tests/test_wavesoccer.py`: conservación, equivalencias, navegación de los 172 equipos, temporadas, simulación, idempotencia y reversión.
- `scripts/empaquetar_codigo.py`: incluye el listado original en el paquete de código para su trazabilidad y pruebas.
- `README.md` y este informe: uso y límites de publicación.
- `listado_wavesoccer_nuevo.txt`: archivo fuente del propietario, conservado sin modificaciones; debe incluirse en Git junto con el manifiesto.

La carga cubre el archivo completo. El propio listado no acredita que represente todo el catálogo actual de WaveSoccer ni disponibilidad de mercancía.

Resultado: **39 pruebas aprobadas**, incluyendo navegación de los 172 equipos y ramas de tipos/temporadas. `git diff --check` pasó. No hubo commit, push, cambio de remoto ni operaciones de escritura en Render.

```bash
.venv/bin/python -m unittest discover -s tests -v
```
