# mm profile

Manage LLM provider profiles — store and switch between API endpoints, models, and keys without editing config files.

## Synopsis

```bash
mm profile SUBCOMMAND [OPTIONS]
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `list` | List all configured profiles |
| `add NAME` | Add a new profile |
| `update NAME` | Update one or more fields of an existing profile |
| `clone SRC DEST` | Clone a profile, optionally overriding individual fields |
| `use NAME` | Switch the active profile |
| `remove NAME` | Remove a profile |

## Profile fields

Each profile stores three fields:

| Field | Description |
|-------|-------------|
| `base_url` | LLM API base URL (e.g. `https://api.openai.com/v1`) |
| `model` | Default model name for this endpoint |
| `api_key` | API key (optional; empty for local providers like Ollama) |

## Profile resolution order

The active profile is resolved in this order of precedence:

1. `--profile NAME` flag on the `mm` command
2. `MM_PROFILE` environment variable
3. `active_profile` field in `~/.config/mm/profiles.toml`
4. `"ollama"` (built-in fallback)

## mm profile list

List all configured profiles with their `base_url` and `model`. The active profile is marked with a bullet (●).

```bash
mm profile list
mm profile list --format json
mm profile list --format tsv
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--format FORMAT` | `-f` | Output format: `rich` (default), `json`, `tsv`, `csv` |

API keys are masked (`••••`) in all output formats.

**Example output (rich):**

```
  Profile       base_url                          model
  ──────────────────────────────────────────────────────
● ollama        http://localhost:11434/v1          qwen3-vl:8b
  openai        https://api.openai.com/v1          gpt-4o
  openrouter    https://openrouter.ai/api/v1       Qwen/Qwen3.5-0.8B
```

## mm profile add

Add a new named profile. `--base-url` and `--model` are required.

```bash
mm profile add NAME --base-url URL --model MODEL [--api-key KEY]
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--base-url URL` | `-b` | LLM API base URL (required) |
| `--model MODEL` | `-m` | Default model name (required) |
| `--api-key KEY` | `-k` | API key (default: empty) |

**Examples:**

```bash
# Add an OpenRouter profile
mm profile add openrouter \
  --base-url https://openrouter.ai/api/v1 \
  --model Qwen/Qwen3.5-0.8B

# Add an OpenAI profile with API key
mm profile add openai \
  --base-url https://api.openai.com/v1 \
  --api-key sk-... \
  --model gpt-4o

# Add a local Ollama profile
mm profile add ollama \
  --base-url http://localhost:11434/v1 \
  --model qwen3-vl:8b

# Add a vLLM server
mm profile add vllm \
  --base-url http://gpu-server:8000/v1 \
  --model Qwen/Qwen2.5-VL-7B-Instruct
```

Returns an error if a profile with the given name already exists.

## mm profile update

Update one or more fields of an existing profile. Only the fields you specify are changed; others are preserved.

```bash
mm profile update NAME [--base-url URL] [--model MODEL] [--api-key KEY]
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--base-url URL` | `-b` | New LLM API base URL |
| `--model MODEL` | `-m` | New model name |
| `--api-key KEY` | `-k` | New API key |

**Examples:**

```bash
# Switch the model on an existing profile
mm profile update ollama --model qwen3.5:0.8

# Rotate an API key
mm profile update openai --api-key sk-new-key

# Update both URL and model
mm profile update openai \
  --base-url https://api.openai.com/v1 \
  --model gpt-4o-mini
```

Returns an error if the profile does not exist.

## mm profile use

Switch the active profile. The active profile is persisted in `~/.config/mm/profiles.toml`.

```bash
mm profile use NAME
```

**Examples:**

```bash
mm profile use openrouter
mm profile use ollama
mm profile use gemini
```

Returns an error if the named profile does not exist.

## mm profile clone

Clone an existing profile, optionally overriding individual fields. All fields are copied from the source profile; any option provided on the command line overwrites the corresponding field in the clone.

```bash
mm profile clone SRC DEST [--base-url URL] [--model MODEL] [--api-key KEY]
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--base-url URL` | `-b` | Override base URL in the clone |
| `--model MODEL` | `-m` | Override model name in the clone |
| `--api-key KEY` | `-k` | Override API key in the clone (defaults to `''` if not provided) |

**Examples:**

```bash
# Exact copy
mm profile clone ollama my-ollama

# Clone with a different model
mm profile clone ollama my-ollama --model qwen3-vl:8b

# Clone with a different API key
mm profile clone openai openai-dev --api-key sk-dev-...

# Clone with multiple overrides
mm profile clone openai openai-eu --model qwen3-vl:8b --base-url https://eu.openai.com/v1
```

Returns an error if the source profile does not exist or the destination name is already taken.

## mm profile remove

Remove a profile. The currently active profile cannot be removed — switch to another profile first.

```bash
mm profile remove NAME
```

**Examples:**

```bash
mm profile remove openai
```

Returns an error if the profile is currently active or does not exist.

## Per-command profile selection

Select a profile for a single command without changing the active profile:

```bash
# CLI flag (highest priority)
mm --profile openrouter cat photo.png -m accurate

# Environment variable
MM_PROFILE=openai mm cat photo.png -m accurate
```

## Configuration file

Profiles are stored in `~/.config/mm/profiles.toml`. The file follows standard TOML format with one section per profile:

```toml
active_profile = "ollama"

[ollama]
base_url = "http://localhost:11434/v1"
model = "qwen3-vl:8b"
api_key = ""

[openai]
base_url = "https://api.openai.com/v1"
model = "gpt-4o"
api_key = "sk-..."
```

## Notes

- Profile names are case-sensitive.
- `mm profile list --format json` emits an `{"active": "...", "profiles": {...}}` envelope; API keys are masked as `"••••"` in all formats.
- Use `mm config reset-profiles` to restore all built-in profiles to their defaults and remove custom ones.
