'use strict';
document.querySelectorAll('[data-photo]').forEach(button => button.addEventListener('click', () => {
  let main = document.querySelector('#main-photo');
  if (!main) { main = document.createElement('img'); main.id = 'main-photo'; main.alt = document.querySelector('h1').textContent; document.querySelector('.product-main-photo').replaceChildren(main); }
  main.src = button.dataset.photo;
}));
const variant = document.querySelector('#variant-select');
if (variant) {
  const update = () => { const option = variant.selectedOptions[0]; if(option) document.querySelector('#variant-price').textContent = option.dataset.price + ' MXN'; };
  variant.addEventListener('change', update); update();
}

// En teléfonos el árbol y los filtros se abren solo cuando el visitante los solicita.
if (window.matchMedia('(max-width: 760px)').matches) {
  document.querySelectorAll('.category-navigation, .category-filters').forEach(panel => { panel.open = false; });
}
