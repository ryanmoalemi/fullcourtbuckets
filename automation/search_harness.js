// Node harness: run the site search engine from site_nav.js against search-index.json.
// Usage: node search_harness.js <root> <query>...  -> JSON [{q, suggestion, top:[{t,u,k}]}]
var fs = require('fs'), path = require('path'), vm = require('vm');
var root = process.argv[2];
var src = fs.readFileSync(path.join(__dirname, 'site_nav.js'), 'utf8');
var stubEl = function () { return null; };
var ctx = { window: {}, document: { querySelector: stubEl, getElementById: stubEl, addEventListener: function () {} },
  localStorage: { getItem: function () { return null; }, setItem: function () {} }, console: console, Date: Date, Math: Math, JSON: JSON,
  fetch: function () { var d = JSON.parse(fs.readFileSync(path.join(root, 'search-index.json'), 'utf8'));
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve(d); } }); } };
ctx.window = ctx; vm.createContext(ctx);
try { vm.runInContext(src, ctx); } catch (e) { /* header-only blocks may need a fuller DOM */ }
ctx.FCBSearch.load().then(function () {
  var out = process.argv.slice(3).map(function (q) {
    var r = ctx.FCBSearch.search(q);
    return { q: q, suggestion: r.suggestion, top: r.results.slice(0, 5).map(function (x) { return { t: x.doc.item.t, u: x.doc.item.u, k: x.doc.item.k }; }) };
  });
  process.stdout.write(JSON.stringify(out));
});
