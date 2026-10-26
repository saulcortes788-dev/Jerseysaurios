# Publicar Jerseysaurios permanentemente en Render

Estado: el proyecto está preparado y probado localmente con Gunicorn. Este archivo no confirma que exista un servicio publicado. Para realizar el despliegue debes conectar tu cuenta de Render y autorizar su acceso al repositorio del proyecto.

## Qué se publicará

- Aplicación Flask existente, con categorías, catálogo, administración, pedidos y reportes.
- Un servicio Python con Gunicorn, una instancia y un worker con cuatro threads.
- Un disco persistente de 1 GB montado en `/var/data`.
- SQLite y las fotos en `/var/data/jerseysaurios`, fuera del código que se reemplaza al desplegar.
- HTTPS proporcionado por el alojamiento y cookies seguras.
- Una clave de sesión aleatoria generada por Render, nunca escrita en el repositorio.

El archivo `render.yaml` contiene esta configuración. Crear el servicio genera cargos en Render; el importe definitivo debe revisarse en su pantalla de contratación. La configuración utiliza el identificador actual del plan básico `0.5c-512mb`.

Referencias oficiales: [Flask en Render](https://render.com/docs/deploy-flask), [discos persistentes](https://render.com/docs/disks), [precios](https://render.com/pricing), [BluePrints](https://render.com/docs/blueprint-spec).

## Camino recomendado: conectar Render

1. Crea tu cuenta en https://dashboard.render.com/ si todavía no la tienes.
2. Instala y conecta la integración Render en esta conversación, entrando en tu propia cuenta cuando te lo solicite.
3. Una vez conectada, se podrá revisar tu espacio de trabajo y continuar la publicación. La conexión de una cuenta no implica que se haya creado ya el servidor.
4. Si Render necesita acceso al código, autoriza únicamente el repositorio privado de Jerseysaurios que se usará para el despliegue. No subas la carpeta `data/`, claves ni respaldos a GitHub.

Si prefieres realizar la publicación desde el navegador, sigue el procedimiento manual de abajo. No es necesario comprar un dominio para obtener el primer enlace de Render.

## Procedimiento manual desde el navegador

### A. Preparar el código

Se genera un ZIP que contiene solo el código y configuración de publicación:

```bash
cd /home/azulsaurio/Descargas/control_negocio
.venv/bin/python scripts/empaquetar_codigo.py
```

Resultado: `dist/jerseysaurios-codigo.zip`. Excluye la base de datos, imágenes subidas, usuarios, claves, `.venv`, respaldos y archivos de entorno reales. Las pruebas de migración llevan sus esquemas de prueba y no necesitan tus respaldos.

1. Crea un repositorio privado de GitHub para el proyecto.
2. Extrae el ZIP en una carpeta aparte.
3. Sube su contenido a la raíz del repositorio mediante **Add file → Upload files**. El archivo `render.yaml` debe estar en la raíz del repositorio; no subas el ZIP como un único archivo.
4. No subas `data/` ni `backups/`. La información real se transfiere aparte al disco del servidor, de forma privada.

### B. Crear el servicio

1. En Render, entra en **New → Blueprint**.
2. Conecta el repositorio privado del proyecto.
3. Render detectará `render.yaml`: revisa el servicio `jerseysaurios`, su plan básico y el disco de 1 GB.
4. Comprueba el importe mostrado por Render antes de confirmar la creación.
5. Espera a que el despliegue figure como **Live**. Render proporcionará el enlace asignado al servicio. El nombre exacto depende de su disponibilidad: no debe suponerse que `jerseysaurios.onrender.com` esté libre.

El disco no está disponible en la fase de construcción: por eso solo se instalan dependencias al construir, y SQLite se inicializa cuando arranca el servicio.

### C. Crear tu administrador de forma privada

En producción `/configurar` está desactivado para impedir que un visitante reclame la primera cuenta. Usa la pestaña **Shell** del servicio en Render:

```bash
python -m flask --app wsgi:app create-admin
```

Introduce un usuario y una contraseña de al menos 12 caracteres cuando se soliciten. La contraseña se escribe de forma oculta y se guarda con hash. No se pone en el código ni en el historial de comandos.

Si la base importada ya tiene tu administrador, no crees otro: utiliza sus credenciales. Para cambiar una contraseña desde la consola autorizada:

```bash
python -m flask --app wsgi:app reset-admin-password
```

Después entra en `https://EL-ENLACE-ASIGNADO/admin` y configura nombre de tienda, WhatsApp y contenido. El catálogo funciona aunque todavía no se haya creado el administrador; la administración devolverá 503 hasta que esté configurada.

### D. Conservar o transferir el catálogo actual

El ZIP de código no contiene los datos reales. Un servidor recién creado tendrá la estructura y categorías iniciales, pero no las fotos, productos o ajustes que solo existen en tu computadora.

Para crear una copia consistente de SQLite y todas las imágenes desde Linux:

```bash
cd /home/azulsaurio/Descargas/control_negocio
.venv/bin/python -m flask --app app:create_app backup-data
```

El comando muestra el nombre de un archivo `.tar.gz` dentro de `data/respaldos/`. Es un archivo privado: puede contener datos de clientes y hashes de acceso. No se incluye en el ZIP de código ni debe subirse a un repositorio.

La transferencia al disco persistente se realiza mediante el acceso privado del proveedor (SSH/SCP o el método admitido por Render). Antes de sustituir una base existente hay que hacer respaldo, detener las escrituras y coordinar la restauración; no extraigas un respaldo encima de SQLite mientras la aplicación recibe pedidos. Este proyecto no restaura archivos recibidos automáticamente ni sobrescribe datos del servidor al desplegar código.

[Transferencia de archivos y discos](https://render.com/docs/disks#transferring-files) · [Acceso Shell/SSH](https://render.com/docs/ssh).

## Comprobar después del despliegue

1. Abre el enlace HTTPS desde tu teléfono usando datos móviles: así verificas que no depende de tu computadora ni de su Wi-Fi.
2. Visita `/salud`: debe responder `{"status":"ok"}`.
3. Comprueba `/categorias` y el catálogo público sin iniciar sesión.
4. Verifica que `/configurar` no permita crear cuentas desde el navegador.
5. Inicia sesión en `/admin`, agrega un producto real y sube una foto.
6. Reinicia el servicio desde Render y verifica que ese producto y su foto sigan disponibles: comprueba que el disco esté conectado y que `JERSEY_DATA_DIR` apunte dentro de él.
7. Prueba un pedido y su pago manual antes de compartir el enlace con clientes.

Los SKUs `DEMO-*` no se muestran ni se pueden pedir en producción. Siguen guardados y disponibles en tu copia local; no se borran. Para publicar mercancía real debes registrar sus datos reales.

## Respaldos de producción

Desde Shell de Render:

```bash
python -m flask --app wsgi:app backup-data
```

Genera un respaldo consistente con la API de SQLite y copia las fotografías, incluidos los originales y créditos. El archivo tiene permisos privados. Descárgalo periódicamente y guarda una copia fuera de Render; los respaldos en el mismo disco no bastan frente a la pérdida de ese disco. La clave de sesión de Render se conserva en sus variables de entorno, no se vuelca en el respaldo.

La programación automática y la retención de copias no se activan en este cambio. Deben configurarse con la cuenta de alojamiento disponible. No restaures una imagen de disco como sustituto de un respaldo consistente de SQLite.

## Dominio propio y actualización

Puedes comenzar con el enlace que asigne Render. El dominio propio se contrata aparte y se conecta posteriormente. Cuando añadas un dominio, incluye su nombre en `JERSEY_TRUSTED_HOSTS` si se activa la lista de hosts permitidos. Render configura su hostname público mediante `RENDER_EXTERNAL_HOSTNAME` y la aplicación lo acepta automáticamente.

Subir cambios al repositorio despliega código nuevo; la base y las fotos deben seguir en el disco persistente. Esta configuración mantiene una sola instancia: no actives varias instancias o workers sin revisar primero SQLite y el control de intentos de acceso.
