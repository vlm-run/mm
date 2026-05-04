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
  .mm-footer .mm-install {
    font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace;
    background: var(--mm-surface-tint);
    color: var(--mm-accent-deep);
    padding: 2px 8px;
    border-radius: 6px;
    border: 1px solid var(--mm-border);
    font-size: 11.5px;
  }
  .mm-footer .mm-footer-sep {
    margin: 0 10px;
    color: var(--mm-text-muted);
  }
  @keyframes mm-fade-up {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .mm-header, .mm-footer { animation: mm-fade-up 0.5s ease-out both; }
  .mm-footer  { animation-delay: 0.1s; }
  .mm-section { padding: 12px 2px 16px 2px; margin: 0; }
  .gradio-container .mm-tabnav {
    margin: 4px 0 20px 0 !important;
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
    gap: 4px !important;
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
    overflow: hidden !important;
  }
  .gradio-container .mm-tabnav label {
    display: inline-flex !important;
    align-items: center !important;
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    padding: 8px 16px !important;
    margin: 0 !important;
    margin-bottom: -1px !important;
    color: var(--mm-text-secondary) !important;
    font-family: Geist, Inter, sans-serif !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    box-shadow: none !important;
    transition: color 0.15s ease, border-color 0.15s ease !important;
  }
  .gradio-container .mm-tabnav label:hover {
    color: var(--mm-accent) !important;
  }
  .gradio-container .mm-tabnav input[type="radio"] {
    display: none !important;
  }
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

  .gradio-container .mm-accordion {
    border: 1px solid var(--mm-border) !important;
    border-radius: 10px !important;
    background: var(--mm-surface) !important;
    margin: 12px 0 !important;
    overflow: hidden !important;
    box-shadow: none !important;
  }
  .gradio-container .mm-accordion > button.label-wrap,
  .gradio-container .mm-accordion > .label-wrap,
  .gradio-container .mm-accordion > summary {
    background: var(--mm-surface-tint) !important;
    color: var(--mm-text) !important;
    font-family: Geist, Inter, sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
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

  /* Profile table — custom @gr.render layout with per-row action buttons */
  .gradio-container .mm-profile-row {
    display: grid !important;
    grid-template-columns: 1.4fr 2fr 1.4fr 0.6fr 0.6fr 1.6fr;
    gap: 8px !important;
    padding: 8px 12px !important;
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
    font-size: 13px !important;
    color: var(--mm-text) !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
  }
  .gradio-container .mm-profile-row.mm-profile-header > .mm-profile-cell {
    font-family: Geist, Inter, sans-serif !important;
    font-size: 12px !important;
    color: var(--mm-text-secondary) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
  }
  .gradio-container .mm-profile-actions {
    display: flex !important;
    flex-direction: row !important;
    gap: 4px !important;
    flex-wrap: nowrap !important;
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
  }
  .gradio-container .mm-profile-actions button {
    padding: 4px 10px !important;
    font-size: 12px !important;
    white-space: nowrap !important;
    min-width: 0 !important;
  }
  .gradio-container .mm-profile-empty {
    padding: 16px !important;
    color: var(--mm-text-secondary) !important;
    font-style: italic !important;
  }
  .html-container {
    margin-top: -35px;
  }
</style>
"""

HEADER_HTML = """
<div class="mm-header">
  <h1 class="mm-h1"><span class="mm-h1-mark">mm</span> &middot; fast, multimodal context for agents</h1>
  <p class="mm-sub">cat, grep &amp; profile management for the mm Python API</p>
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
