/* Copy citation, copy embed code, and the embed panel toggle. */
(function () {
  function markCopied(button) {
    var label = button.getAttribute('data-label');
    if (!label) {
      label = button.textContent;
      button.setAttribute('data-label', label);
    }
    button.textContent = 'Copied!';
    window.clearTimeout(button._copyTimer);
    button._copyTimer = window.setTimeout(function () {
      button.textContent = label;
    }, 2000);
  }

  function fallbackCopy(text, button) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.setAttribute('aria-hidden', 'true');
    area.style.position = 'fixed';
    area.style.left = '-9999px';
    area.style.top = '0';
    document.body.appendChild(area);
    area.focus();
    area.select();
    try { document.execCommand('copy'); } catch (err) {}
    document.body.removeChild(area);
    markCopied(button);
  }

  function copyText(button, text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        markCopied(button);
      }, function () {
        fallbackCopy(text, button);
      });
    } else {
      fallbackCopy(text, button);
    }
  }

  document.addEventListener('click', function (event) {
    var cite = event.target.closest('.fcb-copy-citation');
    if (cite) {
      var box = cite.closest('.fcb-quick-cite');
      var source = box && box.querySelector('.fcb-citation-source');
      copyText(cite, source ? source.value : '');
      return;
    }
    var embedCopy = event.target.closest('.fcb-copy-embed');
    if (embedCopy) {
      var panel = embedCopy.closest('.fcb-embed-panel');
      var area = panel && panel.querySelector('textarea');
      copyText(embedCopy, area ? area.value : '');
      return;
    }
    var toggle = event.target.closest('.fcb-embed-toggle');
    if (!toggle) return;
    var controlled = document.getElementById(toggle.getAttribute('aria-controls'));
    if (!controlled) return;
    var open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
    controlled.hidden = open;
  });
})();
