# SPDX-FileCopyrightText: 2026 Jay Ma
# SPDX-License-Identifier: AGPL-3.0-only

"""Flet entry point."""

import flet as ft

from xps_app.app import main

if __name__ == "__main__":
    ft.run(main)
