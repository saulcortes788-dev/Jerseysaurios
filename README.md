# Jerseysaurios · Tienda y administración local

Aplicación en español con Python, Flask, SQLite, HTML, CSS y JavaScript. Para publicarla permanentemente, consulta [PUBLICAR_EN_RENDER.md](PUBLICAR_EN_RENDER.md). Diseño azul y blanco adaptable a teléfonos y computadoras. Conserva los módulos anteriores de ventas directas, gastos, clientes, inventario y reportes.

## 1. Iniciar en Linux

Requiere Python 3.10 o posterior. Abre una terminal y ejecuta:

```bash
cd /home/azulsaurio/Descargas/control_negocio
bash iniciar.sh
```

La primera instalación necesita Internet para instalar Flask y Pillow. El script crea o reutiliza `.venv`. Si tu distribución no incluye venv, en Debian/Ubuntu instala `sudo apt install python3-venv`.

Abre en el navegador:

- **Tienda pública:** http://127.0.0.1:5000/
- **Administración:** http://127.0.0.1:5000/admin
- **Catálogo público:** http://127.0.0.1:5000/tienda/catalogo
- **Carrito:** http://127.0.0.1:5000/carrito
- **Categorías públicas:** http://127.0.0.1:5000/categorias
- **Administrar jerarquía:** http://127.0.0.1:5000/admin/categorias

En el primer acceso administrativo se pide crear usuario y contraseña de al menos 10 caracteres. No hay contraseña predeterminada. Si ya creaste tu administrador, utiliza las mismas credenciales.

Detén la aplicación con **Ctrl+C**. Para volver a abrirla, ejecuta nuevamente `bash iniciar.sh`.

Si ya tenías una versión ejecutándose, detén esa instancia y vuelve a iniciarla para cargar el código nuevo. Si el puerto 5000 está ocupado, puedes usar:

```bash
bash iniciar.sh 5001
```

En ese caso abre http://127.0.0.1:5001/ y http://127.0.0.1:5001/admin. La aplicación escucha solo en esta computadora.

Instalación manual:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## 2. Preparar tu tienda

1. **Configurar tienda:** introduce el nombre, texto del banner y número de WhatsApp con código de país, solo dígitos (por ejemplo, 52 seguido de tu número mexicano de 10 dígitos). No se envían mensajes automáticamente.
2. **Categorías:** administra una jerarquía de niveles libres. La carga inicial incluye las 30 categorías solicitadas, desde Mundial 2026 hasta Accesorios, y conserva las categorías anteriores con sus imágenes y créditos. Puedes crear ramas por equipo/selección, temporada y tipo, moverlas, ordenarlas, activarlas o desactivarlas. No se instalan fotos ni logotipos de terceros.
3. **Productos:** registra SKU, nombre, equipo, selección, liga, categoría, talla, marca, temporada, versión jugador/aficionado, equipación local/visitante/tercera, costo, precio de venta, stock y mínimo. Marca Destacado, Novedad u Oferta para mostrarlo en las secciones correspondientes.
4. **Editar ficha y foto:** cambia datos descriptivos y foto principal. Desde la misma ficha puedes añadir imágenes a la galería con origen, créditos y declaración de autorización.
5. **Variantes:** crea S, M, L, XL y XXL desde la ficha, cada una con SKU y stock independientes. El código de modelo compartido las agrupa en una tarjeta pública. Se copian los datos y precios iniciales del modelo; después cada variante se puede modificar en Productos.
6. **Inventario:** revisa existencias por talla, alertas y valoración al costo. En Productos se muestra margen estimado por unidad (precio menos costo). Retirar/eliminar un producto lo oculta de la tienda sin borrar su historial; puedes reactivarlo.

El precio público de una tarjeta agrupada es el mínimo de sus variantes mostradas; la ficha detalla el precio y stock exactos de cada talla. La búsqueda pública combina nombre/SKU/equipo, liga, selección, talla, categoría e intervalo de precios en MXN.

## 3. Probar el flujo de compra

1. Abre la tienda en una ventana privada para probar como visitante.
2. Busca un producto, abre su ficha, selecciona talla/cantidad y agrégalo al carrito.
3. Cambia las cantidades o usa 0 para retirar un artículo.
4. Captura nombre y teléfono y confirma el pedido. El servidor verifica precio y stock nuevamente, reserva las piezas y crea un pedido **pendiente**. Un doble envío del mismo formulario no crea pedidos adicionales.
5. Se muestra un enlace privado de consulta con un token aleatorio. No publica datos personales. Con WhatsApp configurado, aparece un botón que abre un mensaje preparado con el resumen; el visitante decide enviarlo.
6. En **Pedidos**, registra pagos realmente recibidos por efectivo, transferencia u otro medio. Puedes registrar pagos parciales, sin superar el saldo. No se capturan ni procesan datos de tarjetas.
7. Cuando se completa el importe, el estado cambia a **pagado** y se registran las ventas con el precio y costo guardados al pedir. No se vuelve a descontar inventario.
8. Cambia el estado de pagado a **enviado** y después **entregado**.

