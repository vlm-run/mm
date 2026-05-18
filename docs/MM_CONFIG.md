# mm config

View and set extraction mode configuration — Whisper model, audio speed, beam size, and transcription backend settings stored in `~/.config/mm/mm.toml`.

## Synopsis

```bash
mm config SUBCOMMAND [OPTIONS]
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `show` | Display resolved configuration with current values |
| `init` | Create the default config file |
| `set KEY VALUE` | Set a single config key |
| `reset-db` | Delete all mm databases and caches |
| `reset-profiles` | Restore all profiles to built-in defaults |
| `reset` | Reset everything: databases and profiles |

## mm config show

Display the active configuration. Values are read from `~/.config/mm/mm.toml` when it exists; built-in defaults are used otherwise.

```bash
mm config show
mm config show --format json
mm config show --format tsv
```

**Options:**

| Flag | Description |
|------|-------------|
| `--format FORMAT` | Output format: `rich` (default), `json`, `tsv`, `csv` |

**Example output (rich):**

```
Extraction Modes
  mode      whisper_model   audio_speed   beam_size
  ─────────────────────────────────────────────────
  fast      tiny            1.6           1
  accurate  medium          1.0           5

Transcription
  key        value
  ─────────────────────────────────
  backend    openai
  base_url   http://localhost:11434/v1
  api_key    ••••
```

## mm config init

Create the default config file at `~/.config/mm/mm.toml`. Does nothing if the file already exists unless `--force` is passed.

```bash
mm config init
mm config init --force    # overwrite existing config
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--force` | `-f` | Overwrite the existing config file |

## mm config set

Set a single configuration key. Changes are written to `~/.config/mm/mm.toml`, creating the file if it does not exist.

```bash
mm config set KEY VALUE
```

### Mode keys

Controls Whisper transcription behavior per extraction mode.

| Key | Description | Example |
|-----|-------------|---------|
| `mode.fast.whisper_model` | Whisper model for fast mode | `tiny`, `base`, `small` |
| `mode.fast.audio_speed` | Audio playback speed multiplier for fast mode | `1.6` |
| `mode.fast.beam_size` | Whisper beam size for fast mode | `1` |
| `mode.accurate.whisper_model` | Whisper model for accurate mode | `medium`, `large-v3` |
| `mode.accurate.audio_speed` | Audio playback speed multiplier for accurate mode | `1.0` |
| `mode.accurate.beam_size` | Whisper beam size for accurate mode | `5` |

### Transcription keys

Controls the transcription backend used for audio and video.

| Key | Description | Example |
|-----|-------------|---------|
| `transcription.backend` | Transcription backend | `openai`, `mlx`, `ctranslate2` |
| `transcription.base_url` | API base URL for `openai` backend | `http://localhost:11434/v1` |
| `transcription.api_key` | API key for the transcription endpoint | `sk-...` |

**Examples:**

```bash
# Use a faster Whisper model for quick transcription
mm config set mode.fast.whisper_model tiny
mm config set mode.fast.audio_speed 2.0
mm config set mode.fast.beam_size 1

# Use a more accurate model for detailed transcription
mm config set mode.accurate.whisper_model large-v3
mm config set mode.accurate.audio_speed 1.0
mm config set mode.accurate.beam_size 5

# Point at a local OpenAI-compatible transcription server
mm config set transcription.backend openai
mm config set transcription.base_url http://localhost:11434/v1
mm config set transcription.api_key sk-...
```

## mm config reset-db

Delete all mm databases and caches. This removes the SQLite database at `~/.local/share/mm/mm.db` and any legacy cache files. **This action is irreversible.**

```bash
mm config reset-db
mm config reset-db --yes    # skip confirmation prompt
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--yes` | `-y` | Skip the confirmation prompt |

This clears:
- All cached LLM extractions (`extractions` table)
- All chunked content and embeddings (`chunks` / `chunks_vec` tables)
- File metadata index (`files` table)

## mm config reset-profiles

Reset all profiles to built-in defaults. Removes custom profiles and restores reserved profiles to their default values. Mode settings (Whisper model, audio speed) are preserved.

```bash
mm config reset-profiles
mm config reset-profiles --yes    # skip confirmation
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--yes` | `-y` | Skip the confirmation prompt |

## mm config reset

Combines `reset-db` and `reset-profiles` into a single operation. Deletes all databases, clears all caches, and restores profiles to defaults. **This action is irreversible.**

```bash
mm config reset
mm config reset --yes    # skip all confirmation prompts
```

**Options:**

| Flag | Short | Description |
|------|-------|-------------|
| `--yes` | `-y` | Skip the confirmation prompt |

## Configuration file

`mm` reads configuration from `~/.config/mm/mm.toml`. The file is optional; built-in defaults apply when it does not exist.

```toml
[mode.fast]
whisper_model = "tiny"
audio_speed = 1.6
beam_size = 1

[mode.accurate]
whisper_model = "medium"
audio_speed = 1.0
beam_size = 5

[transcription]
backend = "openai"
base_url = "http://localhost:11434/v1"
api_key = ""
```

## Transcription backends

The `transcription.backend` key selects the Whisper runtime:

| Backend | Description | Install |
|---------|-------------|---------|
| `openai` | Any OpenAI-compatible `/audio/transcriptions` endpoint (default) | Built-in |
| `mlx` | Apple Metal GPU via `lightning-whisper-mlx` — fastest on Apple Silicon | `pip install mm-ctx[mlx]` |
| `ctranslate2` | CPU int8 / CUDA float16 via `faster-whisper` | `pip install mm-ctx[gpu]` |

The backend can also be overridden per-invocation with `--encode.backend`:

```bash
mm cat audio.mp3 -m accurate --encode.backend mlx
mm cat audio.mp3 -m accurate --encode.backend ctranslate2
```

## Notes

- `mm config show` sources its caption from the actual config file path, so you can verify which file is being read.
- `reset-db` lists every file that will be deleted before prompting for confirmation.
- `reset-profiles` preserves `[mode.*]` and `[transcription.*]` settings — only the `[profiles]` sections are affected.
- The `api_key` field is always masked in `show` output and JSON (`••••`).
