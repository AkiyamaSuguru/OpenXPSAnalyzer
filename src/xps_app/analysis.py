"""Numerical summaries for imported spectra."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from xps_app.models import Spectrum, SpectrumType


@dataclass(frozen=True, slots=True)
class ComponentMetric:
    name: str
    peak_position_ev: float
    peak_height: float
    area: float


@dataclass(frozen=True, slots=True)
class SpectrumMetrics:
    point_count: int
    energy_min: float
    energy_max: float
    intensity_min: float
    intensity_max: float
    raw_peak_position_ev: float
    rmse: float | None = None
    mae: float | None = None
    r_squared: float | None = None
    components: tuple[ComponentMetric, ...] = ()


def _finite_peak_position(energy: np.ndarray, values: np.ndarray) -> tuple[float, float]:
    mask = np.isfinite(energy) & np.isfinite(values)
    if not mask.any():
        return float("nan"), float("nan")
    valid_energy = energy[mask]
    valid_values = values[mask]
    index = int(np.nanargmax(valid_values))
    return float(valid_energy[index]), float(valid_values[index])


def analyze_spectrum(
    spectrum: Spectrum,
    component_mode: str = "absolute",
) -> SpectrumMetrics:
    """Calculate preview statistics and fit-quality indicators."""

    if component_mode not in {"absolute", "relative"}:
        raise ValueError("component_mode must be 'absolute' or 'relative'.")
    energy = spectrum.data["binding_energy"].values.astype(float)
    intensity = spectrum.data["intensity"].values.astype(float)
    peak_position, _ = _finite_peak_position(energy, intensity)
    finite_energy = energy[np.isfinite(energy)]
    finite_intensity = intensity[np.isfinite(intensity)]

    common = dict(
        point_count=spectrum.point_count,
        energy_min=float(np.min(finite_energy)),
        energy_max=float(np.max(finite_energy)),
        intensity_min=float(np.min(finite_intensity)),
        intensity_max=float(np.max(finite_intensity)),
        raw_peak_position_ev=peak_position,
    )
    if spectrum.spectrum_type is SpectrumType.RAW:
        return SpectrumMetrics(**common)

    fit = spectrum.data["fitting_curve"].values.astype(float)
    background = spectrum.data["background"].values.astype(float)
    mask = np.isfinite(intensity) & np.isfinite(fit)
    residual = intensity[mask] - fit[mask]
    rmse = float(np.sqrt(np.mean(residual**2)))
    mae = float(np.mean(np.abs(residual)))
    denominator = float(np.sum((intensity[mask] - np.mean(intensity[mask])) ** 2))
    r_squared = float(1 - np.sum(residual**2) / denominator) if denominator > 0 else None

    component_metrics: list[ComponentMetric] = []
    for index, name in enumerate(spectrum.components):
        stored = spectrum.data["component_intensity"].isel(component=index).values.astype(float)
        plotted = stored if component_mode == "absolute" else background + stored
        relative_values = stored - background if component_mode == "absolute" else stored
        peak_mask = np.isfinite(energy) & np.isfinite(relative_values) & np.isfinite(plotted)
        if peak_mask.any():
            valid_energy = energy[peak_mask]
            valid_relative = relative_values[peak_mask]
            valid_plotted = plotted[peak_mask]
            peak_index = int(np.nanargmax(valid_relative))
            position = float(valid_energy[peak_index])
            height = float(valid_plotted[peak_index])
        else:
            position = float("nan")
            height = float("nan")
        area_mask = np.isfinite(energy) & np.isfinite(relative_values)
        x = energy[area_mask]
        y = np.clip(relative_values[area_mask], 0, None)
        order = np.argsort(x)
        area = float(np.trapezoid(y[order], x[order])) if len(x) > 1 else 0.0
        component_metrics.append(
            ComponentMetric(
                name=name,
                peak_position_ev=position,
                peak_height=height,
                area=area,
            )
        )

    return SpectrumMetrics(
        **common,
        rmse=rmse,
        mae=mae,
        r_squared=r_squared,
        components=tuple(component_metrics),
    )
