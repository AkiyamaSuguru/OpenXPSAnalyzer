# SPDX-FileCopyrightText: 2026 Jay Ma
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenXPSAnalyzer application package."""

from xps_app.models import Spectrum, SpectrumType, XPSProject

__all__ = ["Spectrum", "SpectrumType", "XPSProject"]
__version__ = "0.4.0"
