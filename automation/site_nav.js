/* Toggles the mobile menu. Every menu link is already in the HTML. */
'use strict';
(function () {
  var nav = document.querySelector('nav.site-nav');
  if (!nav) return;
  var button = nav.querySelector('.site-nav-toggle');
  if (!button) return;
  document.documentElement.classList.add('site-nav-ready');

  function fitPanel() {
    var header = nav.closest('header') || nav.closest('.site-header') || nav.parentNode;
    var menu = document.getElementById('site-nav-menu');
    if (!header || !menu || !header.getBoundingClientRect) return;
    var room = window.innerHeight - header.getBoundingClientRect().bottom;
    if (room > 80) menu.style.maxHeight = room + 'px';
  }

  function setOpen(open) {
    if (open) fitPanel();
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
  window.addEventListener('resize', function () {
    if (nav.classList.contains('is-open')) fitPanel();
  });
})();
/* Shrinks the shared bar after the reader leaves the top of the page. */
(function () {
  var header = document.querySelector('header.site-header');
  if (!header) return;
  function sync() {
    header.classList.toggle('is-compact', window.scrollY > 8);
  }
  sync();
  window.addEventListener('scroll', sync, { passive: true });
})();
/* Header search over the static index. Results are cloned from a template. */
(function () {
  var root = document.querySelector('.site-search');
  if (!root) return;
  var button = root.querySelector('.site-search-toggle');
  var panel = document.getElementById('site-search-panel');
  var input = root.querySelector('input[type="search"]');
  var list = root.querySelector('.site-search-results');
  var status = root.querySelector('.site-search-status');
  var template = document.getElementById('site-search-item');
  if (!button || !panel || !input || !list || !template) return;
  var items = null;
  var loading = false;

  function setOpen(open) {
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) panel.removeAttribute('hidden');
    else panel.setAttribute('hidden', '');
    if (open) input.focus();
  }

  function clearList() {
    while (list.firstChild) list.removeChild(list.firstChild);
  }

  function show(matches) {
    clearList();
    var shown = matches.slice(0, 8);
    for (var i = 0; i < shown.length; i++) {
      var item = shown[i];
      var node = template.content.firstElementChild.cloneNode(true);
      var link = node.querySelector('a');
      link.setAttribute('href', item.url);
      node.querySelector('.site-search-title').textContent = item.title;
      node.querySelector('.site-search-kind').textContent = item.type || '';
      list.appendChild(node);
    }
    if (status) {
      if (!shown.length) status.textContent = 'No matches.';
      else status.textContent = shown.length + (shown.length === 1 ? ' match' : ' matches');
    }
  }

  function filter() {
    var query = input.value.toLowerCase().trim();
    if (!items) return;
    if (!query) {
      clearList();
      if (status) status.textContent = '';
      return;
    }
    var matches = [];
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var hay = (item.title + ' ' + (item.text || '') + ' ' + item.type).toLowerCase();
      if (hay.indexOf(query) !== -1) matches.push(item);
      if (matches.length === 8) break;
    }
    show(matches);
  }

  function ready(data) {
    items = (data && data.items) || [];
    loading = false;
    filter();
  }

  button.addEventListener('click', function () {
    var open = button.getAttribute('aria-expanded') !== 'true';
    setOpen(open);
    if (open && !items && !loading) {
      loading = true;
      if (status) status.textContent = 'Loading search…';
      fetch('/search-index.json')
        .then(function (response) { return response.json(); })
        .then(ready)
        .catch(function () {
          loading = false;
          if (status) status.textContent = 'Search is unavailable.';
        });
    }
  });
  input.addEventListener('input', filter);
  var form = root.querySelector('form');
  if (form) form.addEventListener('submit', function (event) { event.preventDefault(); filter(); });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') setOpen(false);
  });
})();
