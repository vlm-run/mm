"""Design system chrome — fonts, custom CSS, header, footer.

Extracted from ``ui.py`` so the visual layer can be edited without
touching the Gradio component wiring. The Gradio theme tokens (colours,
radii, hover states) live in ``theme.py``; this module only carries
the supplemental CSS, the header markup, and the footer markup.
"""

from __future__ import annotations

DESIGN_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
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
    --mm-shadow: 0 1px 2px rgba(1,9,23,0.04), 0 4px 12px rgba(1,9,23,0.04);
  }

  /* Page chrome — centered */
  .gradio-container {
    max-width: 1200px !important;
    margin: 0 auto !important;
    padding: 24px 28px 80px !important;
    font-family: Geist, Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  }
  gradio-app, gradio-app > .main, gradio-app > div {
    width: 100% !important;
  }

  /* Checkboxes — white inset square with brand-blue check when selected. */
  .gradio-container input[type="checkbox"] {
    appearance: none;
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    margin: 0;
    cursor: pointer;
    background-position: center;
    background-repeat: no-repeat;
    background-size: 14px 14px;
    transition: background-color 0.15s ease, border-color 0.15s ease;
  }
  .gradio-container input[type="checkbox"]:hover {
    border-color: var(--mm-accent-soft) !important;
  }

  /* Field label typography */
  .gradio-container label > span,
  .gradio-container .label-wrap > span,
  .gradio-container span.label {
    font-family: Geist, Inter, sans-serif;
    font-size: 12px;
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

  /* Sage-blue focus halo for keyboard navigation */
  .gradio-container *:focus-visible {
    outline: 2px solid var(--mm-accent-soft);
    outline-offset: 2px;
  }

  /* Soft shadow on the white surfaces */
  .gradio-container .form,
  .gradio-container .panel,
  .gradio-container .block {
    box-shadow: var(--mm-shadow);
  }

  /* Tables / Dataframe — explicit so dark mode never wins */
  .gradio-container .table-wrap,
  .gradio-container table {
    background: var(--mm-surface) !important;
    color: var(--mm-text) !important;
    border-color: var(--mm-border) !important;
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

  /* CodeMirror / Code blocks — navy on white, no dark theme bleed */
  .gradio-container .codemirror-wrappper,
  .gradio-container .cm-editor,
  .gradio-container .cm-scroller,
  .gradio-container .cm-content,
  .gradio-container pre {
    background: var(--mm-surface) !important;
    color: var(--mm-text) !important;
    font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace !important;
  }
  .gradio-container .cm-line { color: var(--mm-text) !important; }
  .gradio-container .cm-gutters {
    background: var(--mm-bg) !important;
    color: var(--mm-text-secondary) !important;
    border-right: 1px solid var(--mm-border) !important;
  }
  /* JSON syntax tokens (CodeMirror v6 + Lezer highlighting classes) */
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

  /* Page header — flat, no card */
  .mm-header { margin: 4px 2px 20px 2px; }
  .mm-h1 {
    font-family: Geist, Inter, sans-serif;
    font-size: 22px;
    line-height: 1.15;
    letter-spacing: -0.01em;
    margin: 0 0 2px 0;
    color: var(--mm-text);
    font-weight: 600;
  }
  .mm-h1 .mm-h1-mark { color: var(--mm-accent); }
  .mm-sub {
    font-family: Geist, Inter, sans-serif;
    font-size: 13px;
    line-height: 1.4;
    color: var(--mm-text-secondary);
    margin: 0;
    font-weight: 400;
  }

  /* Per-tab section heading */
  .mm-section { padding: 12px 2px 16px 2px; }
  .mm-section h2 {
    font-family: Geist, Inter, sans-serif;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: 1.2;
    margin: 0 0 4px 0;
    color: var(--mm-text);
  }
  .mm-section .mm-note {
    font-family: Geist, Inter, sans-serif;
    font-size: 13px;
    color: var(--mm-text-secondary);
    margin: 0;
    font-weight: 400;
  }
  .mm-section code, .gradio-container code {
    font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
    background: var(--mm-surface-tint);
    color: var(--mm-accent-deep);
    padding: 1px 6px;
    border-radius: 6px;
    font-size: 0.9em;
    border: 1px solid var(--mm-border);
  }

  /* 2-column layout for Browse/Cat/Grep.
     min-lg (≥1024px): result : config = 3 : 2 (result side larger).
     max-lg (<1024px): single column, both fill parent. */
  .gradio-container .mm-twocol {
    display: flex;
    flex-direction: row;
    gap: 16px;
    align-items: stretch;
    width: 100%;
  }
  .mm-twocol .mm-result { flex: 3 1 0; min-width: 0; }
  .mm-twocol .mm-config { flex: 2 1 0; min-width: 0; }
  .gradio-container .mm-config-panel {
    background: var(--mm-surface);
    border: 1px solid var(--mm-border);
    border-radius: 14px;
    padding: 16px;
    box-shadow: var(--mm-shadow);
  }
  @media (max-width: 1023px) {
    .gradio-container .mm-twocol { flex-direction: column; }
    .mm-twocol .mm-result,
    .mm-twocol .mm-config { flex: 1 1 auto; width: 100%; }
  }

  /* Read-only directory hint — visually present, not interactive */
  .gradio-container .mm-readonly,
  .gradio-container .mm-readonly input,
  .gradio-container .mm-readonly textarea {
    pointer-events: none;
    cursor: not-allowed;
    opacity: 0.7;
  }

  /* Footer */
  .mm-footer {
    text-align: center;
    margin-top: 48px;
    padding: 20px 0 0 0;
    border-top: 1px solid var(--mm-border);
    font-family: Geist, Inter, sans-serif;
    font-size: 12px;
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

  /* Subtle entry animation */
  @keyframes mm-fade-up {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .mm-header, .mm-section, .mm-footer { animation: mm-fade-up 0.5s ease-out both; }
  .mm-section { animation-delay: 0.05s; }
  .mm-footer  { animation-delay: 0.1s; }
</style>
"""

HEADER_HTML = """
<div class="mm-header">
  <h1 class="mm-h1"><span class="mm-h1-mark">mm</span> &middot; fast, multimodal context</h1>
  <p class="mm-sub">cat, grep &amp; profile management for the mm Python API</p>
</div>
"""

FOOTER_HTML = (
    '<div class="mm-footer">Powered by '
    '<a href="https://vlm.run/open-source/mm" target="_blank" rel="noopener">VLM Run</a>'
    "</div>"
)
