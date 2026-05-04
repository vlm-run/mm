from mm.cat_utils.base_utils import KIND_ORDER


def do_list_encoders() -> None:
    """Print a Rich panel of all registered encoders with descriptions."""
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    from mm.encoders import list_encoders_detail

    entries = list_encoders_detail()

    kind_rank = {k: i for i, k in enumerate(KIND_ORDER)}
    entries.sort(key=lambda e: (kind_rank.get(e["media_types"][0], 99), e["prefixed_name"]))

    max_name = max((len(e["prefixed_name"]) for e in entries), default=28)
    name_w = max_name + 2
    lines: list[Text] = []
    prev_kind = ""
    for entry in entries:
        cur_kind = entry["media_types"][0] if entry["media_types"] else "unknown"
        if cur_kind != prev_kind and prev_kind:
            lines.append(Text(""))
        prev_kind = cur_kind

        prefixed = entry["prefixed_name"]
        desc = entry["description"]
        params: list[tuple[str, str]] = entry["params"]

        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(prefixed.ljust(name_w), style="bold white")
        line.append(desc, style="white")
        lines.append(line)

        if params:
            param_line = Text(no_wrap=True, overflow="ellipsis")
            param_line.append(" " * name_w)
            param_parts: list[str] = []
            for pname, default in params:
                param_parts.append(f"{pname}={default}")
            param_line.append(", ".join(param_parts), style="green")
            lines.append(param_line)

    body = Text("\n").join(lines)
    max_line = max((len(line.plain) for line in lines), default=60)
    panel_w = max_line + 8
    console = Console(width=max(panel_w, 80))
    panel = Panel(
        body, title="Encoders", title_align="left", box=box.ROUNDED, padding=(1, 2), width=panel_w
    )
    console.print()
    console.print(panel)
    console.print()
