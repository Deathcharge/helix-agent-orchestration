# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Allow `python -m samsarix_orchestration` after installation."""

from .cli import main

raise SystemExit(main())
