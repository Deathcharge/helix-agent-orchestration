# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Allow the historical `python -m helix_orchestration` entry point."""

from samsarix_orchestration.cli import legacy_main

raise SystemExit(legacy_main())
