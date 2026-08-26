"""xarray-backed XPS domain models."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import xarray as xr

from xps_app.constants import (
    BE_COL,
    BG_COL,
    FIT_COL,
    FIT_REQUIRED_COLUMNS,
    INTENSITY_COL,
    RAW_REQUIRED_COLUMNS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    STANDARD_COLUMNS,
)
from xps_app.exceptions import XPSDataError


class SpectrumType(StrEnum):
    RAW = "raw"
    FIT = "fit"


def detect_spectrum_type(frame: pd.DataFrame) -> SpectrumType:
    """Validate and identify raw versus fitted XPS data."""

    missing_raw = [column for column in RAW_REQUIRED_COLUMNS if column not in frame.columns]
    if missing_raw:
        raise XPSDataError(f"缺少必要列：{missing_raw}")
    has_fit = FIT_COL in frame.columns
    has_bg = BG_COL in frame.columns
    if has_fit and has_bg:
        return SpectrumType.FIT
    if not has_fit and not has_bg:
        return SpectrumType.RAW
    missing = [column for column in (FIT_COL, BG_COL) if column not in frame.columns]
    raise XPSDataError(f"拟合谱数据不完整，缺少列：{missing}")


@dataclass(slots=True)
class Spectrum:
    """One XPS spectrum stored as an xarray Dataset."""

    name: str
    data: xr.Dataset
    spectrum_id: str = field(default_factory=lambda: uuid4().hex)
    source_path: str = ""

    @classmethod
    def from_dataframe(
        cls,
        name: str,
        frame: pd.DataFrame,
        source_path: str | Path = "",
        spectrum_id: str | None = None,
        sample: str | None = None,
        region: str | None = None,
    ) -> Spectrum:
        spectrum_type = detect_spectrum_type(frame)
        required = (
            FIT_REQUIRED_COLUMNS if spectrum_type is SpectrumType.FIT else RAW_REQUIRED_COLUMNS
        )
        clean = frame.copy()
        for column in clean.columns:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=list(required)).reset_index(drop=True)
        if clean.empty:
            raise XPSDataError("谱图没有可用的数据点。")

        point = np.arange(len(clean), dtype=np.int64)
        variables: dict[str, tuple[tuple[str, ...], np.ndarray]] = {
            "intensity": (("point",), clean[INTENSITY_COL].to_numpy(dtype=float)),
        }
        coordinates: dict[str, object] = {
            "point": point,
            "binding_energy": (("point",), clean[BE_COL].to_numpy(dtype=float)),
        }

        component_columns: list[str] = []
        if spectrum_type is SpectrumType.FIT:
            variables["fitting_curve"] = (
                ("point",),
                clean[FIT_COL].to_numpy(dtype=float),
            )
            variables["background"] = (
                ("point",),
                clean[BG_COL].to_numpy(dtype=float),
            )
            component_columns = [
                str(column) for column in clean.columns if column not in STANDARD_COLUMNS
            ]
            invalid_components = [
                column for column in component_columns if not clean[column].notna().any()
            ]
            if invalid_components:
                raise XPSDataError(f"分峰列中没有数值数据：{invalid_components}")
            if component_columns:
                variables["component_intensity"] = (
                    ("component", "point"),
                    clean[component_columns].to_numpy(dtype=float).T,
                )
                coordinates["component"] = np.asarray(component_columns, dtype=str)

        now = datetime.now(UTC).isoformat()
        source = Path(source_path) if str(source_path) else None
        resolved_region = (region or (source.stem if source else name)).strip() or name
        resolved_sample = (sample or (source.parent.name if source else "")).strip()
        dataset = xr.Dataset(
            data_vars=variables,
            coords=coordinates,
            attrs={
                "schema_name": SCHEMA_NAME,
                "schema_version": SCHEMA_VERSION,
                "spectrum_type": spectrum_type.value,
                "name": name.strip() or "Untitled",
                "source_path": str(source_path),
                "source_file": source.name if source else "",
                "sample": resolved_sample,
                "region": resolved_region,
                "xarray_name": resolved_region,
                "created_at": now,
            },
        )
        dataset["binding_energy"].attrs.update(units="eV", long_name=BE_COL)
        dataset["intensity"].attrs.update(units="a.u.", long_name=INTENSITY_COL)
        if "fitting_curve" in dataset:
            dataset["fitting_curve"].attrs.update(units="a.u.", long_name=FIT_COL)
            dataset["background"].attrs.update(units="a.u.", long_name=BG_COL)
        if "component_intensity" in dataset:
            dataset["component_intensity"].attrs.update(
                units="a.u.", long_name="Fitted component intensity"
            )
        return cls(
            name=dataset.attrs["name"],
            data=dataset,
            spectrum_id=spectrum_id or uuid4().hex,
            source_path=str(source_path),
        )

    @classmethod
    def from_dataset(cls, dataset: xr.Dataset) -> Spectrum:
        """Restore one Spectrum from a DataTree leaf Dataset."""

        required = {"binding_energy", "intensity"}
        missing = sorted(required.difference(dataset.variables))
        if missing:
            raise XPSDataError(f"xarray 谱图缺少变量：{missing}")
        spectrum_type = SpectrumType(str(dataset.attrs.get("spectrum_type", "raw")))
        if spectrum_type is SpectrumType.FIT:
            fit_missing = sorted({"fitting_curve", "background"}.difference(dataset.variables))
            if fit_missing:
                raise XPSDataError(f"拟合谱 xarray 数据缺少变量：{fit_missing}")
        loaded = dataset.load().copy(deep=True)
        name = str(loaded.attrs.get("name") or loaded.attrs.get("region") or "Untitled")
        return cls(
            name=name,
            data=loaded,
            spectrum_id=str(loaded.attrs.get("spectrum_id") or uuid4().hex),
            source_path=str(loaded.attrs.get("source_path", "")),
        )

    @property
    def spectrum_type(self) -> SpectrumType:
        return SpectrumType(self.data.attrs["spectrum_type"])

    @property
    def components(self) -> list[str]:
        if "component" not in self.data.coords:
            return []
        return [str(value) for value in self.data.coords["component"].values.tolist()]

    @property
    def point_count(self) -> int:
        return int(self.data.sizes["point"])

    @property
    def sample(self) -> str:
        return str(self.data.attrs.get("sample", ""))

    @property
    def region(self) -> str:
        return str(self.data.attrs.get("region", self.name))

    def rename_components(self, names: list[str]) -> None:
        """Rename component labels while preserving their order and values."""

        if len(names) != len(self.components):
            raise XPSDataError(
                f"分峰名称数量错误。期望 {len(self.components)} 个，实际 {len(names)} 个。"
            )
        cleaned = [str(name).strip() for name in names]
        if any(not name for name in cleaned):
            raise XPSDataError("分峰名称不能为空。")
        if len(set(cleaned)) != len(cleaned):
            raise XPSDataError("分峰名称不能重复。")
        self.data = self.data.assign_coords(component=np.asarray(cleaned, dtype=str))

    def to_dataframe(self) -> pd.DataFrame:
        values: dict[str, np.ndarray] = {
            BE_COL: self.data["binding_energy"].values,
            INTENSITY_COL: self.data["intensity"].values,
        }
        if self.spectrum_type is SpectrumType.FIT:
            values[FIT_COL] = self.data["fitting_curve"].values
            for index, component in enumerate(self.components):
                values[component] = self.data["component_intensity"].isel(component=index).values
            values[BG_COL] = self.data["background"].values
        return pd.DataFrame(values)


@dataclass
class XPSProject:
    """In-memory collection used by the application and storage layer."""

    name: str = "Untitled project"
    spectra: OrderedDict[str, Spectrum] = field(default_factory=OrderedDict)
    file_path: Path | None = None
    dirty: bool = False

    def add(self, spectrum: Spectrum) -> None:
        if spectrum.spectrum_id in self.spectra:
            raise XPSDataError(f"谱图 ID 已存在：{spectrum.spectrum_id}")
        existing_names = {item.name for item in self.spectra.values()}
        original = spectrum.name
        suffix = 2
        while spectrum.name in existing_names:
            spectrum.name = f"{original} ({suffix})"
            spectrum.data.attrs["name"] = spectrum.name
            suffix += 1
        self.spectra[spectrum.spectrum_id] = spectrum
        self.dirty = True

    def remove(self, spectrum_id: str) -> Spectrum:
        try:
            spectrum = self.spectra.pop(spectrum_id)
        except KeyError as exc:
            raise XPSDataError(f"找不到谱图：{spectrum_id}") from exc
        self.dirty = True
        return spectrum

    def get(self, spectrum_id: str | None) -> Spectrum | None:
        if spectrum_id is None:
            return None
        return self.spectra.get(spectrum_id)

    def clear(self, name: str = "Untitled project") -> None:
        self.name = name
        self.spectra.clear()
        self.file_path = None
        self.dirty = False

    def __len__(self) -> int:
        return len(self.spectra)
