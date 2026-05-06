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
