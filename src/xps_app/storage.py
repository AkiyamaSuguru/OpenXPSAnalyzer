"""NetCDF-4/HDF5 persistence for complete XPS projects."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

from xps_app.constants import SCHEMA_NAME, SCHEMA_VERSION
from xps_app.exceptions import XPSStorageError
from xps_app.models import Spectrum, SpectrumType, XPSProject


def project_to_dataset(project: XPSProject) -> xr.Dataset:
    """Pack spectra of unequal lengths into one labeled xarray Dataset.

    The ``point`` dimension is padded with NaN and ``point_count`` records each
    spectrum's true length.  Component names form a union coordinate, while
    ``component_present`` distinguishes missing components from all-NaN data.
    """

    spectra = list(project.spectra.values())
    if not spectra:
        raise XPSStorageError("项目中没有可保存的谱图。")

    spectrum_ids = [spectrum.spectrum_id for spectrum in spectra]
    max_points = max(spectrum.point_count for spectrum in spectra)
    component_names = list(
        dict.fromkeys(component for spectrum in spectra for component in spectrum.components)
    )
    n_spectra = len(spectra)
    n_components = len(component_names)

    shape = (n_spectra, max_points)
    binding_energy = np.full(shape, np.nan, dtype=np.float64)
    intensity = np.full(shape, np.nan, dtype=np.float64)
    fitting_curve = np.full(shape, np.nan, dtype=np.float64)
    background = np.full(shape, np.nan, dtype=np.float64)
    component_intensity = np.full((n_spectra, n_components, max_points), np.nan, dtype=np.float64)
    component_present = np.zeros((n_spectra, n_components), dtype=np.int8)
    point_count = np.zeros(n_spectra, dtype=np.int64)

    names: list[str] = []
    types: list[str] = []
    sources: list[str] = []
    samples: list[str] = []
    regions: list[str] = []
    created: list[str] = []
    component_index = {name: index for index, name in enumerate(component_names)}

    for row, spectrum in enumerate(spectra):
        count = spectrum.point_count
        point_count[row] = count
        binding_energy[row, :count] = spectrum.data["binding_energy"].values
        intensity[row, :count] = spectrum.data["intensity"].values
        names.append(spectrum.name)
        types.append(spectrum.spectrum_type.value)
        sources.append(spectrum.source_path)
        samples.append(spectrum.sample)
        regions.append(spectrum.region)
        created.append(str(spectrum.data.attrs.get("created_at", "")))

        if spectrum.spectrum_type is SpectrumType.FIT:
            fitting_curve[row, :count] = spectrum.data["fitting_curve"].values
            background[row, :count] = spectrum.data["background"].values
            for local_index, component in enumerate(spectrum.components):
                column = component_index[component]
                component_present[row, column] = 1
                component_intensity[row, column, :count] = spectrum.data[
                    "component_intensity"
                ].isel(component=local_index)

    data_vars: dict[str, object] = {
        "binding_energy": (("spectrum", "point"), binding_energy),
        "intensity": (("spectrum", "point"), intensity),
        "fitting_curve": (("spectrum", "point"), fitting_curve),
        "background": (("spectrum", "point"), background),
        "point_count": (("spectrum",), point_count),
        "spectrum_name": (("spectrum",), np.asarray(names, dtype=str)),
        "spectrum_type": (("spectrum",), np.asarray(types, dtype=str)),
        "source_path": (("spectrum",), np.asarray(sources, dtype=str)),
        "sample_name": (("spectrum",), np.asarray(samples, dtype=str)),
        "region_name": (("spectrum",), np.asarray(regions, dtype=str)),
        "created_at": (("spectrum",), np.asarray(created, dtype=str)),
    }
    coordinates: dict[str, object] = {
        "spectrum": np.asarray(spectrum_ids, dtype=str),
        "point": np.arange(max_points, dtype=np.int64),
    }
    if component_names:
        coordinates["component"] = np.asarray(component_names, dtype=str)
        data_vars["component_intensity"] = (
            ("spectrum", "component", "point"),
            component_intensity,
        )
        data_vars["component_present"] = (
            ("spectrum", "component"),
            component_present,
        )

    dataset = xr.Dataset(
        data_vars=data_vars,
        coords=coordinates,
        attrs={
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "project_name": project.name,
            "saved_at": datetime.now(UTC).isoformat(),
            "storage_format": "NetCDF-4/HDF5",
            "storage_layout": "flat-padded",
        },
    )
    dataset["binding_energy"].attrs.update(units="eV", long_name="Binding Energy")
    for variable in ("intensity", "fitting_curve", "background"):
        dataset[variable].attrs.update(units="a.u.")
    if "component_intensity" in dataset:
        dataset["component_intensity"].attrs.update(units="a.u.")
    return dataset


def dataset_to_project(dataset: xr.Dataset, file_path: str | Path | None = None) -> XPSProject:
    """Unpack a project Dataset and validate its schema."""

    if dataset.attrs.get("schema_name") != SCHEMA_NAME:
        raise XPSStorageError("该 NetCDF 文件不是 OpenXPSAnalyzer 项目。")
    if str(dataset.attrs.get("schema_version")) != SCHEMA_VERSION:
        raise XPSStorageError(
            "不支持的项目格式版本："
            f"{dataset.attrs.get('schema_version', 'unknown')}（当前支持 {SCHEMA_VERSION}）。"
        )
    required = {
        "binding_energy",
        "intensity",
        "fitting_curve",
        "background",
        "point_count",
        "spectrum_name",
        "spectrum_type",
    }
    missing = sorted(required.difference(dataset.variables))
    if "component" in dataset.coords:
        missing.extend(
            variable
            for variable in ("component_intensity", "component_present")
            if variable not in dataset.variables
        )
    if missing:
        raise XPSStorageError(f"NetCDF 项目缺少变量：{sorted(set(missing))}")

    project = XPSProject(name=str(dataset.attrs.get("project_name", "Untitled project")))
    spectrum_ids = [str(value) for value in dataset.coords["spectrum"].values.tolist()]
    all_components = (
        [str(value) for value in dataset.coords["component"].values.tolist()]
        if "component" in dataset.coords
        else []
    )

    from xps_app.constants import BE_COL, BG_COL, FIT_COL, INTENSITY_COL

    for row, spectrum_id in enumerate(spectrum_ids):
        count = int(dataset["point_count"].isel(spectrum=row).item())
        if count <= 0 or count > dataset.sizes["point"]:
            raise XPSStorageError(f"谱图 {spectrum_id} 的 point_count 无效：{count}")
        frame_data: dict[str, np.ndarray] = {
            BE_COL: dataset["binding_energy"].isel(spectrum=row, point=slice(0, count)).values,
            INTENSITY_COL: dataset["intensity"].isel(spectrum=row, point=slice(0, count)).values,
        }
        spectrum_type = str(dataset["spectrum_type"].isel(spectrum=row).item())
        if spectrum_type == SpectrumType.FIT.value:
            frame_data[FIT_COL] = (
                dataset["fitting_curve"].isel(spectrum=row, point=slice(0, count)).values
            )
            if all_components:
                present = dataset["component_present"].isel(spectrum=row).values.astype(bool)
                for component_index, component in enumerate(all_components):
                    if present[component_index]:
                        frame_data[component] = (
                            dataset["component_intensity"]
                            .isel(
                                spectrum=row,
                                component=component_index,
                                point=slice(0, count),
                            )
                            .values
                        )
            frame_data[BG_COL] = (
                dataset["background"].isel(spectrum=row, point=slice(0, count)).values
            )
        elif spectrum_type != SpectrumType.RAW.value:
            raise XPSStorageError(f"未知的谱图类型：{spectrum_type}")

        import pandas as pd

        name = str(dataset["spectrum_name"].isel(spectrum=row).item())
        source = (
            str(dataset["source_path"].isel(spectrum=row).item())
            if "source_path" in dataset
            else ""
        )
        spectrum = Spectrum.from_dataframe(
            name=name,
            frame=pd.DataFrame(frame_data),
            source_path=source,
            spectrum_id=spectrum_id,
            sample=(
                str(dataset["sample_name"].isel(spectrum=row).item())
                if "sample_name" in dataset
                else None
            ),
            region=(
                str(dataset["region_name"].isel(spectrum=row).item())
                if "region_name" in dataset
                else name
            ),
        )
        if "created_at" in dataset:
            spectrum.data.attrs["created_at"] = str(dataset["created_at"].isel(spectrum=row).item())
        project.spectra[spectrum_id] = spectrum

    project.file_path = Path(file_path) if file_path is not None else None
    project.dirty = False
    return project


def _group_name(value: str, fallback: str) -> str:
    cleaned = str(value).strip().replace("/", "_").replace("\\", "_")
    return cleaned or fallback


def project_to_datatree(project: XPSProject) -> xr.DataTree:
    """Build the GMA-compatible ``/{sample}/{file_stem}`` xarray hierarchy."""

    if not project.spectra:
        raise XPSStorageError("项目中没有可保存的谱图。")
    root_dataset = xr.Dataset(
        attrs={
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "project_name": project.name,
            "saved_at": datetime.now(UTC).isoformat(),
            "storage_format": "NetCDF-4/HDF5",
            "storage_layout": "xarray-datatree",
        }
    )
    tree = xr.DataTree(dataset=root_dataset, name="XPS")
    for spectrum in project.spectra.values():
        sample = _group_name(spectrum.sample or project.name, "sample")
        region = _group_name(spectrum.name, spectrum.region or "spectrum")
        dataset = spectrum.data.copy(deep=True)
        dataset.attrs.update(
            spectrum_id=spectrum.spectrum_id,
            name=spectrum.name,
            sample=spectrum.sample or project.name,
            region=spectrum.region,
            xarray_path=f"/{sample}/{region}",
        )
        tree[f"/{sample}/{region}"] = dataset
    return tree


def datatree_to_project(
    tree: xr.DataTree,
    file_path: str | Path | None = None,
) -> XPSProject:
    """Restore an XPS project from a named xarray DataTree."""

    if tree.attrs.get("schema_name") != SCHEMA_NAME:
        raise XPSStorageError("该 NetCDF 文件不是 OpenXPSAnalyzer 项目。")
    if str(tree.attrs.get("schema_version")) != SCHEMA_VERSION:
        raise XPSStorageError(
            "不支持的项目格式版本："
            f"{tree.attrs.get('schema_version', 'unknown')}（当前支持 {SCHEMA_VERSION}）。"
        )
    project = XPSProject(name=str(tree.attrs.get("project_name", "Untitled project")))
    for group in tree.groups:
        if group == "/":
            continue
        dataset = tree[group].to_dataset(inherit=False)
        if "intensity" not in dataset.data_vars:
            continue
        try:
            spectrum = Spectrum.from_dataset(dataset)
        except Exception as exc:
            raise XPSStorageError(f"DataTree 节点 {group} 无效：{exc}") from exc
        project.spectra[spectrum.spectrum_id] = spectrum
    if not project.spectra:
        raise XPSStorageError("NetCDF DataTree 中没有找到 XPS 谱图节点。")
    project.file_path = Path(file_path) if file_path is not None else None
    project.dirty = False
    return project


def save_project(project: XPSProject, file_path: str | Path) -> Path:
    """Atomically save a project as a named xarray DataTree in NetCDF-4."""

    path = Path(file_path).expanduser()
    if path.suffix.lower() not in {".nc", ".nc4", ".netcdf"}:
        path = path.with_suffix(".nc")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    tree = project_to_datatree(project)
    try:
        tree.to_netcdf(temporary, engine="h5netcdf")
        temporary.replace(path)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        raise XPSStorageError(f"无法保存 NetCDF 项目：{exc}") from exc
    project.file_path = path
    project.dirty = False
    return path


def load_project(file_path: str | Path) -> XPSProject:
    """Open and fully load an OpenXPSAnalyzer NetCDF project."""

    path = Path(file_path).expanduser()
    if not path.is_file():
        raise XPSStorageError(f"找不到 NetCDF 项目：{path}")
    try:
        with xr.open_dataset(path, engine="h5netcdf") as opened:
            layout = str(opened.attrs.get("storage_layout", "flat-padded"))
        if layout == "xarray-datatree":
            tree = xr.load_datatree(path, engine="h5netcdf")
            return datatree_to_project(tree, file_path=path)
        with xr.open_dataset(path, engine="h5netcdf") as opened:
            dataset = opened.load()
        return dataset_to_project(dataset, file_path=path)
    except XPSStorageError:
        raise
    except Exception as exc:
        raise XPSStorageError(f"无法打开 NetCDF 项目：{exc}") from exc