Cancelar un pedido sin pagos repone las piezas una sola vez. Si ya tiene pagos, el administrador debe confirmar que realizó el reembolso por fuera del sistema, registrar una referencia y haber recibido la mercancía antes de reponerla. Se conserva un registro de reembolso y las ventas quedan anuladas para los reportes. El programa no envía dinero ni verifica transferencias.

Los pedidos pendientes reservan stock **sin vencimiento automático**. Revísalos y cancela los que no se concreten. El total del pedido corresponde a productos; envío y condiciones se acuerdan con la tienda. Un pedido gratuito se confirma como pagado desde su estado, sin inventar un pago positivo.

## 4. Clientes, ventas y resultados

- **Clientes:** registro, búsqueda por nombre/teléfono/correo y acceso a su historial de pedidos y compras. Los datos de contacto de la tienda permanecen en administración.
- **Ventas:** se conservan las ventas directas anteriores y su exportación CSV. Los pedidos pagados aparecen también en el historial, identificados por folio de pedido; los cancelados se indican como anulados. No vuelvas a capturar una venta directa para un pedido que ya pagaste.
- **Dashboard:** ingresos reconocidos, gastos, costo vendido conocido, utilidad estimada, productos más vendidos y alertas de stock.
- **Reportes:** filtro de fechas inclusivas. Ingresos menos costos históricos menos gastos operativos. Los pedidos pendientes y sus anticipos no se reconocen como venta hasta completar el pago. Las ventas anuladas se excluyen del período original; el reporte es de resultados, no un estado de flujo de efectivo.
- Si faltan costos históricos, la utilidad es **provisional** y puede estar sobreestimada. No se recalcula el pasado al modificar un costo actual. No dupliques compras de mercancía como gasto operativo cuando ya se reflejan en el costo de venta.

## 5. Importación autorizada de fotos y categorías

La extracción automática y las descargas remotas están **desactivadas**, incluso si previamente se proporcionó un álbum de Yupoo. El módulo anterior se conserva en el respaldo; la ruta de extracción solo informa que deben revisarse la nueva fuente y sus permisos antes de desarrollar un conector.

En **Importar productos** puedes:

- Capturar un producto manualmente y subir una foto local.
- Guardar URL de origen, URL de imagen y créditos originales, sin visitar ni descargar esa URL.
- Importar un CSV UTF-8 con productos/categorías y referencias de imágenes.
- Importar imágenes locales referenciadas por el CSV: coloca los archivos en `data/importaciones/` y usa su ruta relativa en la columna `image_file`. Las rutas fuera de esa carpeta se rechazan.

Se solicita declarar autorización para usar el contenido. El sistema conserva las referencias y créditos y los muestra junto a las fotos del producto; no elude accesos ni elimina marcas de agua de la imagen. Las fotografías se validan y generan una copia JPEG de hasta 1400 × 1400, sin modificar tus archivos originales. Se conserva una copia original sin modificar en el subdirectorio `.originales/` junto a cada grupo de imágenes (no accesible públicamente), y la copia JPEG conserva los campos EXIF de autor, descripción y copyright cuando existen. Completa además el campo Créditos para mostrarlos junto a la imagen en la tienda.

Plantilla vacía: `static/plantilla_importacion.csv`. Columnas obligatorias: `sku,name,price`. Opcionales: `description,category,team,selection,league,season,brand,size,model_key,stock,cost,minimum_stock,source_url,image_url,image_file,credit`.

Máximo 500 filas y 1 MB por CSV. La importación completa se revierte si una fila falla o repite un SKU. Las categorías del CSV se crean si no existen; sus imágenes de portada se editan en Categorías. Los archivos locales admitidos son JPEG, PNG o WebP, de hasta 20 megapíxeles; los formularios tienen límite total de 8 MB.

## 6. Datos de demostración opcionales

No se agregan productos ni precios ficticios automáticamente. Para probar con una colección claramente identificada:

```bash
.venv/bin/python cargar_demo.py
```

Crea **[DEMOSTRACIÓN] Jersey de prueba**, con tallas DEMO-S a DEMO-XXL, precios ficticios y categoría Demostración. El nombre y descripción indican que no es mercancía real. La carga es idempotente y no reemplaza SKUs existentes. Retira estas variantes desde Productos al terminar las pruebas. No ejecutes este paso si solo quieres trabajar con tu inventario real.

