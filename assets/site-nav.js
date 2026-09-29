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

  function setBranch(control, open) {
    var item = control.parentNode;
    if (!item || !item.classList) return;
    item.classList.toggle('is-open', open);
    control.setAttribute('aria-expanded', open ? 'true' : 'false');
    var label = control.querySelector('.site-nav-subtoggle-label');
    var section = control.getAttribute('data-section') || 'submenu';
    if (label) label.textContent = (open ? 'Hide ' : 'Show ') + section + ' menu';
  }

  function closeBranches() {
    var controls = nav.querySelectorAll('.site-nav-subtoggle');
    for (var i = 0; i < controls.length; i++) setBranch(controls[i], false);
  }

  button.addEventListener('click', function () {
    var open = button.getAttribute('aria-expanded') !== 'true';
    if (!open) closeBranches();
    setOpen(open);
  });
  nav.addEventListener('click', function (event) {
    var target = event.target;
    var control = null;
    while (target && target !== nav) {
      if (target.classList && target.classList.contains('site-nav-subtoggle')) {
        control = target;
        break;
      }
      target = target.parentNode;
    }
    if (!control) return;
    var open = control.getAttribute('aria-expanded') !== 'true';
    closeBranches();
    if (open) setBranch(control, true);
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && nav.classList.contains('is-open')) {
      closeBranches();
      setOpen(false);
    }
  });
})();
