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
/* Site search: lazy-loaded static index, typo-tolerant ranking, autocomplete,
   recent searches and the /search/ results page. DOM nodes are cloned from templates. */
(function () {
  var INDEX_URL = '/search-index.json';
  var RECENT_KEY = 'fcb-recent-searches';
  var TYPE_LABEL = { Article: 'Articles', Player: 'Players', Team: 'Teams', Owner: 'Owners', Tracker: 'Trackers',
    Data: 'Data pages', Game: 'Games', Couple: 'Couples & relatives', Person: 'People', Page: 'Pages' };
  var FIELD_W = { t: 10, w: 4, k: 3, b: 1 };
  var OPTIONAL = { wnba: 1, the: 1, a: 1, of: 1, and: 1, fcb: 1, 'in': 1, to: 1, for: 1 };
  var docs = null, vocab = null, display = null, loadPromise = null;

  function fold(s) {
    s = String(s || '').toLowerCase();
    if (s.normalize) s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return s.replace(/['\u2019\u2018`]/g, '');
  }
  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + 'y';
    if (w.length > 4 && /(ches|shes|sses|xes)$/.test(w)) return w.slice(0, -2);
    if (w.length > 5 && /ing$/.test(w)) return w.slice(0, -3);
    if (w.length > 4 && /ed$/.test(w) && !/eed$/.test(w)) return w.slice(0, -2);
    if (w.length > 3 && /s$/.test(w) && !/(ss|us|is)$/.test(w)) return w.slice(0, -1);
    return w;
  }
  function tokens(s) { return fold(s).split(/[^a-z0-9]+/).filter(Boolean); }

  function prepare(data) {
    var items = (data && data.items) || [];
    docs = []; vocab = {}; display = {};
    var now = Date.now();
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var f = { t: {}, w: {}, k: {}, b: {} };
      var parts = { t: it.t, w: it.w, k: (it.k || '') + ' ' + (TYPE_LABEL[it.k] || ''), b: (it.b || '') + ' ' + (it.s || '') };
      for (var key in parts) {
        var tk = tokens(parts[key]);
        for (var j = 0; j < tk.length; j++) {
          var st = stem(tk[j]);
          f[key][st] = 1;
          vocab[st] = (vocab[st] || 0) + (key === 't' ? 3 : 1);
        }
      }
      var raw = String(it.t || '').split(/\s+/);
      for (var r = 0; r < raw.length; r++) {
        var clean = raw[r].replace(/^[^\w\u00c0-\u024f]+|[^\w\u00c0-\u024f']+$/g, '');
        var ks = stem(fold(clean).replace(/[^a-z0-9]/g, ''));
        if (ks && !display[ks]) display[ks] = clean;
      }
      var boost = 0;
      if (it.d && (it.k === 'Article' || it.k === 'Tracker' || it.k === 'Game')) {
        var age = (now - Date.parse(it.d + 'T12:00:00')) / 864e5;
        if (age >= 0) boost = 4 * Math.exp(-age / 30);
      }
      if (it.k === 'Team' || it.k === 'Owner' || it.k === 'Tracker' || it.k === 'Data') boost += 1;
      var tt = tokens(it.t).map(stem);
      docs.push({ item: it, f: f, ft: fold(it.t), tt: tt, boost: boost });
    }
  }
  function load() {
    if (!loadPromise) {
      loadPromise = fetch(INDEX_URL).then(function (r) { if (!r.ok) throw new Error('index'); return r.json(); })
        .then(function (data) { prepare(data); return true; });
      loadPromise.catch(function () { loadPromise = null; });
    }
    return loadPromise;
  }

  function edits(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var prev2 = null, prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev.push(j);
    for (i = 1; i <= a.length; i++) {
      cur = [i]; var best = i;
      for (j = 1; j <= b.length; j++) {
        var cost = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a.charAt(i - 1) === b.charAt(j - 2) && a.charAt(i - 2) === b.charAt(j - 1)) v = Math.min(v, prev2[j - 2] + 1);
        cur.push(v); if (v < best) best = v;
      }
      if (best > max) return max + 1;
      prev2 = prev; prev = cur;
    }
    return prev[b.length];
  }
  /* Each query term -> list of [vocabTerm, weight, kind]. kind: e exact, p prefix, f fuzzy. */
  function expand(term, isLast) {
    var out = [], st = stem(term), max = term.length >= 8 ? 2 : (term.length >= 4 ? 1 : 0);
    if (vocab[st]) out.push([st, 1, 'e']);
    if (st !== term && vocab[term]) out.push([term, 1, 'e']);
    for (var v in vocab) {
      if (v === st || v === term) continue;
      if ((isLast || term.length >= 3) && term.length >= 2 && v.indexOf(term) === 0) { out.push([v, isLast ? 0.85 : 0.7, 'p']); continue; }
      if (max && v.charAt(0) === term.charAt(0) || max === 2) {
        var d = edits(st, v, max);
        if (d <= max) out.push([v, d === 1 ? 0.6 : 0.4, 'f']);
      }
    }
    out.sort(function (a, b) { return b[1] - a[1] || vocab[b[0]] - vocab[a[0]]; });
    return out.slice(0, 40);
  }

  function search(query) {
    var q = tokens(query);
    if (!q.length || !docs) return { results: [], terms: [], suggestion: '' };
    var exps = [], required = [];
    for (var i = 0; i < q.length; i++) {
      exps.push(expand(q[i], i === q.length - 1));
      required.push(!OPTIONAL[q[i]] || q.length === 1);
    }
    var phrase = fold(query).trim();
    function run(strict) {
      var res = [];
      for (var d = 0; d < docs.length; d++) {
        var doc = docs[d], score = 0, missing = 0, hits = [];
        for (var t = 0; t < exps.length; t++) {
          var best = 0, bestTerm = '', bestKind = '';
          for (var e = 0; e < exps[t].length; e++) {
            var ex = exps[t][e];
            for (var fk in FIELD_W) {
              if (doc.f[fk][ex[0]]) {
                var s = FIELD_W[fk] * ex[1];
                if (s > best) { best = s; bestTerm = ex[0]; bestKind = ex[2]; }
              }
            }
          }
          if (!best) { if (required[t]) missing++; continue; }
          score += best; hits.push([t, bestTerm, bestKind]);
        }
        if (!score || (strict && missing)) continue;
        if (!strict) score *= Math.pow(0.4, missing);
        if (phrase.length > 2 && doc.ft.indexOf(phrase) !== -1) score += 8;
        if (doc.tt.length && doc.tt.length <= 4) {
          var covered = 0;
          for (var c = 0; c < doc.tt.length; c++) for (var hc = 0; hc < hits.length; hc++) if (hits[hc][1] === doc.tt[c]) { covered++; break; }
          if (covered === doc.tt.length) score += 14;
          else if (covered && (doc.item.k === 'Team' || doc.item.k === 'Owner')) score += 7;
        }
        if (doc.ft.indexOf(fold(q[0])) === 0) score += 2;
        score += doc.boost;
        res.push({ doc: doc, score: score, hits: hits });
      }
      res.sort(function (a, b) { return b.score - a.score || a.doc.item.t.length - b.doc.item.t.length; });
      return res;
    }
    var results = run(true);
    if (!results.length) results = run(false);
    var suggestion = '';
    if (results.length) {
      var top = results[0], fixed = q.slice(), changed = false;
      for (var h = 0; h < top.hits.length; h++) {
        var hit = top.hits[h];
        if (hit[2] === 'f') {
          var hasExact = false;
          for (var x = 0; x < exps[hit[0]].length; x++) if (exps[hit[0]][x][2] !== 'f') hasExact = true;
          if (!hasExact) { fixed[hit[0]] = hit[1]; changed = true; }
        }
      }
      if (changed) {
        var nice = [];
        for (var n = 0; n < fixed.length; n++) nice.push(display[stem(fixed[n])] || display[fixed[n]] || fixed[n]);
        suggestion = nice.join(' ');
      }
    }
    var terms = [];
    for (var m = 0; m < q.length; m++) { terms.push(q[m]); var ss = stem(q[m]); if (ss !== q[m]) terms.push(ss); }
    for (var r = 0; r < results.length && r < 20; r++) for (var hh = 0; hh < results[r].hits.length; hh++) terms.push(results[r].hits[hh][1]);
    return { results: results, terms: terms, suggestion: suggestion };
  }

  /* Highlight: fill node with text, wrapping matched words in cloned <mark>s. */
  var markTpl = document.getElementById('site-search-mark');
  function highlight(node, text, terms) {
    while (node.firstChild) node.removeChild(node.firstChild);
    text = String(text || '');
    var parts = text.split(/([^\s,.;:!?()\u2013\u2014"]+)/);
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i]; if (!p) continue;
      var f = fold(p).replace(/[^a-z0-9]/g, ''), hit = false;
      if (f) for (var t = 0; t < terms.length; t++) {
        var term = terms[t];
        if (term.length >= 2 && (f === term || stem(f) === term || (term.length >= 3 && f.indexOf(term) === 0))) { hit = true; break; }
      }
      if (hit && markTpl) {
        var mk = markTpl.content.firstElementChild.cloneNode(true);
        mk.textContent = p; node.appendChild(mk);
      } else node.appendChild(document.createTextNode(p));
    }
  }

  function recent() { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').slice(0, 6); } catch (e) { return []; } }
  function remember(q) {
    q = String(q || '').trim(); if (q.length < 2) return;
    try {
      var list = recent().filter(function (x) { return x.toLowerCase() !== q.toLowerCase(); });
      list.unshift(q); localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6)));
    } catch (e) {}
  }
  function searchUrl(q) { return '/search/?q=' + encodeURIComponent(q); }

  var itemTpl = document.getElementById('site-search-item');
  var groupTpl = document.getElementById('site-search-group');
  function renderItem(list, it, terms, onPick) {
    var node = itemTpl.content.firstElementChild.cloneNode(true);
    var link = node.querySelector('a');
    link.setAttribute('href', it.u);
    var thumb = node.querySelector('.ss-thumb'), img = node.querySelector('.ss-thumb img');
    if (it.i && img) {
      img.setAttribute('src', it.i);
      if (it.c) { thumb.classList.add('is-person'); img.setAttribute('width', '40'); img.setAttribute('height', '40'); }
    } else if (thumb) { thumb.classList.add('is-empty'); if (img) thumb.removeChild(img); }
    highlight(node.querySelector('.site-search-title'), it.t, terms);
    var sn = node.querySelector('.ss-snippet'); if (sn) highlight(sn, it.s || '', terms);
    var kind = node.querySelector('.site-search-kind');
    var meta = it.k || ''; if (it.d && (it.k === 'Article' || it.k === 'Tracker' || it.k === 'Game')) meta += ' \u00b7 ' + it.d;
    kind.textContent = meta;
    if (onPick) link.addEventListener('click', onPick);
    list.appendChild(node);
    return node;
  }
  function renderGroup(list, label) {
    var g = groupTpl.content.firstElementChild.cloneNode(true); g.textContent = label; list.appendChild(g);
  }
  function grouped(results, limit) {
    var order = [], groups = {};
    for (var i = 0; i < results.length && i < limit; i++) {
      var k = results[i].doc.item.k || 'Page';
      if (!groups[k]) { groups[k] = []; order.push(k); }
      groups[k].push(results[i].doc.item);
    }
    return { order: order, groups: groups };
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  /* ---------- Header dropdown ---------- */
  var root = document.querySelector('.site-search');
  if (root && itemTpl) (function () {
    var button = root.querySelector('.site-search-toggle');
    var panel = document.getElementById('site-search-panel');
    var input = root.querySelector('input[type="search"]');
    var list = root.querySelector('.site-search-results');
    var status = root.querySelector('.site-search-status');
    var dym = root.querySelector('.ss-dym');
    var all = root.querySelector('.ss-all');
    var form = root.querySelector('form');
    if (!button || !panel || !input || !list) return;
    var active = -1, timer = null;

    function links() { return list.querySelectorAll('a'); }
    function setActive(i) {
      var ls = links(); if (!ls.length) { active = -1; return; }
      if (i < 0) i = ls.length - 1; if (i >= ls.length) i = 0;
      for (var j = 0; j < ls.length; j++) { ls[j].parentNode.classList.toggle('is-active', j === i); ls[j].parentNode.setAttribute('aria-selected', j === i ? 'true' : 'false'); }
      active = i; ls[i].scrollIntoView({ block: 'nearest' });
    }
    function setOpen(open) {
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) { panel.removeAttribute('hidden'); input.focus(); start(); } else panel.setAttribute('hidden', '');
    }
    function start() {
      if (docs) return update();
      if (status) status.textContent = 'Loading search\u2026';
      load().then(update, function () { if (status) status.textContent = 'Search is unavailable.'; });
    }
    function showRecent() {
      var rs = recent();
      if (!rs.length) return;
      renderGroup(list, 'Recent searches');
      for (var i = 0; i < rs.length; i++) renderItem(list, { t: rs[i], u: searchUrl(rs[i]), k: 'Recent search' }, [], null);
    }
    function update() {
      clear(list); active = -1;
      if (dym) dym.setAttribute('hidden', '');
      if (all) all.setAttribute('hidden', '');
      var query = input.value.trim();
      input.setAttribute('aria-expanded', 'false');
      if (!query) { if (status) status.textContent = ''; showRecent(); return; }
      if (!docs) return;
      var out = search(query);
      var res = out.results;
      if (out.suggestion && dym && fold(out.suggestion) !== fold(query)) {
        var a = dym.querySelector('a'); a.textContent = out.suggestion; a.setAttribute('href', searchUrl(out.suggestion));
        dym.removeAttribute('hidden');
      }
      if (!res.length) { if (status) status.textContent = 'No matches. Try fewer words.'; return; }
      var g = grouped(res, 8);
      for (var i = 0; i < g.order.length; i++) {
        renderGroup(list, TYPE_LABEL[g.order[i]] || g.order[i]);
        for (var j = 0; j < g.groups[g.order[i]].length; j++) renderItem(list, g.groups[g.order[i]][j], out.terms, function () { remember(input.value); });
      }
      input.setAttribute('aria-expanded', 'true');
      if (status) status.textContent = res.length + (res.length === 1 ? ' result' : ' results');
      if (all) { all.setAttribute('href', searchUrl(query)); all.textContent = res.length === 1 ? 'See the result' : 'See all ' + res.length + ' results'; all.removeAttribute('hidden'); }
    }
    button.addEventListener('click', function () { setOpen(button.getAttribute('aria-expanded') !== 'true'); });
    input.addEventListener('focus', start);
    input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(update, 60); });
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); setActive(active + 1); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); setActive(active - 1); }
      else if (ev.key === 'Escape') { ev.preventDefault(); setOpen(false); button.focus(); }
    });
    if (form) form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var ls = links(), q = input.value.trim();
      if (active >= 0 && ls[active]) { remember(q); window.location.href = ls[active].getAttribute('href'); return; }
      if (q) { remember(q); window.location.href = searchUrl(q); }
    });
    if (dym) dym.addEventListener('click', function (ev) {
      var a = dym.querySelector('a'); if (!a || !docs) return; ev.preventDefault(); input.value = a.textContent; update(); input.focus();
    });
    document.addEventListener('keydown', function (ev) {
      var tag = (ev.target && ev.target.tagName) || '';
      if (ev.key === '/' && !ev.ctrlKey && !ev.metaKey && !/INPUT|TEXTAREA|SELECT/.test(tag) && !(ev.target && ev.target.isContentEditable)) {
        ev.preventDefault();
        var pageInput = document.getElementById('sp-q');
        if (pageInput) { pageInput.focus(); pageInput.select(); } else setOpen(true);
      } else if (ev.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') setOpen(false);
    });
    document.addEventListener('click', function (ev) {
      if (button.getAttribute('aria-expanded') === 'true' && !root.contains(ev.target)) setOpen(false);
    });
  })();

  /* ---------- /search/ results page ---------- */
  var page = document.getElementById('search-page');
  if (page && itemTpl) (function () {
    var input = document.getElementById('sp-q');
    var form = document.getElementById('sp-form');
    var status = document.getElementById('sp-status');
    var dym = document.getElementById('sp-dym');
    var list = document.getElementById('sp-results');
    var timer = null;
    var params = new URLSearchParams(window.location.search);
    input.value = params.get('q') || '';
    function render(push) {
      var q = input.value.trim();
      clear(list); dym.setAttribute('hidden', '');
      var url = q ? searchUrl(q) : '/search/';
      if (push) history.replaceState(null, '', url);
      document.title = (q ? q + ' \u2013 ' : '') + 'Search | Full Court Buckets';
      if (!q) {
        status.textContent = 'Search players, teams, owners, trackers and stories.';
        var rs = recent();
        if (rs.length) { renderGroup(list, 'Recent searches'); for (var r = 0; r < rs.length; r++) renderItem(list, { t: rs[r], u: searchUrl(rs[r]), k: 'Recent search' }, [], null); }
        return;
      }
      var out = search(q), res = out.results;
      if (out.suggestion && fold(out.suggestion) !== fold(q)) {
        var a = dym.querySelector('a'); a.textContent = out.suggestion; a.setAttribute('href', searchUrl(out.suggestion)); dym.removeAttribute('hidden');
      }
      status.textContent = res.length ? res.length + (res.length === 1 ? ' result' : ' results') + ' for \u201c' + q + '\u201d' : 'No results for \u201c' + q + '\u201d.';
      var g = grouped(res, 200);
      for (var i = 0; i < g.order.length; i++) {
        var k = g.order[i];
        renderGroup(list, (TYPE_LABEL[k] || k) + ' (' + g.groups[k].length + ')');
        for (var j = 0; j < g.groups[k].length; j++) renderItem(list, g.groups[k][j], out.terms, function () { remember(q); });
      }
    }
    status.textContent = 'Loading search\u2026';
    load().then(function () { render(false); if (input.value.trim()) remember(input.value); },
      function () { status.textContent = 'Search is unavailable.'; });
    input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(function () { if (docs) render(true); }, 80); });
    form.addEventListener('submit', function (ev) { ev.preventDefault(); remember(input.value); if (docs) render(true); });
    dym.addEventListener('click', function (ev) {
      var a = dym.querySelector('a'); if (!docs) return; ev.preventDefault(); input.value = a.textContent; remember(input.value); render(true);
    });
  })();

  window.FCBSearch = { load: load, search: function (q) { return search(q); }, stem: stem, fold: fold };
})();
/* Now bar staleness guard: after data-expires, show the evergreen fallback link. */
(function(){var bar=document.querySelector('.fcb-now');if(!bar)return;var exp=Date.parse(bar.getAttribute('data-expires')||'');
if(!isNaN(exp)&&Date.now()>=exp){var a=bar.querySelector('.ticker-text a');if(a){a.textContent=bar.getAttribute('data-fallback-text');a.setAttribute('href',bar.getAttribute('data-fallback-url'));}}})();
