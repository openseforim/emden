(function () {
  var REPO = 'https://github.com/openseforim/emden';
  var root = document.documentElement, body = document.body;
  function get(k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  // theme: auto / light / paper / dark
  var th = document.getElementById('theme');
  function applyTheme(v) {
    if (v === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', v);
    if (th) th.value = v;
  }
  applyTheme(get('ms-theme', 'auto'));
  if (th) th.addEventListener('change', function () { set('ms-theme', th.value); applyTheme(th.value); });

  // search box: keep the query on the search page
  var q = new URLSearchParams(location.search).get('q');
  document.querySelectorAll('.sform input').forEach(function (i) { if (q) i.value = q; });

  if (!body.classList.contains('reader')) return;
  if (window.innerWidth < 800) document.querySelectorAll('details.pages').forEach(function (d) { d.open = false; });

  // languages
  var btns = document.querySelectorAll('.seg button');
  function view(v) {
    body.classList.remove('view-both', 'view-he', 'view-en');
    body.classList.add('view-' + v);
    btns.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.view === v ? 'true' : 'false'); });
    set('ms-view', v);
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { view(b.dataset.view); }); });
  view(get('ms-view', 'both'));

  // Kahana's notes
  var notes = document.getElementById('opt-notes');
  function applyNotes(on) { body.classList.toggle('no-knotes', !on); notes.checked = on; set('ms-notes', on ? '1' : '0'); }
  notes.addEventListener('change', function () { applyNotes(notes.checked); });
  applyNotes(get('ms-notes', '1') === '1');

  // scan images: load only when the scan view is on
  var scan = document.getElementById('opt-scan');
  function applyScan(on) {
    body.classList.toggle('show-scan', on); scan.checked = on; set('ms-scan', on ? '1' : '0');
    if (on) document.querySelectorAll('.scanimg img[data-src]').forEach(function (im) { im.src = im.dataset.src; im.removeAttribute('data-src'); });
  }
  scan.addEventListener('change', function () {
    var top = document.elementFromPoint(window.innerWidth / 2, 140);
    var sec = top && top.closest ? top.closest('.page') : null;
    applyScan(scan.checked);
    if (sec) sec.scrollIntoView();
  });
  applyScan(get('ms-scan', '0') === '1');

  // "Suggest a correction": prefill a GitHub issue with the page link and any selected words
  document.querySelectorAll('.page').forEach(function (sec) {
    var fix = sec.querySelector('a.fix');
    if (!fix) return;
    function href() {
      var s = window.getSelection();
      var t = s && s.rangeCount && sec.contains(s.anchorNode) ? String(s).replace(/\s+/g, ' ').trim().slice(0, 300) : '';
      var b = 'Page: ' + location.origin + location.pathname + '#' + sec.id + '\n' + (t ? 'Words: "' + t + '"\n' : '') +
        '\nWhat is wrong:\n\nWhat it should be:\n';
      fix.href = REPO + '/issues/new?title=' + encodeURIComponent('[correction] ' + sec.dataset.label + ' (ch. ' + sec.dataset.ch + ')') +
        '&body=' + encodeURIComponent(b);
    }
    href();
    fix.addEventListener('pointerdown', href); fix.addEventListener('focus', href);
  });
})();
