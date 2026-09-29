/* Toggles the mobile menu. Every menu link is already in the HTML. */
'use strict';
(function () {
  var nav = document.querySelector('nav.site-nav');
  if (!nav) return;
  var button = nav.querySelector('.site-nav-toggle');
  if (!button) return;
  document.documentElement.classList.add('site-nav-ready');

  function setOpen(open) {
    nav.classList.toggle('is-open', open);
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    var label = button.querySelector('.site-nav-toggle-label');
    if (label) label.textContent = open ? 'Close' : 'Menu';
  }

  button.addEventListener('click', function () {
    setOpen(button.getAttribute('aria-expanded') !== 'true');
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && nav.classList.contains('is-open')) setOpen(false);
  });
})();
