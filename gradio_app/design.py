from __future__ import annotations

DESIGN_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-canvas@0.5.0/lib/xterm-addon-canvas.js"></script>
<script>
(function() {
  function mount() {
    var el = document.getElementById('mm-terminal');
    if (!el || el.dataset.mmMounted === 'true') return;
    if (typeof Terminal === 'undefined' || typeof FitAddon === 'undefined' || typeof CanvasAddon === 'undefined') {
      setTimeout(mount, 100);
      return;
    }
    el.dataset.mmMounted = 'true';

    var term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily: '"Geist Mono", ui-monospace, SFMono-Regular, Consolas, monospace',
      fontSize: 13,
      theme: {
        background: '#0F1115',
        foreground: '#FFFFFF',
        cursor: '#FFFFFF',
        cursorAccent: '#0F1115',
        selectionBackground: 'rgba(78,140,255,0.45)',
        black: '#1A1D24',
        red: '#FF6B6B',
        green: '#7FE38C',
        yellow: '#FFD479',
        blue: '#7FB3FF',
        magenta: '#D9A0FF',
        cyan: '#8FE6FF',
        white: '#FFFFFF',
        brightBlack: '#7A8597',
        brightRed: '#FF9090',
        brightGreen: '#A4F0AB',
        brightYellow: '#FFE5A6',
        brightBlue: '#A8CCFF',
        brightMagenta: '#E6BEFF',
        brightCyan: '#B5EEFF',
        brightWhite: '#FFFFFF'
      }
    });
    var fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(el);
    try { term.loadAddon(new CanvasAddon.CanvasAddon()); } catch (e) {}
    function safeFit() { try { fit.fit(); } catch (e) {} }
    safeFit();
    setTimeout(safeFit, 50);
    setTimeout(safeFit, 250);
    setTimeout(safeFit, 800);
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(function() { safeFit(); sendResize(); }).observe(el);
    }

    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(proto + '//' + window.location.host + '/ws/terminal');
    ws.binaryType = 'arraybuffer';

    function sendResize() {
      if (!ws || ws.readyState !== 1) return;
      ws.send(JSON.stringify({type: 'resize', rows: term.rows, cols: term.cols}));
    }

    ws.onopen = function() { sendResize(); term.focus(); };
    ws.onmessage = function(ev) {
      if (typeof ev.data === 'string') term.write(ev.data);
      else term.write(new Uint8Array(ev.data));
    };
    ws.onclose = function() { term.write('\\r\\n\\x1b[31m[connection closed]\\x1b[0m\\r\\n'); };
    ws.onerror = function() { term.write('\\r\\n\\x1b[31m[connection error — is the FastAPI server running?]\\x1b[0m\\r\\n'); };

    term.onData(function(data) {
      if (ws.readyState === 1) ws.send(JSON.stringify({type: 'input', data: data}));
    });

    var rT;
    window.addEventListener('resize', function() {
      clearTimeout(rT);
      rT = setTimeout(function() { try { fit.fit(); } catch (e) {} sendResize(); }, 80);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  }
  setTimeout(mount, 50);
  setTimeout(mount, 400);
  setTimeout(mount, 1200);
  var mo = new MutationObserver(function() { mount(); });
  mo.observe(document.documentElement, {childList: true, subtree: true});
})();
</script>
<script>
(function() {
  var KIND_GLYPH = { image: '◧', video: '▶', audio: '♪', pdf: '◫', text: 'T', other: '·' };

  function fmtSize(n) {
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
    return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, function(c) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  }

  var state = { files: [], selected: null, root: '' };

  function setOpen(open) {
    var modal = document.getElementById('mm-fv-modal');
    if (!modal) return;
    modal.classList.toggle('mm-fv-open', !!open);
    document.body.style.overflow = open ? 'hidden' : '';
    if (open && state.files.length === 0) loadFiles();
  }

  function loadFiles() {
    var listEl = document.getElementById('mm-fv-list');
    if (listEl) listEl.innerHTML = '<div class="mm-fv-empty">Loading…</div>';
    fetch('/api/files').then(function(r) { return r.json(); }).then(function(data) {
      state.files = data.files || [];
      state.root = data.root || '';
      if (state.files.length > 0 && !state.selected) {
        state.selected = state.files[0];
        renderList();
        renderPreview(state.selected);
      } else {
        renderList();
      }
    }).catch(function() {
      if (listEl) listEl.innerHTML = '<div class="mm-fv-empty">Failed to load files.</div>';
    });
  }

  function buildTree(files) {
    var root = {};
    files.forEach(function(f) {
      var parts = f.path.split('/');
      var node = root;
      parts.forEach(function(name, i) {
        if (!node[name]) node[name] = { children: {} };
        if (i === parts.length - 1) node[name].file = f;
        node = node[name].children;
      });
    });
    return root;
  }

  function walkTree(node, prefix, lines) {
    var entries = Object.keys(node).map(function(k) {
      return { name: k, file: node[k].file, children: node[k].children };
    });
    entries.sort(function(a, b) {
      var aDir = !a.file, bDir = !b.file;
      if (aDir !== bDir) return aDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    entries.forEach(function(e, i) {
      var last = i === entries.length - 1;
      lines.push({
        entry: e,
        prefix: prefix + (last ? '└── ' : '├── '),
        isFile: !!e.file,
      });
      var childKeys = Object.keys(e.children);
      if (childKeys.length > 0) {
        walkTree(e.children, prefix + (last ? '    ' : '│   '), lines);
      }
    });
  }

  function renderList() {
    var listEl = document.getElementById('mm-fv-list');
    if (!listEl) return;
    if (!state.files.length) {
      listEl.innerHTML = '<div class="mm-fv-empty">No files in mmbench-tiny.</div>';
      return;
    }
    var tree = buildTree(state.files);
    var lines = [];
    walkTree(tree, '', lines);

    var totalBytes = state.files.reduce(function(s, f) { return s + f.size; }, 0);
    var rootName = (state.root || 'mmbench-tiny').split('/').filter(Boolean).pop() || 'mmbench-tiny';
    var html = '<div class="mm-fv-tree-root">' +
                 '<span class="mm-fv-glyph">▾</span>' +
                 '<span class="mm-fv-name">' + escapeHTML(rootName) + '/</span>' +
                 '<span class="mm-fv-size">' + state.files.length + ' files · ' + fmtSize(totalBytes) + '</span>' +
               '</div>';
    lines.forEach(function(line) {
      var prefix = '<span class="mm-fv-tree-prefix">' + escapeHTML(line.prefix) + '</span>';
      if (line.isFile) {
        var f = line.entry.file;
        var sel = state.selected && state.selected.path === f.path ? ' mm-fv-item-selected' : '';
        html += '<div class="mm-fv-item' + sel + '" data-path="' + escapeHTML(f.path) + '">' +
                  prefix +
                  '<span class="mm-fv-glyph">' + KIND_GLYPH[f.kind] + '</span>' +
                  '<span class="mm-fv-name">' + escapeHTML(line.entry.name) + '</span>' +
                  '<span class="mm-fv-size">' + fmtSize(f.size) + '</span>' +
                '</div>';
      } else {
        html += '<div class="mm-fv-tree-dir">' +
                  prefix +
                  '<span class="mm-fv-glyph">▸</span>' +
                  '<span class="mm-fv-name">' + escapeHTML(line.entry.name) + '/</span>' +
                '</div>';
      }
    });
    listEl.innerHTML = html;
    Array.prototype.forEach.call(listEl.querySelectorAll('.mm-fv-item'), function(el) {
      el.addEventListener('click', function() {
        var path = el.getAttribute('data-path');
        var f = state.files.find(function(x) { return x.path === path; });
        if (f) selectFile(f);
      });
    });
  }

  function selectFile(f) {
    state.selected = f;
    renderList();
    renderPreview(f);
  }

  function renderPreview(f) {
    var pv = document.getElementById('mm-fv-preview');
    var meta = document.getElementById('mm-fv-meta');
    var url = '/api/files/raw/' + f.path.split('/').map(encodeURIComponent).join('/');
    meta.innerHTML = '<span class="mm-fv-meta-name">' + escapeHTML(f.path) + '</span>' +
                     '<span class="mm-fv-meta-sep">·</span>' +
                     '<span>' + f.kind + '</span>' +
                     '<span class="mm-fv-meta-sep">·</span>' +
                     '<span>' + fmtSize(f.size) + '</span>';
    if (f.kind === 'image') {
      pv.innerHTML = '<div class="mm-fv-frame mm-fv-frame-center">' +
                       '<img src="' + url + '" alt="" />' +
                     '</div>';
    } else if (f.kind === 'video') {
      pv.innerHTML = '<div class="mm-fv-frame mm-fv-frame-center">' +
                       '<video src="' + url + '" controls></video>' +
                     '</div>';
    } else if (f.kind === 'audio') {
      pv.innerHTML = '<div class="mm-fv-frame mm-fv-frame-center">' +
                       '<audio src="' + url + '" controls></audio>' +
                     '</div>';
    } else if (f.kind === 'pdf') {
      pv.innerHTML = '<iframe class="mm-fv-iframe" src="' + url + '"></iframe>';
    } else if (f.kind === 'text') {
      pv.innerHTML = '<pre class="mm-fv-text">Loading…</pre>';
      fetch(url).then(function(r) { return r.text(); }).then(function(t) {
        pv.innerHTML = '<pre class="mm-fv-text">' + escapeHTML(t) + '</pre>';
      }).catch(function() { pv.innerHTML = '<div class="mm-fv-empty">Failed to load.</div>'; });
    } else {
      pv.innerHTML = '<div class="mm-fv-empty">No inline preview for this file type. ' +
                     '<a href="' + url + '" target="_blank">Open raw →</a></div>';
    }
  }

  function ensureMounted() {
    if (document.getElementById('mm-fv-modal')) return;

    var btn = document.createElement('button');
    btn.id = 'mm-fv-btn';
    btn.type = 'button';
    btn.title = 'Browse mmbench-tiny';
    btn.setAttribute('aria-label', 'Open file browser');
    btn.innerHTML =
      '<span class="mm-fv-btn-icon">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>' +
        '</svg>' +
      '</span>' +
      '<span class="mm-fv-btn-label">File browser</span>';
    btn.addEventListener('click', function() { setOpen(true); });
    document.body.appendChild(btn);

    var modal = document.createElement('div');
    modal.id = 'mm-fv-modal';
    modal.innerHTML =
      '<div class="mm-fv-backdrop"></div>' +
      '<div class="mm-fv-panel" role="dialog" aria-label="File viewer">' +
        '<div class="mm-fv-head">' +
          '<div class="mm-fv-title">Files <span class="mm-fv-subtitle">mmbench-tiny</span></div>' +
          '<button class="mm-fv-close" aria-label="Close">×</button>' +
        '</div>' +
        '<div class="mm-fv-body">' +
          '<aside class="mm-fv-sidebar"><div id="mm-fv-list"></div></aside>' +
          '<main class="mm-fv-main">' +
            '<div id="mm-fv-meta" class="mm-fv-meta"></div>' +
            '<div id="mm-fv-preview" class="mm-fv-preview"></div>' +
          '</main>' +
        '</div>' +
      '</div>';
    document.body.appendChild(modal);
    modal.querySelector('.mm-fv-backdrop').addEventListener('click', function() { setOpen(false); });
    modal.querySelector('.mm-fv-close').addEventListener('click', function() { setOpen(false); });
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') setOpen(false);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureMounted);
  } else {
    ensureMounted();
  }
  setTimeout(ensureMounted, 200);
})();
</script>
<style>
  :root {
    --mm-bg: #F5FAFF;
    --mm-surface: #FFFFFF;
    --mm-surface-tint: #E6EDFC;
    --mm-border: #D5E2F7;
    --mm-border-strong: #AAC2EC;
    --mm-text: #010917;
    --mm-text-secondary: #596983;
    --mm-text-muted: #A29F9F;
    --mm-accent: #1E5ACA;
    --mm-accent-deep: #102955;
    --mm-accent-hover: #2756A8;
    --mm-accent-bright: #4E8CFF;
    --mm-accent-soft: #749ADF;
    --mm-danger: #B23A3A;
    --mm-danger-soft: #FBE7E7;
    --mm-danger-border: #E5B0B0;
    --mm-shadow: 0 1px 2px rgba(1,9,23,0.04), 0 4px 12px rgba(1,9,23,0.04);
    --mm-shadow-sm: 0 1px 2px rgba(1,9,23,0.05);
  }

  .gradio-container {
    max-width: 1080px !important;
    margin: 0 auto !important;
    padding: 18px 24px 56px !important;
    font-family: Geist, Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    font-size: 13px !important;
  }
  gradio-app, gradio-app > .main, gradio-app > div {
    width: 100% !important;
  }

  .gradio-container input[type="checkbox"] {
    appearance: none;
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    margin: 0;
    cursor: pointer;
    background-position: center;
    background-repeat: no-repeat;
    background-size: 12px 12px;
    transition: background-color 0.15s ease, border-color 0.15s ease;
  }
  .gradio-container input[type="checkbox"]:hover {
    border-color: var(--mm-accent-soft) !important;
  }

  .gradio-container label > span,
  .gradio-container .label-wrap > span,
  .gradio-container span.label {
    font-family: Geist, Inter, sans-serif;
    font-size: 11.5px;
    font-weight: 500;
    letter-spacing: 0;
    color: var(--mm-text-secondary);
  }
  .gradio-container .tab-nav button {
    font-family: Geist, Inter, sans-serif;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0;
    color: var(--mm-text-secondary);
  }
  .gradio-container .tab-nav button.selected { color: var(--mm-text); }

  .gradio-container *:focus-visible {
    outline: 2px solid var(--mm-accent-soft);
    outline-offset: 2px;
    border-radius: 6px;
  }

  .gradio-container .table-wrap,
  .gradio-container table {
    background: var(--mm-surface) !important;
    color: var(--mm-text) !important;
    border-color: var(--mm-border) !important;
    font-size: 12.5px !important;
  }
  .gradio-container th, .gradio-container td {
    color: var(--mm-text) !important;
  }
  .gradio-container .tr-head {
    background: var(--mm-surface-tint) !important;
    color: var(--mm-text) !important;
  }
  .gradio-container .tr-head th { color: var(--mm-text) !important; font-weight: 600 !important; }
  .gradio-container .tr-body { background: var(--mm-surface) !important; }
  .gradio-container .tr-body:nth-child(odd) { background: var(--mm-bg) !important; }
  .gradio-container .tr-body:hover { background: var(--mm-surface-tint) !important; }

  .gradio-container .codemirror-wrappper,
  .gradio-container .cm-editor,
  .gradio-container .cm-scroller,
  .gradio-container .cm-content,
  .gradio-container pre {
    background: var(--mm-surface) !important;
    color: var(--mm-text) !important;
    font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace !important;
    font-size: 12.5px !important;
  }
  .gradio-container .cm-line { color: var(--mm-text) !important; }
  .gradio-container .cm-gutters {
    background: var(--mm-bg) !important;
    color: var(--mm-text-secondary) !important;
    border-right: 1px solid var(--mm-border) !important;
  }
  .gradio-container .ͼ1 .tok-string,
  .gradio-container .cm-content .tok-string,
  .gradio-container .cm-content [class*="tok-string"] { color: var(--mm-accent-deep) !important; }
  .gradio-container .cm-content .tok-number,
  .gradio-container .cm-content [class*="tok-number"] { color: var(--mm-accent) !important; }
  .gradio-container .cm-content .tok-keyword,
  .gradio-container .cm-content [class*="tok-keyword"] { color: var(--mm-accent) !important; font-weight: 500; }
  .gradio-container .cm-content .tok-property,
  .gradio-container .cm-content .tok-propertyName,
  .gradio-container .cm-content [class*="tok-property"] { color: var(--mm-text) !important; font-weight: 500; }
  .gradio-container .cm-content .tok-bool,
  .gradio-container .cm-content [class*="tok-bool"] { color: var(--mm-accent) !important; }
  .gradio-container .cm-content .tok-null { color: var(--mm-text-muted) !important; }
  .gradio-container .cm-content .tok-punctuation { color: var(--mm-text-secondary) !important; }

  .mm-header { margin: 12px 2px }
  .mm-h1 {
    font-family: Geist, Inter, sans-serif;
    font-size: 19px;
    line-height: 1.15;
    letter-spacing: -0.01em;
    margin: 0 0 2px;
    color: var(--mm-text);
    font-weight: 600;
  }
  .mm-h1 .mm-h1-mark { color: var(--mm-accent); }
  .mm-sub {
    font-family: Geist, Inter, sans-serif;
    font-size: 12.5px;
    line-height: 1.4;
    color: var(--mm-text-secondary);
    margin: 0;
    font-weight: 400;
  }

  .mm-hero {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    margin: 22px 0 30px;
    padding: 0;
  }
  .mm-hero-logo {
    width: 80px;
    height: 80px;
    display: block;
    margin: 0 auto 12px;
    filter: drop-shadow(0 2px 10px rgba(1, 9, 23, 0.07));
  }
  .mm-hero-title {
    font-family: Geist, Inter, sans-serif;
    font-size: 36px;
    font-weight: 700;
    letter-spacing: -0.025em;
    line-height: 1.05;
    color: var(--mm-text);
    margin: 0 0 6px;
  }

  .mm-section { padding: 2px 2px 10px; }
  .mm-section h2 {
    font-family: Geist, Inter, sans-serif;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: 1.2;
    margin: 0 0 2px;
    color: var(--mm-text);
  }
  .mm-section .mm-note {
    font-family: Geist, Inter, sans-serif;
    font-size: 12.5px;
    color: var(--mm-text-secondary);
    margin: 0;
    font-weight: 400;
  }
  .mm-section code, .gradio-container code {
    font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
    background: var(--mm-surface-tint);
    color: var(--mm-accent-deep);
    padding: 1px 5px;
    border-radius: 5px;
    font-size: 0.88em;
    border: 1px solid var(--mm-border);
  }

  .gradio-container .mm-twocol {
    display: flex;
    flex-direction: row;
    gap: 14px;
    align-items: stretch;
    width: 100%;
  }
  .mm-twocol .mm-result { flex: 3 1 0; min-width: 0; }
  .mm-twocol .mm-config { flex: 2 1 0; min-width: 0; }
  .gradio-container .mm-config-panel {
    background: var(--mm-surface);
    border: 1px solid var(--mm-border);
    border-radius: 12px;
    padding: 14px;
    box-shadow: var(--mm-shadow);
  }
  @media (max-width: 1023px) {
    .gradio-container .mm-twocol { flex-direction: column; }
    .mm-twocol .mm-result,
    .mm-twocol .mm-config { flex: 1 1 auto; width: 100%; }
  }

  .gradio-container .mm-readonly,
  .gradio-container .mm-readonly input,
  .gradio-container .mm-readonly textarea {
    pointer-events: none;
    cursor: not-allowed;
    opacity: 0.65;
  }

  .mm-footer {
    text-align: center;
    margin-top: 32px;
    padding: 14px 0 0;
    border-top: 1px solid var(--mm-border);
    font-family: Geist, Inter, sans-serif;
    font-size: 11.5px;
    color: var(--mm-text-secondary);
    font-weight: 400;
  }
  .mm-footer a {
    color: var(--mm-accent);
    text-decoration: none;
    font-weight: 500;
    transition: color 0.2s ease;
  }
  .mm-footer a:hover { color: var(--mm-accent-hover); }
  .mm-footer .mm-install {
    font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
    background: var(--mm-surface-tint);
    color: var(--mm-accent-deep);
    padding: 2px 7px;
    border-radius: 5px;
    border: 1px solid var(--mm-border);
    font-size: 11px;
  }
  .mm-footer .mm-footer-sep {
    margin: 0 8px;
    color: var(--mm-text-muted);
  }

  @keyframes mm-fade-up {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .mm-header, .mm-footer { animation: mm-fade-up 0.4s ease-out both; }
  .mm-footer { animation-delay: 0.08s; }

  .gradio-container .mm-tabnav {
    margin: 0 0 14px !important;
    border-bottom: 1px solid var(--mm-border) !important;
    background: transparent !important;
    border-radius: 0 !important;
    padding: 0 !important;
    box-shadow: none !important;
  }
  .gradio-container .mm-tabnav .wrap,
  .gradio-container .mm-tabnav fieldset {
    display: flex !important;
    flex-direction: row !important;
    gap: 2px !important;
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
    overflow:hidden !important;
  }
  .gradio-container .mm-tabnav label {
    display: inline-flex !important;
    align-items: center !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    padding: 7px 14px !important;
    margin: 0 !important;
    margin-bottom: -1px !important;
    color: var(--mm-text-secondary) !important;
    font-family: Geist, Inter, sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    box-shadow: none !important;
    transition: color 0.15s ease, border-color 0.15s ease !important;
  }
  .gradio-container .mm-tabnav label:hover { color: var(--mm-accent) !important; }
  .gradio-container .mm-tabnav input[type="radio"] { display: none !important; }
  .gradio-container .mm-tabnav label.selected,
  .gradio-container .mm-tabnav label:has(input:checked) {
    color: var(--mm-text) !important;
    border-bottom-color: var(--mm-accent) !important;
    background: transparent !important;
  }

  .gradio-container .mm-pane,
  .gradio-container div.mm-pane {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
    margin-top: -16px !important;
    border-radius: 0 !important;
    overflow: visible !important;
    max-height: none !important;
    min-height: 0 !important;
  }
  .gradio-container .mm-pane > .form,
  .gradio-container .mm-pane > .panel,
  .gradio-container .mm-pane > .block:not(.mm-config-panel):not(.mm-accordion),
  .gradio-container .mm-pane > div.gap:not(.mm-config-panel):not(.mm-accordion) {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
  }
  .gr-group > div,
  .mm-pane > div {
    background-color: var(--mm-bg) !important;
  }
  .mm-config-panel > div,
  .mm-accordion > div {
    background-color: var(--mm-surface) !important;
  }
  .gradio-container .mm-pane .form > * + *,
  .gradio-container .mm-pane .gap > * + *,
  .gradio-container .mm-pane > .form > .block + .block,
  .gradio-container .mm-config-panel .form > * + *,
  .gradio-container .mm-config-panel .gap > * + * {
    border-top: none !important;
  }

  .html-container {
    margin-top: -35px;
  }
  .gradio-container .mm-pane > .html-container:first-child {
    margin-top: -2px !important;
  }
  .gradio-container .mm-config-panel .html-container,
  .gradio-container .mm-pane .html-container {
    margin: 0 !important;
    padding: 0 !important;
  }

  .gradio-container .mm-accordion {
    border: 1px solid var(--mm-border) !important;
    border-radius: 9px !important;
    background: var(--mm-surface) !important;
    margin: 10px 0 !important;
    overflow: hidden !important;
    box-shadow: none !important;
  }
  .gradio-container .mm-accordion > button.label-wrap,
  .gradio-container .mm-accordion > .label-wrap,
  .gradio-container .mm-accordion > summary {
    background: var(--mm-surface-tint) !important;
    color: var(--mm-text) !important;
    font-family: Geist, Inter, sans-serif !important;
    font-size: 12.5px !important;
    font-weight: 500 !important;
    padding: 8px 12px !important;
    border: none !important;
    border-radius: 0 !important;
  }
  .gradio-container .mm-accordion > button.label-wrap:hover,
  .gradio-container .mm-accordion > .label-wrap:hover {
    background: var(--mm-border) !important;
  }
  .gradio-container .mm-accordion[open] > button.label-wrap,
  .gradio-container .mm-accordion.open > button.label-wrap,
  .gradio-container .mm-accordion[open] > .label-wrap {
    border-bottom: 1px solid var(--mm-border) !important;
  }

  .gradio-container .mm-profile-row {
    display: grid !important;
    grid-template-columns: 1.3fr 2.2fr 1.3fr 0.5fr 0.5fr 0.95fr;
    gap: 8px !important;
    padding: 7px 12px !important;
    border-bottom: 1px solid var(--mm-border) !important;
    align-items: center !important;
    background: var(--mm-surface) !important;
    margin: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
  }
  .gradio-container .mm-profile-row.mm-profile-header {
    background: var(--mm-surface-tint) !important;
    border-radius: 8px 8px 0 0 !important;
    border-bottom: 1px solid var(--mm-border-strong) !important;
  }
  .gradio-container .mm-profile-row > .mm-profile-cell {
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    font-family: 'Geist Mono', ui-monospace, monospace !important;
    font-size: 12.5px !important;
    color: var(--mm-text) !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
  }
  .gradio-container .mm-profile-row.mm-profile-header > .mm-profile-cell {
    font-family: Geist, Inter, sans-serif !important;
    font-size: 11px !important;
    color: var(--mm-text-secondary) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-weight: 600 !important;
  }
  .gradio-container .mm-profile-row .mm-profile-mark {
    color: var(--mm-accent) !important;
    text-align: center !important;
    font-weight: 600 !important;
  }
  .gradio-container .mm-profile-row .mm-profile-mark-muted {
    color: var(--mm-text-muted) !important;
    text-align: center !important;
  }
  .gradio-container .mm-profile-row.mm-profile-active-row {
    background: linear-gradient(0deg, rgba(30,90,202,0.04), rgba(30,90,202,0.04)), var(--mm-surface) !important;
  }

  .gradio-container .mm-profile-actions {
    display: flex !important;
    flex-direction: row !important;
    gap: 6px !important;
    flex-wrap: nowrap !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
    justify-content: flex-end !important;
  }
  .gradio-container .mm-icon-btn,
  .gradio-container button.mm-icon-btn {
    width: 28px !important;
    height: 28px !important;
    min-width: 0 !important;
    padding: 0 !important;
    border-radius: 7px !important;
    font-size: 14px !important;
    line-height: 1 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    background: var(--mm-surface) !important;
    border: 1px solid var(--mm-border) !important;
    color: var(--mm-text-secondary) !important;
    box-shadow: none !important;
    transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease, transform 0.12s ease !important;
  }
  .gradio-container .mm-icon-btn:hover,
  .gradio-container button.mm-icon-btn:hover {
    background: var(--mm-surface-tint) !important;
    border-color: var(--mm-border-strong) !important;
    color: var(--mm-accent) !important;
  }
  .gradio-container .mm-icon-btn:active,
  .gradio-container button.mm-icon-btn:active {
    transform: translateY(1px) !important;
  }
  .gradio-container .mm-icon-btn.mm-icon-btn-danger,
  .gradio-container button.mm-icon-btn.mm-icon-btn-danger {
    color: var(--mm-danger) !important;
  }
  .gradio-container .mm-icon-btn.mm-icon-btn-danger:hover,
  .gradio-container button.mm-icon-btn.mm-icon-btn-danger:hover {
    background: var(--mm-danger-soft) !important;
    border-color: var(--mm-danger-border) !important;
    color: #8E2A2A !important;
  }

  .gradio-container .mm-profile-empty {
    padding: 14px !important;
    color: var(--mm-text-secondary) !important;
    font-style: italic !important;
    font-size: 12.5px !important;
    background: var(--mm-surface) !important;
    border: 1px dashed var(--mm-border) !important;
    border-radius: 9px !important;
  }

  .gradio-container button.mm-link-btn {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: var(--mm-text-secondary) !important;
    padding: 4px 0 !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    text-align: left !important;
    width: auto !important;
    min-width: 0 !important;
  }
  .gradio-container button.mm-link-btn:hover {
    color: var(--mm-accent) !important;
    background: transparent !important;
  }

  .gradio-container .mm-terminal-wrap {
    background: #0F1115;
    border: 1px solid var(--mm-border);
    border-radius: 12px;
    padding: 10px;
    box-shadow: var(--mm-shadow);
  }
  .gradio-container #mm-terminal {
    width: 100%;
    height: 600px;
  }
  .gradio-container #mm-terminal .xterm,
  .gradio-container #mm-terminal .xterm-viewport,
  .gradio-container #mm-terminal .xterm-screen {
    height: 100% !important;
    background: #0F1115 !important;
  }

  #mm-fv-btn {
    position: fixed;
    top: 16px;
    left: 16px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px 8px 10px;
    background: var(--mm-accent);
    color: #FFFFFF;
    border: 1px solid var(--mm-accent);
    border-radius: 999px;
    font-family: Geist, Inter, sans-serif;
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: 0.01em;
    cursor: pointer;
    z-index: 9000;
    box-shadow: 0 2px 8px rgba(30, 90, 202, 0.25), 0 1px 2px rgba(1, 9, 23, 0.06);
    transition: background 0.12s ease, border-color 0.12s ease, transform 0.12s ease, box-shadow 0.12s ease;
  }
  #mm-fv-btn:hover {
    background: var(--mm-accent-hover);
    border-color: var(--mm-accent-hover);
    box-shadow: 0 4px 14px rgba(30, 90, 202, 0.32), 0 1px 2px rgba(1, 9, 23, 0.08);
  }
  #mm-fv-btn:active { transform: translateY(1px); }
  #mm-fv-btn:focus-visible {
    outline: 2px solid var(--mm-accent-soft);
    outline-offset: 2px;
  }
  #mm-fv-btn .mm-fv-btn-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.18);
  }
  #mm-fv-btn .mm-fv-btn-label { line-height: 1; }

  #mm-fv-modal {
    position: fixed;
    inset: 0;
    z-index: 9100;
    display: none;
    font-family: Geist, Inter, sans-serif;
  }
  #mm-fv-modal.mm-fv-open { display: block; }
  #mm-fv-modal .mm-fv-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(1, 9, 23, 0.45);
    backdrop-filter: blur(2px);
    -webkit-backdrop-filter: blur(2px);
  }
  #mm-fv-modal .mm-fv-panel {
    position: absolute;
    top: 4vh;
    left: 50%;
    transform: translateX(-50%);
    width: min(1100px, 92vw);
    height: 88vh;
    background: var(--mm-surface);
    border: 1px solid var(--mm-border);
    border-radius: 12px;
    box-shadow: 0 24px 60px rgba(1, 9, 23, 0.18);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  #mm-fv-modal .mm-fv-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--mm-border);
    background: var(--mm-surface);
  }
  #mm-fv-modal .mm-fv-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--mm-text);
    letter-spacing: 0.01em;
  }
  #mm-fv-modal .mm-fv-subtitle {
    font-family: 'Geist Mono', ui-monospace, monospace;
    font-size: 11.5px;
    font-weight: 400;
    color: var(--mm-text-secondary);
    margin-left: 8px;
  }
  #mm-fv-modal .mm-fv-close {
    background: transparent;
    border: none;
    width: 28px;
    height: 28px;
    border-radius: 6px;
    font-size: 20px;
    line-height: 1;
    color: var(--mm-text-secondary);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  #mm-fv-modal .mm-fv-close:hover {
    background: var(--mm-surface-tint);
    color: var(--mm-text);
  }
  #mm-fv-modal .mm-fv-body {
    flex: 1;
    display: flex;
    min-height: 0;
  }
  #mm-fv-modal .mm-fv-sidebar {
    width: 320px;
    border-right: 1px solid var(--mm-border);
    overflow: auto;
    background: var(--mm-bg);
    padding: 8px 0;
  }
  #mm-fv-modal .mm-fv-tree-root {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 14px 8px;
    font-family: 'Geist Mono', ui-monospace, monospace;
    font-size: 12px;
    color: var(--mm-text);
    border-bottom: 1px solid var(--mm-border);
    margin-bottom: 6px;
  }
  #mm-fv-modal .mm-fv-tree-root .mm-fv-glyph { color: var(--mm-accent); }
  #mm-fv-modal .mm-fv-tree-root .mm-fv-name { font-weight: 600; flex: 1; }
  #mm-fv-modal .mm-fv-tree-root .mm-fv-size {
    color: var(--mm-text-muted);
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
  }
  #mm-fv-modal .mm-fv-item,
  #mm-fv-modal .mm-fv-tree-dir {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 14px;
    font-family: 'Geist Mono', ui-monospace, monospace;
    font-size: 12px;
    line-height: 1.4;
    color: var(--mm-text);
    border-left: 2px solid transparent;
  }
  #mm-fv-modal .mm-fv-item { cursor: pointer; }
  #mm-fv-modal .mm-fv-item:hover { background: var(--mm-surface-tint); }
  #mm-fv-modal .mm-fv-item-selected {
    background: var(--mm-surface);
    border-left-color: var(--mm-accent);
  }
  #mm-fv-modal .mm-fv-tree-dir {
    color: var(--mm-text-secondary);
    cursor: default;
    user-select: none;
  }
  #mm-fv-modal .mm-fv-tree-dir .mm-fv-glyph { color: var(--mm-text-muted); }
  #mm-fv-modal .mm-fv-tree-prefix {
    color: var(--mm-text-muted);
    white-space: pre;
    flex-shrink: 0;
    font-variant-ligatures: none;
  }
  #mm-fv-modal .mm-fv-glyph {
    color: var(--mm-text-secondary);
    font-size: 11px;
    width: 14px;
    text-align: center;
    flex-shrink: 0;
  }
  #mm-fv-modal .mm-fv-item-selected .mm-fv-glyph { color: var(--mm-accent); }
  #mm-fv-modal .mm-fv-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
  }
  #mm-fv-modal .mm-fv-size {
    color: var(--mm-text-muted);
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  #mm-fv-modal .mm-fv-empty {
    padding: 16px;
    color: var(--mm-text-secondary);
    font-size: 12px;
    text-align: center;
  }
  #mm-fv-modal .mm-fv-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    background: var(--mm-surface);
  }
  #mm-fv-modal .mm-fv-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--mm-border);
    font-family: 'Geist Mono', ui-monospace, monospace;
    font-size: 11.5px;
    color: var(--mm-text-secondary);
    background: var(--mm-bg);
  }
  #mm-fv-modal .mm-fv-meta-name {
    color: var(--mm-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  #mm-fv-modal .mm-fv-meta-sep { color: var(--mm-text-muted); }
  #mm-fv-modal .mm-fv-preview {
    flex: 1;
    overflow: auto;
    background: var(--mm-surface);
  }
  #mm-fv-modal .mm-fv-frame {
    width: 100%;
    height: 100%;
    padding: 18px;
    box-sizing: border-box;
  }
  #mm-fv-modal .mm-fv-frame-center {
    display: flex;
    align-items: center;
    justify-content: center;
    background:
      linear-gradient(45deg, var(--mm-bg) 25%, transparent 25%) 0 0 / 16px 16px,
      linear-gradient(-45deg, var(--mm-bg) 25%, transparent 25%) 0 8px / 16px 16px,
      linear-gradient(45deg, transparent 75%, var(--mm-bg) 75%) 8px -8px / 16px 16px,
      linear-gradient(-45deg, transparent 75%, var(--mm-bg) 75%) -8px 0 / 16px 16px,
      var(--mm-surface);
  }
  #mm-fv-modal .mm-fv-frame img,
  #mm-fv-modal .mm-fv-frame video {
    max-width: 100%;
    max-height: 100%;
    border-radius: 6px;
    box-shadow: 0 4px 16px rgba(1, 9, 23, 0.08);
    background: var(--mm-surface);
  }
  #mm-fv-modal .mm-fv-frame audio { width: min(520px, 100%); }
  #mm-fv-modal .mm-fv-iframe {
    width: 100%;
    height: 100%;
    border: 0;
    background: var(--mm-surface);
  }
  #mm-fv-modal .mm-fv-text {
    margin: 0;
    padding: 16px 18px;
    font-family: 'Geist Mono', ui-monospace, monospace;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--mm-text);
    background: var(--mm-surface);
    white-space: pre-wrap;
    word-break: break-word;
  }
  @media (max-width: 720px) {
    #mm-fv-modal .mm-fv-sidebar { width: 200px; }
    #mm-fv-modal .mm-fv-panel { top: 2vh; height: 96vh; width: 96vw; }
  }
</style>
"""

HEADER_HTML = """
<div class="mm-header mm-hero">
  <img class="mm-hero-logo"
       src="https://raw.githubusercontent.com/vlm-run/.github/refs/heads/main/profile/assets/vlm-black.svg"
       alt="VLM Run">
  <h1 class="mm-hero-title">mm-ctx</h1>
  <hr style="width: 100%; height; 1px; margin:0; padding: 0" />
  <div align="center">
    <h3 style="font-size:18px;">Fast, multimodal context for agents</h3>
  </div>
</div>
"""

FOOTER_HTML = (
    '<div class="mm-footer">'
    '<code class="mm-install">pip install mm-ctx</code>'
    '<span class="mm-footer-sep">·</span>'
    "Powered by "
    '<a href="https://vlm.run/open-source/mm" target="_blank" rel="noopener">VLM Run</a>'
    "</div>"
)
