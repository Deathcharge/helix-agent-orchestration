"""Allow `python -m helix_orchestration` after installation."""

from .cli import main

raise SystemExit(main())
