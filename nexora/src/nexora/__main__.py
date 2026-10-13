"""Allows `python -m nexora ...` as an alternative to the `nex` command."""

from .cli import main

raise SystemExit(main())
