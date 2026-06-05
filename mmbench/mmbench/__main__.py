"""Command-line entrypoint for mmbench-agents.

Subcommands::

    python -m mmbench dataset {freeze,verify}
    python -m mmbench run --assistants mock-strong,mock-weak [options]
    python -m mmbench report --db benchmark.db --run 1 --out report.html
    python -m mmbench serve --db benchmark.db

``run`` defaults to the deterministic mock assistants so a full sweep, store,
and dashboard can be produced with no external credentials. Pass real assistant
names (``claude``/``codex``/``gemini``) to evaluate live harnesses where their
CLIs and keys are available.
"""

from __future__ import annotations

import argparse
import sys

from mmbench.dataset import _main as dataset_main
from mmbench.dataset import pinned_hash
from mmbench.harness import Harness
from mmbench.sweep import Sweep, SweepConfig
from mmbench.tasks import TASKS, TASKS_BY_ID
from mmbench.types import AssistantSpec, Profile, SweepMode

_CLI_ASSISTANTS = {"claude", "codex", "gemini"}


def _assistant(name: str) -> AssistantSpec:
    """Build an assistant spec, routing CLI names to the cli adapter."""
    if name in _CLI_ASSISTANTS:
        return AssistantSpec(name=name, adapter=name, command=name)
    return AssistantSpec(name=name, adapter=name)


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute a sweep and optionally render a static report."""
    assistants = [_assistant(n) for n in args.assistants.split(",") if n]
    profiles = [Profile(name=n) for n in args.profiles.split(",") if n]
    tasks = list(TASKS) if args.tasks == "all" else [TASKS_BY_ID[t] for t in args.tasks.split(",")]
    config = SweepConfig(
        sweep_mode=SweepMode(args.sweep_mode),
        assistants=assistants,
        profiles=profiles or [Profile.none()],
        tasks=tasks,
        repeats=args.repeats,
        max_turns=args.max_turns,
        timeout_s=args.timeout,
        max_cost_usd=args.max_cost,
        label=args.label,
    )
    from mmbench.store import Store

    with Store(args.db) as store:
        sweep = Sweep(Harness(), store)
        run_id = sweep.run(config, dataset_hash=pinned_hash())
        print(f"run {run_id} complete · db={args.db}")
        if args.report:
            from mmbench.report import build_report

            out = build_report(store, run_id, args.report)
            print(f"report written: {out}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from mmbench.report import build_report
    from mmbench.store import Store

    with Store(args.db) as store:
        out = build_report(store, args.run, args.out)
    print(f"report written: {out}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from mmbench.app import main as serve_main

    return serve_main(["--db", args.db, "--host", args.host, "--port", str(args.port)])


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to a subcommand."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="mmbench")
    sub = parser.add_subparsers(dest="command", required=True)

    p_data = sub.add_parser("dataset", help="freeze or verify the corpus pin")
    p_data.add_argument("action", choices=["freeze", "verify"])

    p_run = sub.add_parser("run", help="run a benchmark sweep")
    p_run.add_argument("--db", default="benchmark.db")
    p_run.add_argument("--assistants", default="mock-strong,mock-weak")
    p_run.add_argument("--profiles", default="")
    p_run.add_argument("--tasks", default="all")
    p_run.add_argument("--repeats", type=int, default=1)
    p_run.add_argument("--sweep-mode", default="assistant", choices=[m.value for m in SweepMode])
    p_run.add_argument("--max-turns", type=int, default=20)
    p_run.add_argument("--timeout", type=float, default=120.0)
    p_run.add_argument("--max-cost", type=float, default=0.0)
    p_run.add_argument("--label", default="")
    p_run.add_argument("--report", default="")

    p_report = sub.add_parser("report", help="render a static HTML report")
    p_report.add_argument("--db", default="benchmark.db")
    p_report.add_argument("--run", type=int, required=True)
    p_report.add_argument("--out", default="report.html")

    p_serve = sub.add_parser("serve", help="serve the interactive dashboard")
    p_serve.add_argument("--db", default="benchmark.db")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8008)

    args = parser.parse_args(argv)
    if args.command == "dataset":
        return dataset_main(["dataset", args.action])
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "serve":
        return _cmd_serve(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
