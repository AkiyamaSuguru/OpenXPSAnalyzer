from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from xps_app.constants import BE_COL, FIT_COL
from xps_app.models import Spectrum, SpectrumType, XPSProject, detect_spectrum_type
from xps_app.storage import load_project, project_to_dataset, project_to_datatree, save_project


def test_spectrum_dataframe_round_trip(fitted_frame: pd.DataFrame) -> None:
    spectrum = Spectrum.from_dataframe("C 1s", fitted_frame, "source.xlsx")

    assert spectrum.spectrum_type is SpectrumType.FIT
    assert spectrum.components == ["C–C", "C–O"]
    assert spectrum.point_count == len(fitted_frame)
    pd.testing.assert_frame_equal(spectrum.to_dataframe(), fitted_frame)
    assert isinstance(spectrum.data, xr.Dataset)
    assert spectrum.data["binding_energy"].attrs["units"] == "eV"


def test_project_netcdf_round_trip_with_ragged_spectra(
    tmp_path: Path, raw_frame: pd.DataFrame, fitted_frame: pd.DataFrame
) -> None:
    project = XPSProject("coating study")
    raw = Spectrum.from_dataframe("Survey", raw_frame)
    fitted = Spectrum.from_dataframe("C 1s", fitted_frame)
    project.add(raw)
    project.add(fitted)
    target = tmp_path / "study.nc"

    saved = save_project(project, target)
    loaded = load_project(saved)

    assert saved.is_file()
    assert loaded.name == "coating study"
    assert list(loaded.spectra) == [raw.spectrum_id, fitted.spectrum_id]
    assert loaded.get(raw.spectrum_id).spectrum_type is SpectrumType.RAW
    pd.testing.assert_frame_equal(loaded.get(fitted.spectrum_id).to_dataframe(), fitted_frame)
    assert loaded.dirty is False


def test_project_dataset_contains_labeled_dimensions(
    raw_frame: pd.DataFrame, fitted_frame: pd.DataFrame
) -> None:
    project = XPSProject("demo")
    project.add(Spectrum.from_dataframe("survey", raw_frame))
    project.add(Spectrum.from_dataframe("c1s", fitted_frame))

    dataset = project_to_dataset(project)

    assert dataset.sizes["spectrum"] == 2
    assert dataset.sizes["point"] == max(len(raw_frame), len(fitted_frame))
    assert dataset.coords["component"].values.tolist() == ["C–C", "C–O"]
    assert dataset.attrs["storage_format"] == "NetCDF-4/HDF5"


def test_project_datatree_uses_sample_and_file_stem_paths(
    raw_frame: pd.DataFrame, fitted_frame: pd.DataFrame
) -> None:
    project = XPSProject("B1_sic")
    project.add(Spectrum.from_dataframe("survey", raw_frame, sample="B1_sic", region="survey"))
    project.add(Spectrum.from_dataframe("C1s", fitted_frame, sample="B1_sic", region="C1s"))

    tree = project_to_datatree(project)

    assert tree.groups == ("/", "/B1_sic", "/B1_sic/survey", "/B1_sic/C1s")
    assert tree["/B1_sic/C1s"].attrs["region"] == "C1s"
    assert tree.attrs["storage_layout"] == "xarray-datatree"


def test_detects_raw_and_rejects_half_fitted(raw_frame: pd.DataFrame) -> None:
    assert detect_spectrum_type(raw_frame) is SpectrumType.RAW
    incomplete = raw_frame.copy()
    incomplete[FIT_COL] = np.ones(len(incomplete))
    try:
        detect_spectrum_type(incomplete)
    except ValueError as exc:
        assert "Background" in str(exc)
    else:
        raise AssertionError("partial fit data must be rejected")


def test_duplicate_names_are_disambiguated(raw_frame: pd.DataFrame) -> None:
    project = XPSProject()
    first = Spectrum.from_dataframe("Survey", raw_frame)
    second = Spectrum.from_dataframe("Survey", raw_frame)
    project.add(first)
    project.add(second)

    assert [item.name for item in project.spectra.values()] == ["Survey", "Survey (2)"]
    assert second.to_dataframe()[BE_COL].equals(raw_frame[BE_COL])
