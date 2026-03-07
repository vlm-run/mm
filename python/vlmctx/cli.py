"""vlmctx CLI -- Unix-philosophy multi-modal context management."""

from __future__ import annotations

import typer

from vlmctx.commands import audio, cat, describe, find, grep, head, info, keyframes, ls, sql, tail

app = typer.Typer(
    name="vlmctx",
    help="High-performance multi-modal context management.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

app.command(name="find")(find.find_cmd)
app.command(name="ls")(ls.ls_cmd)
app.command(name="cat")(cat.cat_cmd)
app.command(name="head")(head.head_cmd)
app.command(name="tail")(tail.tail_cmd)
app.command(name="grep")(grep.grep_cmd)
app.command(name="sql")(sql.sql_cmd)
app.command(name="describe")(describe.describe_cmd)
app.command(name="info")(info.info_cmd)
app.command(name="keyframes")(keyframes.keyframes_cmd)
app.command(name="audio")(audio.audio_cmd)


if __name__ == "__main__":
    app()
