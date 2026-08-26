from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from xps_app.constants import BE_COL, BG_COL, FIT_COL, INTENSITY_COL


@pytest.fixture
def raw_frame() -> pd.DataFrame:
    energy = np.linspace(300.0, 280.0, 41)
    intensity = 50 + 180 * np.exp(-0.5 * ((energy - 288.0) / 1.3) ** 2)
    return pd.DataFrame({BE_COL: energy, INTENSITY_COL: intensity})


@pytest.fixture
def fitted_frame() -> pd.DataFrame:
    energy = np.linspace(292.0, 280.0, 61)
    background = np.full_like(energy, 100.0)
    c_c = background + 400 * np.exp(-0.5 * ((energy - 285.0) / 0.45) ** 2)
    c_o = background + 220 * np.exp(-0.5 * ((energy - 287.0) / 0.70) ** 2)
    fit = c_c + c_o - background
    return pd.DataFrame(
        {
            BE_COL: energy,
            INTENSITY_COL: fit.copy(),
            FIT_COL: fit,
            "C–C": c_c,
            "C–O": c_o,
            BG_COL: background,
        }
    )
