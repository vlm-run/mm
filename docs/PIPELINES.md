# Pipelines

Pipelines configure a 2-stage flow for LLM-based media understanding:
**encode** (via an encoder) then **generate** (LLM call) to produce text output.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'lineColor': '#666'}}}%%
graph LR
  file["Media File"]:::input

  subgraph encode ["Encode"]
    encoder["Encoder"]:::encode
  end

  subgraph generate ["Generate"]
    llm["MLLM"]:::generate
  end

  out["stdout"]:::output

  file --> encoder --> llm --> out

  classDef input fill:#e8f4fd,stroke:#4a90d9,stroke-width:1.5px,color:#1a3a5c,rx:8
  classDef encode fill:#e8f5e9,stroke:#4caf50,stroke-width:1.5px,color:#1b5e20,rx:8
  classDef generate fill:#fce4ec,stroke:#e57373,stroke-width:1.5px,color:#6a1b1b,rx:8
  classDef output fill:#f5f5f5,stroke:#bdbdbd,stroke-width:1.5px,color:#424242,rx:8

  style encode fill:#f1f8e9,stroke:#66bb6a,stroke-width:1px,rx:10
  style generate fill:#fff0f0,stroke:#ef9a9a,stroke-width:1px,rx:10
```

Each pipeline is a YAML file under `pipelines/{kind}/{mode}.yaml` that references
an encoder from `mm/encoders/` and configures LLM generation parameters.

```bash
mm cat photo.jpg -p resize          # named encoder
mm cat video.mp4 -p shot-mosaic     # scene-aware video encoder

# Override pipeline config from CLI
mm cat photo.jpg -m accurate --encode.strategy tile
mm cat photo.jpg -m accurate --generate.max-tokens 1024 --generate.temperature 0.5

# Load explicit pipeline YAML (repeatable, dispatched by kind)
mm cat photo.jpg -p ~/my-image-pipeline.yaml
mm cat *.jpg *.mp4 -p image.yaml -p video.yaml

# Custom Python transform via pyfunc
mm cat photo.jpg -m accurate --encode.pyfunc ~/my_filter.py
```

### Example `my_filter.py`

A pyfunc file must define `transform(parts, context) -> list[dict]`.
`parts` is a list of OpenAI-compatible message content dicts (e.g.
`{"type": "text", ...}` or `{"type": "image_url", ...}`); `context` is
file metadata (name, kind, size, etc.).

```python
# ~/my_filter.py — keep only image parts and prepend a custom instruction
def transform(parts: list[dict], context: dict) -> list[dict]:
    images = [p for p in parts if p.get("type") == "image_url"]
    header = {"type": "text", "text": f"Analyze {context['name']} in detail."}
    return [header, *images]
```

Inline variants also work inside a pipeline YAML:

```yaml
encode:
  strategy: resize
  pyfunc: |
    def transform(parts, context):
        return [p for p in parts if p.get("type") == "image_url"]
```

## Encoders

See [ENCODERS.md](ENCODERS.md) for the full encoder reference — all built-in encoders, parameters, planned encoders, and how to write custom encoders.