## 7. Estructura y respaldo

```text
app.py                     Punto de entrada
iniciar.sh                 Inicio en Linux; acepta puerto opcional
cargar_demo.py             Datos ficticios, carga opcional explícita
seed_categorias.py         Seed de categorías idempotente, sin red
requirements.txt           Flask y Pillow
negocio/
  __init__.py              Aplicación, SQLite, migraciones y módulos anteriores
  access.py                Administrador, hash, sesiones y límite de intentos
  store.py                 Tienda, navegación pública, carrito, pedidos y pagos
  categories.py            Árbol de categorías, migración, seed y administración
  importer.py              Captura y CSV autorizados, sin red
  media.py                 Validación y almacenamiento de fotos
  sources.py               Adaptador previo conservado, no conectado a extracción
templates/                 Plantillas administrativas
  shop/                    Tienda pública y administración comercial
static/                    CSS, JavaScript y plantilla CSV
tests/                     Pruebas de negocio e integración
data/
  tienda.sqlite3           Base de datos local
  .secret_key              Clave aleatoria local; nunca está en el código
  uploads/productos/<id>/  Fotos nuevas de galería e importación por producto
  importaciones/           Fotos locales de entrada para CSV
backups/antes_tienda/      Código anterior a la tienda pública
backups/antes_jerarquia/   Código y SQLite anteriores al árbol de categorías
```

Las fotografías anteriores siguen funcionando en su ubicación original. La asociación producto/galería y los créditos se guardan en SQLite. Los archivos existentes se conservaron en respaldos de código; las migraciones agregan tablas/columnas y generan un respaldo de la base antes de ampliar las columnas anteriores a esta tienda.

Para un respaldo completo, **detén todas las instancias y copia toda la carpeta `data/`**, incluida la clave y las imágenes. Los respaldos de código no sustituyen el respaldo de datos. No ejecutes versiones antiguas contra la misma base mientras usas la nueva, porque no conocen las reservas y productos retirados.

## 8. Validación y alcance

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas usan SQLite temporal y productos de prueba. Cubren ventas, CSRF, autenticación, variantes, filtros, carrito, stock modificado, pedidos idempotentes, pagos parciales, cancelación/reembolso, reportes, importación sin red y conservación de registros anteriores.

La tienda es pública dentro de la computadora local; administración requiere sesión. Se usan contraseñas con hash, cookies HttpOnly/SameSite, protección CSRF y límite básico de intentos de acceso. No incluye pagos bancarios automáticos, CFDI, impuestos, cálculo de envío, recuperación de contraseña ni publicación en Internet. Para un despliegue público se requiere preparar el servidor y su seguridad; esta versión ejecuta Flask solo en loopback.


## 9. Categorías y subcategorías jerárquicas

La estructura utiliza la tabla SQLite existente `shop_categories`, migrada conservando sus IDs, nombres, imágenes y créditos. Sus campos de organización son `id`, `name` (nombre), `slug`, `parent_id` (categoría superior), `sort_order` (orden) y `active` (estado). Mantiene también descripción propia, imagen, créditos y etiquetas anteriores. `parent_id` referencia la misma tabla: no existe un número fijo de niveles. Se permiten nombres como una temporada o «Local» en distintos equipos; no pueden repetirse el nombre o slug entre hermanos. Se bloquean ciclos tanto en el panel como en SQLite.

La lista inicial procede **de los 30 nombres proporcionados por el propietario**. Las páginas https://wavesoccer.x.yupoo.com/categories y https://wavesoccer.x.yupoo.com/albums devolvieron un error de acceso durante la consulta, por lo que no se verificó ni copió su árbol. No se añadieron equipos ni selecciones atribuidos a WaveSoccer ni se descargaron fotos, descripciones comerciales o logotipos. Las subcategorías existentes provienen exclusivamente de los metadatos del inventario local, incluidos sus productos identificados de demostración.

### Panel y navegación

