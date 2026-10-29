# Changelog

## [Sin publicar] — rama `feature/rediseno-v2`

### Añadido
- `Dockerfile`, `.dockerignore`, `docker-compose.yml` (local en :8000, volumen `datos`). *Sin commit.*
- 3 tests en `tests/test_store.py`: límite por IP, pedidos vencidos, caché/categoría inactiva.

### Cambiado (sin commit): rediseño "Deportivo audaz" de la tienda
- `static/shop.css` reescrito: fondo #0b0d0c, acento lima #c6ff00 y naranja #ff5a1f para ofertas; tipografía Anton + Inter (Google Fonts, `display=swap`, fallback de sistema).
- Hero a pantalla completa con titular gigante y franja diagonal; categorías como tiles con letra gigante; tarjetas con etiquetas NUEVO/OFERTA y hover con elevación; ficha con chips de talla y precio enormes.
- Cabecera oscura sticky con carrito destacado (fuera del `nav`), footer oscuro; la tienda ya no carga `style.css` del admin; `shop.js` añade sombra a la cabecera.

### Cambiado (commit `885cdae`)
- **Tienda (frontend):** `static/shop.css` reescrito mobile-first con tokens, modo oscuro y `:focus-visible`; cabecera sticky; tarjetas clicables con `loading="lazy"`; filtros en acordeón; tallas en chips con precio dinámico; CTA fija en móvil; carrito, recibo (ticket) y error renovados.
- **Caché:** `static` e imágenes públicas → `public, max-age=604800`; tienda → `no-cache`; admin/carrito → `no-store`.

### Seguridad / correcciones
- Checkout: máx. 5 pedidos por IP cada 10 min (429).
- Pedidos `pendiente` sin pago > 48 h se cancelan y reponen stock (`release_stale_orders`).
- Login: `failures` se poda y se limita a 1000 entradas.
- `/imagenes/`: categorías inactivas ya no se sirven.
- Eliminado `__main__` duplicado en `negocio/__init__.py`.
