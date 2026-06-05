"""Pytest root for mmbench-agents.

Its presence puts this directory on ``sys.path`` so ``import mmbench``
resolves when tests run from anywhere. mm's own suite is scoped to
``tests/python`` (see ``pyproject.toml``), so these tests stay isolated.
"""
