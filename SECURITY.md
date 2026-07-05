# Security Policy

## Supported versions

`mm` is pre-1.0 and released continuously. Only the latest published version on PyPI is supported; please upgrade before reporting an issue.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities. Instead, email **support@vlm.run** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal repro is very helpful).
- The `mm` version and platform you're running.

We'll acknowledge your report as soon as possible and work with you on a fix and disclosure timeline.

## Scope notes

`mm` reads arbitrary local files and directories, and can shell out to external LLM backends (OpenAI-compatible APIs, local Ollama, etc.) configured via profiles. If you find a way for `mm` to read, execute, or exfiltrate data outside of what a user explicitly points it at, that's a vulnerability we want to hear about.
