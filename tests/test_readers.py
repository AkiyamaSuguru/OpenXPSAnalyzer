from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from xps_app.constants import BE_COL, BG_COL, FIT_COL, INTENSITY_COL
from xps_app.exceptions import XPSDataError
from xps_app.readers import element_reader, read_avantage, survey_reader


def _write_avantage(path: Path, frame: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, startrow=15)


def test_survey_reader_skips_header_and_renames_columns(tmp_path: Path) -> None:
    source = pd.DataFrame({"Kinetic": [290, 289, 288], "Counts": [10, 20, 30]})
    path = tmp_path / "survey.xlsx"
    _write_avantage(path, source)

    result = survey_reader(path)

    assert list(result.columns) == [BE_COL, INTENSITY_COL]
    assert result.shape == (3, 2)
    assert result.iloc[0].tolist() == [290, 10]


def test_element_reader_assigns_component_names(tmp_path: Path) -> None:
    source = pd.DataFrame(
        {
            "Energy": [290, 289],
            "Raw": [10, 20],
            "Envelope": [11, 19],
            "Peak 1": [6, 8],
            "Peak 2": [5, 11],
            "Shirley": [1, 1],
        }
    )
    path = tmp_path / "c1s.xlsx"
    _write_avantage(path, source)

    result = element_reader(path, peaks=["C–C", "C–O"])

    assert list(result.columns) == [BE_COL, INTENSITY_COL, FIT_COL, "C–C", "C–O", BG_COL]
    assert read_avantage(path, kind="auto").shape == (2, 6)


def test_element_reader_rejects_wrong_peak_count(tmp_path: Path) -> None:
    source = pd.DataFrame(
        {
            "E": [1],
            "I": [2],
            "F": [2],
            "P1": [1],
            "P2": [1],
            "B": [0],
        }
    )
    path = tmp_path / "bad.xlsx"
    _write_avantage(path, source)

    with pytest.raises(XPSDataError, match="期望 2 个"):
        element_reader(path, peaks=["only-one"])


def test_reader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(XPSDataError, match="找不到"):
        survey_reader(tmp_path / "missing.xlsx")