- En `/admin/categorias`, crea una categoría sin superior para que sea principal, o elige cualquier categoría superior para crear una subcategoría.
- Usa **Editar / mover** para cambiar nombre, slug, categoría superior, orden y estado. Las opciones superiores excluyen la propia categoría y sus descendientes para evitar ciclos.
- Los botones ↑ y ↓ reorganizan una categoría entre sus hermanas. El campo Orden permite una posición manual; los empates se resuelven por ID.
- Desactivar una categoría oculta toda la rama y sus productos, aunque sus hijos sigan marcados activos. Reactivarla restaura la visibilidad de los hijos que estaban activos. No cambia existencias ni borra pedidos.
- Solo se elimina una categoría si no tiene subcategorías ni productos asignados. Primero mueve sus hijos y reasigna los productos, o desactívala para conservarla.
- `/categorias` muestra tarjetas de categorías principales y un menú lateral desplegable. En teléfonos el menú se abre al tocar «Explorar categorías».
- `/categorias/<ruta-de-slugs>` muestra subcategorías, ruta de navegación y productos de toda la rama. Las ramas inactivas devuelven 404 al público. La ficha del producto enlaza a su categoría asignada.
- El catálogo busca por nombre, SKU, equipo, selección, liga, temporada y versión, y permite combinar filtros de estos campos, talla y precio. Se conservan Ofertas, Novedades y las categorías anteriores.

Al cambiar un slug o mover una rama cambia su URL pública; las relaciones de productos se conservan por ID. No hay redirecciones de URLs antiguas en esta versión.

### Conectar productos

Los productos ahora tienen `category_id` como clave foránea. La migración vincula los productos existentes usando únicamente su etiqueta de categoría o liga y sus datos locales de equipo/selección, temporada y equipación; no cambia el texto histórico, SKU, precio ni stock. Los productos sin suficientes datos quedan sin asignación jerárquica, visibles en el catálogo general.

En **Productos → Editar ficha y foto → Categoría jerárquica**, selecciona la rama exacta, o elige organizar con sus datos locales. El mismo selector aparece al registrar productos e importarlos manualmente. Las variantes heredan la categoría de su modelo. El CSV admite la columna opcional `category_id`; sin ella se organiza a partir de sus datos locales.

### Ejecutar el seed varias veces

La migración carga automáticamente la lista inicial una vez. También puedes ejecutarla explícitamente:

```bash
.venv/bin/python seed_categorias.py
.venv/bin/python seed_categorias.py
```

No genera duplicados ni restablece el estado, orden o nombre de categorías ya existentes. Un arranque normal no vuelve a crear categorías que eliminaste desde el panel. Al ejecutar el seed explícitamente, sí se vuelven a añadir categorías iniciales ausentes; si cambiaste tanto nombre como slug ya no puede identificarlas como el mismo registro.

Para organizar únicamente productos que todavía no tienen categoría jerárquica:

```bash
.venv/bin/python seed_categorias.py --vincular-productos
```

Las migraciones son aditivas para productos. El reemplazo de la antigua tabla plana de categorías conserva IDs e imágenes y dispone de respaldo anterior en `backups/antes_jerarquia/tienda.sqlite3`; al detectar el esquema antiguo, la aplicación también crea un archivo SQLite con el prefijo `respaldo_antes_jerarquia_` junto a la base.


## 10. Configuración de publicación en Render

El código incluye `render.yaml`, `wsgi.py` y `gunicorn.conf.py`. Se añadió Gunicorn a `requirements.txt`. El archivo de configuración requiere un servicio de pago con un disco persistente de 1 GB; no crea ni contrata el servicio por sí mismo.

- `JERSEY_ENV=production`: modo de publicación, cookies Secure y creación web de administradores desactivada.
- `JERSEY_DATA_DIR`: carpeta persistente para SQLite, imágenes, entradas CSV y respaldos. En Render: `/var/data/jerseysaurios`.
- `SECRET_KEY`: clave aleatoria de al menos 32 caracteres, generada por Render. En modo local se conserva la clave del archivo `data/.secret_key`.
- `JERSEY_TRUST_PROXY=1`: habilita la lectura de un proxy de confianza para HTTPS e IP. Solo debe usarse detrás del proxy del alojamiento.
- `JERSEY_TRUSTED_HOSTS`: lista opcional de hosts adicionales permitidos; Render aporta su hostname público automáticamente.

La ruta `/salud` comprueba acceso a SQLite sin mostrar información privada. Los productos `DEMO-*` permanecen guardados pero se ocultan en producción. El usuario administrador se crea desde la consola autorizada mediante `python -m flask --app wsgi:app create-admin`.

Para preparar un ZIP de código sin datos privados:

```bash
.venv/bin/python scripts/empaquetar_codigo.py
```

Para un respaldo consistente de datos locales:

```bash
.venv/bin/python -m flask --app app:create_app backup-data
```

El ZIP de código y el respaldo de datos tienen fines distintos. Publicar el ZIP no transfiere automáticamente tus productos, fotos ni ajustes. La transferencia y restauración al servidor se coordinan de forma privada. El proceso completo está descrito en [PUBLICAR_EN_RENDER.md](PUBLICAR_EN_RENDER.md).
