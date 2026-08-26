"""Flet-native interactive charts used by the application UI."""

from __future__ import annotations

from collections.abc import Sequence

import flet as ft
import flet_charts as fch
import numpy as np
from matplotlib.colors import to_hex

from xps_app.constants import BG_COL, FIT_COL, INTENSITY_COL
from xps_app.models import Spectrum, SpectrumType
from xps_app.plotting import Eplotter


def _chart_points(
    series_name: str,
    energy: np.ndarray,
    values: np.ndarray,
    energy_origin: float,
) -> list[fch.LineChartDataPoint]:
    mask = np.isfinite(energy) & np.isfinite(values)
    original_energy = energy[mask]
    x = energy_origin - original_energy
    y = values[mask]
    order = np.argsort(x)
    return [
        fch.LineChartDataPoint(
            x=float(x[index]),
            y=float(y[index]),
            tooltip=fch.LineChartDataPointTooltip(
                text=f"{series_name}: {original_energy[index]:.3f} eV · {y[index]:.5g}",
                text_style=ft.TextStyle(size=11, color=ft.Colors.WHITE),
            ),
        )
        for index in order
    ]


def _line_series(
    name: str,
    energy: np.ndarray,
    values: np.ndarray,
    color: str,
    energy_origin: float,
    width: float = 1.6,
    dash_pattern: Sequence[int] | None = None,
) -> fch.LineChartData:
    return fch.LineChartData(
        points=_chart_points(name, energy, values, energy_origin),
        color=color,
        stroke_width=width,
        dash_pattern=list(dash_pattern) if dash_pattern else None,
        point=False,
        selected_point=fch.ChartCirclePoint(
            color=color,
            radius=4,
            stroke_color=ft.Colors.WHITE,
            stroke_width=1.5,
        ),
        rounded_stroke_cap=True,
    )


def _energy_axis(energy: np.ndarray) -> tuple[fch.ChartAxis, float, float, float]:
    finite = energy[np.isfinite(energy)]
    energy_min = float(np.min(finite))
    energy_max = float(np.max(finite))
    ticks = np.linspace(energy_max, energy_min, 6)
    labels = [
        fch.ChartAxisLabel(
            value=energy_max - float(value),
            label=ft.Text(f"{value:.1f}", size=10, color="#50656B"),
        )
        for value in ticks
    ]
    axis = fch.ChartAxis(
        title=ft.Text("Binding Energy (eV)", size=11, color="#40565D"),
        title_size=26,
        labels=labels,
        label_size=22,
        show_min=False,
        show_max=False,
    )
    return axis, 0.0, energy_max - energy_min, energy_max


def _legend(items: Sequence[tuple[str, str]]) -> ft.Control:
    return ft.Row(
        [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(width=9, height=9, bgcolor=color, border_radius=99),
                        ft.Text(name, size=10, color="#40565D"),
                    ],
                    spacing=5,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                bgcolor="#F2F7F8",
                border_radius=99,
                border=ft.Border.all(1, "#D8E4E7"),
            )
            for name, color in items
        ],
        wrap=True,
        spacing=6,
        run_spacing=6,
    )


def build_interactive_spectrum_chart(
    spectrum: Spectrum,
    palette: str = "sci_default",
    component_mode: str = "absolute",
    show_legend: bool = True,
) -> ft.Control:
    """Build a cross-platform line chart with Plotly-like hover tooltips."""

    if component_mode not in {"absolute", "relative"}:
        raise ValueError("component_mode must be 'absolute' or 'relative'.")

    frame = spectrum.to_dataframe()
    energy = frame.iloc[:, 0].to_numpy(dtype=float)
    axis, min_x, max_x, energy_origin = _energy_axis(energy)
    series: list[fch.LineChartData] = []
    legend_items: list[tuple[str, str]] = []
    y_values: list[np.ndarray] = []

    raw = frame[INTENSITY_COL].to_numpy(dtype=float)
    raw_color = "#263238"
    series.append(_line_series("Raw data", energy, raw, raw_color, energy_origin, width=1.3))
    legend_items.append(("Raw data", raw_color))
    y_values.append(raw)

    if spectrum.spectrum_type is SpectrumType.FIT:
        fit = frame[FIT_COL].to_numpy(dtype=float)
        background = frame[BG_COL].to_numpy(dtype=float)
        series.append(_line_series("Fit", energy, fit, "#D1495B", energy_origin, width=2.1))
        series.append(
            _line_series(
                "Background",
                energy,
                background,
                "#7D8B91",
                energy_origin,
                dash_pattern=[6, 4],
            )
        )
        legend_items.extend([("Fit", "#D1495B"), ("Background", "#7D8B91")])
        y_values.extend([fit, background])

        plotter = Eplotter({spectrum.name: frame}, font_size=9)
        component_colors = [
            to_hex(color) for color in plotter.get_colors(spectrum.components, palette)
        ]
        for name, color in zip(spectrum.components, component_colors, strict=True):
            stored = frame[name].to_numpy(dtype=float)
            values = stored if component_mode == "absolute" else background + stored
            series.append(_line_series(name, energy, values, color, energy_origin, width=1.25))
            legend_items.append((name, color))
            y_values.append(values)

    finite_y = np.concatenate([values[np.isfinite(values)] for values in y_values])
    y_min = float(np.min(finite_y))
    y_max = float(np.max(finite_y))
    y_pad = max((y_max - y_min) * 0.06, abs(y_max) * 0.01, 1.0)

    chart = fch.LineChart(
        data_series=series,
        interactive=True,
        animation=250,
        min_x=min_x,
        max_x=max_x,
        min_y=y_min - y_pad,
        max_y=y_max + y_pad,
        bottom_axis=axis,
        left_axis=fch.ChartAxis(
            title=ft.Text("Intensity (a.u.)", size=11, color="#40565D"),
            title_size=32,
            show_labels=False,
        ),
        horizontal_grid_lines=fch.ChartGridLines(color="#E7EEF0", width=1, dash_pattern=[3, 4]),
        vertical_grid_lines=fch.ChartGridLines(color="#EEF3F4", width=1, dash_pattern=[3, 4]),
        border=ft.Border.all(1, "#CAD9DD"),
        bgcolor=ft.Colors.WHITE,
        tooltip=fch.LineChartTooltip(
            bgcolor="#E61B3037",
            border_radius=8,
            max_width=260,
            fit_inside_horizontally=True,
            fit_inside_vertically=True,
        ),
        expand=True,
    )
    controls: list[ft.Control] = [chart]
    if show_legend:
        controls.append(_legend(legend_items))
    return ft.Column(controls, spacing=8, expand=True)
