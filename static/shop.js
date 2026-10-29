'use strict';
// Galería de la ficha: cambia la foto principal y marca la miniatura activa.
const thumbs = document.querySelectorAll('[data-photo]');
thumbs.forEach(button => button.addEventListener('click', () => {
  let main = document.querySelector('#main-photo');
  if (!main) {
    main = document.createElement('img');
    main.id = 'main-photo';
    main.alt = document.querySelector('h1').textContent.trim();
    document.querySelector('.product-main-photo').replaceChildren(main);
  }
  main.src = button.dataset.photo;
  thumbs.forEach(other => other.setAttribute('aria-pressed', String(other === button)));
}));

// Selector de talla: el precio sigue a la variante elegida.
const price = document.querySelector('#variant-price');
if (price) {
  const sizes = document.querySelectorAll('input[name="product_id"][data-price]');
  const update = () => {
    const chosen = document.querySelector('input[name="product_id"][data-price]:checked');
    if (chosen) price.textContent = chosen.dataset.price + ' MXN';
  };
  sizes.forEach(input => input.addEventListener('change', update));
  update();
}

// En teléfonos el árbol y los filtros se abren solo cuando el visitante los solicita.
if (window.matchMedia('(max-width: 899px)').matches) {
  document.querySelectorAll('.category-navigation, .category-filters').forEach(panel => { panel.open = false; });
}

// El enlace activo de la navegación queda visible cuando la barra se desplaza en móvil.
document.querySelector('.shop-header nav [aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'center' });

// La cabecera fija gana sombra al desplazarse.
const header = document.querySelector('.shop-header');
if (header) {
  const onScroll = () => header.classList.toggle('is-scrolled', window.scrollY > 8);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}
