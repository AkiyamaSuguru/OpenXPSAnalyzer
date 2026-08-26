from __future__ import annotations

import os
from pathlib import Path

import pytest
import xarray as xr

from xps_app.analysis import analyze_spectrum
from xps_app.importers import project_from_avantage_folder
from xps_app.models import SpectrumType
from xps_app.multipanel import MultiPanelConfig, render_multi_panel_figure
from xps_app.storage import load_project, save_project

REAL_B1_FOLDER = Path(os.environ.get("XPS_B1_TEST_DIR", str(Path.home() / "Desktop" / "B1_sic")))


@pytest.mark.skipif(not REAL_B1_FOLDER.is_dir(), reason="real B1_sic fixture is not available")
def test_real_b1_sic_folder_and_netcdf_datatree(tmp_path: Path) -> None:
    project = project_from_avantage_folder(REAL_B1_FOLDER)

    assert project.name == "B1_sic"
    assert [spectrum.name for spectrum in project.spectra.values()] == [
        "C1s",
        "F1s",
        "K2p",
        "Li1s",
        "Na1s",
        "O1s",
        "Si2p",
        "survey",
    ]
    by_name = {spectrum.name: spectrum for spectrum in project.spectra.values()}
    assert by_name["survey"].spectrum_type is SpectrumType.RAW
    assert by_name["survey"].point_count == 1361
    assert by_name["C1s"].spectrum_type is SpectrumType.FIT
    assert by_name["C1s"].point_count == 191
    assert by_name["C1s"].components == [
        "C1s Scan A",
        "C1s Scan B",
        "C1s Scan C",
        "C1s Scan D",
        "C1s Scan E",
        "C1s Scan F",
        "C1s Scan G",
    ]
    assert [
        metric.peak_position_ev for metric in analyze_spectrum(by_name["K2p"]).components
    ] == pytest.approx([292.8, 295.7])

    multi_panel = render_multi_panel_figure(
        [by_name[name] for name in ("survey", "C1s", "K2p", "O1s")],
        MultiPanelConfig(rows=2, cols=2, show_legend=False, dpi=100),
        labels=["(a)", "(b)", "(c)", "(d)"],
        preview=True,
    )
    assert multi_panel.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(multi_panel) > 20_000

    target = save_project(project, tmp_path / "B1_sic.nc")
    tree = xr.load_datatree(target, engine="h5netcdf")
    assert "/B1_sic/C1s" in tree.groups
    assert "/B1_sic/survey" in tree.groups

    loaded = load_project(target)
    assert len(loaded) == 8
    assert {spectrum.region for spectrum in loaded.spectra.values()} == set(by_name)
