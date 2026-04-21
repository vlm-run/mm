#!/usr/bin/env bash
set -euo pipefail

# Render README.md to a centered, dark-themed HTML preview.
# Mirrors the rendering done by .github/workflows/deploy-web.yml (deploy-readme).
#
# Usage:  ./scripts/preview-readme.sh [OUT_DIR]
# Default OUT_DIR: /tmp/mm-readme-preview

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-/tmp/mm-readme-preview}"

mkdir -p "$OUT/docs/assets"
cp -r "$ROOT/docs/assets/." "$OUT/docs/assets/"
cp "$ROOT/README.md" "$OUT/"

cd "$OUT"
npm install --no-save --silent marked@11

node <<'EOF'
const fs = require('fs');
const { marked } = require('marked');
const md = fs.readFileSync('README.md', 'utf8');
const body = marked.parse(md, { gfm: true, breaks: false });
const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>mm-ctx</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-light.min.css">
  <style>
    html, body { background: #ffffff; margin: 0; }
    .markdown-body { box-sizing: border-box; min-width: 200px; max-width: 980px; margin: 0 auto; padding: 45px; }
    @media (max-width: 767px) { .markdown-body { padding: 15px; } }
  </style>
</head>
<body>
  <article class="markdown-body">
${body}
  </article>
</body>
</html>`;
fs.writeFileSync('index.html', html);
console.log('wrote', html.length, 'bytes ->', process.cwd() + '/index.html');
EOF

echo
echo "Open: file://$OUT/index.html"
