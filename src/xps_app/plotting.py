"""Publication, preview, and interactive plotting interfaces for XPS data."""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from matplotlib import MatplotlibDeprecationWarning
from plotly.colors import hex_to_rgb, qualitative

from xps_app.constants import (
    BE_COL,
    BG_COL,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    FIT_COL,
    INTENSITY_COL,
)
from xps_app.exceptions import XPSDataError
from xps_app.models import Spectrum

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MatplotlibDeprecationWarning)
        import scienceplots  # noqa: F401
except ImportError:  # pragma: no cover - optional style registration
    scienceplots = None


class Eplotter:
    """Matplotlib plotter compatible with the supplied analysis module."""

    BE_COL = BE_COL
    INTENSITY_COL = INTENSITY_COL
    FIT_COL = FIT_COL
    BG_COL = BG_COL
    RAW_REQUIRED_COLUMNS = [BE_COL, INTENSITY_COL]
    FIT_REQUIRED_COLUMNS = [BE_COL, INTENSITY_COL, FIT_COL, BG_COL]

    def __init__(
        self,
        dfs: Mapping[str, pd.DataFrame],
        font_family: str = DEFAULT_FONT_FAMILY,
        font_size: float = DEFAULT_FONT_SIZE,
        special_text_scale: float = 1.2,
        use_latex: bool = False,
    ) -> None:
        if not isinstance(dfs, Mapping):
            raise TypeError("dfs must be a mapping such as dict[str, pd.DataFrame].")
        if not dfs:
            raise ValueError("dfs cannot be empty.")
        invalid = {
            key: type(value).__name__
            for key, value in dfs.items()
            if not isinstance(value, pd.DataFrame)
        }
        if invalid:
            raise TypeError(f"All values in dfs must be pandas.DataFrame objects: {invalid}")
        self.dfs = dict(dfs)
        self.keys = list(self.dfs)
        try:
            plt.style.use("science" if use_latex else ["science", "no-latex"])
        except OSError:
            plt.style.use("default")
        self.font_family = font_family
        self.font_size = font_size
        self.special_text_scale = special_text_scale
        plt.rcParams.update(
            {
                "font.family": font_family,
                "font.sans-serif": [
                    "PingFang SC",
                    "Hiragino Sans GB",
                    "Microsoft YaHei",
                    "Noto Sans CJK SC",
                    "Arial Unicode MS",
                    "DejaVu Sans",
                ],
                "font.size": font_size,
                "axes.unicode_minus": False,
            }
        )
        self.color_palettes = {
            "sci_default": ["#0173B2", "#DE8F05", "#029E73", "#D55E00", "#CC78BC", "#CA9161"],
            "tableau": [
                "#1f77b4",
                "#ff7f0e",
                "#2ca02c",
                "#d62728",
                "#9467bd",
                "#8c564b",
                "#e377c2",
                "#7f7f7f",
                "#bcbd22",
                "#17becf",
            ],
            "nature": [
                "#E64B35",
                "#4DBBD5",
                "#00A087",
                "#3C5488",
                "#F39B7F",
                "#8491B4",
                "#91D1C2",
                "#DC0000",
                "#7E6148",
                "#B09C85",
            ],
            "okabe_ito": [
                "#0072B2",
                "#E69F00",
                "#009E73",
                "#D55E00",
                "#CC79A7",
                "#56B4E9",
                "#F0E442",
            ],
            "soft": [
                "#4C72B0",
                "#DD8452",
                "#55A868",
                "#C44E52",
                "#8172B3",
                "#937860",
                "#DA8BC3",
                "#8C8C8C",
                "#CCB974",
                "#64B5CD",
            ],
        }

    @staticmethod
    def _require_columns(frame: pd.DataFrame, required: Sequence[str]) -> None:
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise XPSDataError(f"缺少必要列：{missing}；当前列为：{list(frame.columns)}")

    def _validate_raw_df(self, frame: pd.DataFrame) -> None:
        self._require_columns(frame, self.RAW_REQUIRED_COLUMNS)

    def _validate_fit_df(self, frame: pd.DataFrame) -> None:
        self._require_columns(frame, self.FIT_REQUIRED_COLUMNS)

    def _validate_df(self, frame: pd.DataFrame) -> None:
        self._validate_fit_df(frame)

    def _detect_plot_type(self, frame: pd.DataFrame) -> str:
        self._validate_raw_df(frame)
        has_fit = FIT_COL in frame.columns
        has_bg = BG_COL in frame.columns
        if has_fit and has_bg:
            return "fit"
        if not has_fit and not has_bg:
            return "raw"
        missing = [column for column in (FIT_COL, BG_COL) if column not in frame.columns]
        raise XPSDataError(f"拟合谱数据不完整，缺少列：{missing}")

    def info(self) -> list[dict[str, Any]]:
        """Return structured information instead of printing UI-unfriendly text."""

        return [
            {
                "key": key,
                "type": self._detect_plot_type(frame),
                "shape": frame.shape,
                "columns": list(frame.columns),
            }
            for key, frame in self.dfs.items()
        ]

    def get_colors(
        self,
        component_cols: Sequence[str],
        palette: str | Sequence[Any] | Mapping[str, Any] = "sci_default",
        strict: bool = True,
    ) -> list[Any]:
        count = len(component_cols)
        if count == 0:
            return []
        if isinstance(palette, str):
            if palette in self.color_palettes:
                colors = self.color_palettes[palette]
                return [colors[index % len(colors)] for index in range(count)]
            try:
                colormap = plt.get_cmap(palette)
            except ValueError as exc:
                raise XPSDataError(
                    f"未知色卡：{palette}。可用内置色卡：{list(self.color_palettes)}"
                ) from exc
            return (
                [colormap(0.5)] if count == 1 else [colormap(i / (count - 1)) for i in range(count)]
            )
        if isinstance(palette, Mapping):
            missing = [name for name in component_cols if name not in palette]
            if missing and strict:
                raise XPSDataError(f"以下分峰缺少颜色：{missing}")
            fallback = self.color_palettes["sci_default"]
            return [
                palette.get(name, fallback[index % len(fallback)])
                for index, name in enumerate(component_cols)
            ]
        if isinstance(palette, (list, tuple, np.ndarray)):
            colors = list(palette)
            if not colors:
                raise XPSDataError("颜色列表不能为空。")
            return [colors[index % len(colors)] for index in range(count)]
        raise TypeError("palette must be str, list, tuple, np.ndarray, or dict.")

    def _format_axis(self, axis: plt.Axes, hide_y_ticks: bool = False) -> None:
        if not axis.xaxis_inverted():
            axis.invert_xaxis()
        axis.xaxis.set_ticks_position("bottom")
        axis.set_xlabel(BE_COL)
        axis.set_ylabel("Intensity (a.u.)")
        if hide_y_ticks:
            axis.set_yticks([])
        axis.tick_params(axis="both", direction="in", length=3, width=0.8)

    def raw_plot(
        self,
        df_r: pd.DataFrame,
        ax: plt.Axes,
        color: str = "#00BFFF",
        linewidth: float = 1.0,
        show_legend: bool = False,
        legend_loc: str = "best",
        label: str = "Raw data",
        hide_y_ticks: bool = False,
    ) -> plt.Axes:
        self._validate_raw_df(df_r)
        frame = df_r.sort_values(BE_COL)
        ax.plot(
            frame[BE_COL],
            frame[INTENSITY_COL],
            color=color,
            linewidth=linewidth,
            label=label,
            zorder=2,
        )
        self._format_axis(ax, hide_y_ticks)
        if show_legend:
            ax.legend(fontsize=self.font_size * 0.75, frameon=False, loc=legend_loc)
        return ax

    def fit_plot(
        self,
        df_r: pd.DataFrame,
        ax: plt.Axes,
        palette: str | Sequence[Any] | Mapping[str, Any] = "sci_default",
        component_mode: str = "absolute",
        show_legend: bool = True,
        raw_color: str = "black",
        fit_color: str = "red",
        bg_color: str = "gray",
        raw_size: float = 4,
        component_alpha: float = 0.35,
        legend_loc: str = "best",
        hide_y_ticks: bool = False,
    ) -> plt.Axes:
        if component_mode not in {"absolute", "relative"}:
            raise XPSDataError("component_mode 必须是 absolute 或 relative。")
        self._validate_fit_df(df_r)
        frame = df_r.sort_values(BE_COL)
        be = frame[BE_COL].to_numpy(dtype=float)
        background = frame[BG_COL].to_numpy(dtype=float)
        components = [column for column in frame.columns if column not in self.FIT_REQUIRED_COLUMNS]
        colors = self.get_colors(components, palette)
        ax.scatter(
            be,
            frame[INTENSITY_COL],
            s=raw_size,
            color=raw_color,
            alpha=0.65,
            label="Raw data",
            zorder=2,
        )
        ax.plot(be, frame[FIT_COL], color=fit_color, linewidth=1.2, label="Fit", zorder=4)
        ax.plot(
            be,
            background,
            color=bg_color,
            linestyle="--",
            linewidth=1.0,
            label="Background",
            zorder=3,
        )
        for index, component in enumerate(components):
            stored = frame[component].to_numpy(dtype=float)
            values = stored if component_mode == "absolute" else background + stored
            ax.fill_between(
                be,
                background,
                values,
                color=colors[index],
                alpha=component_alpha,
                label=component,
                zorder=1,
            )
            ax.plot(be, values, color=colors[index], linewidth=0.8, zorder=3)
        self._format_axis(ax, hide_y_ticks)
        if show_legend:
            ax.legend(fontsize=self.font_size * 0.75, frameon=False, loc=legend_loc)
        return ax

    def plot(
        self,
        df_r: pd.DataFrame,
        ax: plt.Axes,
        palette: str | Sequence[Any] | Mapping[str, Any] = "sci_default",
        component_mode: str = "absolute",
        show_legend: bool = True,
        legend_loc: str = "best",
        raw_color: str = "black",
        raw_line_color: str = "#00BFFF",
        raw_size: float = 4,
        fit_color: str = "red",
        bg_color: str = "gray",
        component_alpha: float = 0.35,
        hide_y_ticks: bool = False,
    ) -> plt.Axes:
        if self._detect_plot_type(df_r) == "raw":
            return self.raw_plot(
                df_r,
                ax,
                color=raw_line_color,
                show_legend=show_legend,
                legend_loc=legend_loc,
                hide_y_ticks=hide_y_ticks,
            )
        return self.fit_plot(
            df_r,
            ax,
            palette=palette,
            component_mode=component_mode,
            show_legend=show_legend,
            raw_color=raw_color,
            fit_color=fit_color,
            bg_color=bg_color,
            raw_size=raw_size,
            component_alpha=component_alpha,
            legend_loc=legend_loc,
            hide_y_ticks=hide_y_ticks,
        )

    def plots(
        self,
        save_fig: str | Path | None = None,
        palette: Any = "sci_default",
        n_cols: int = 3,
        figsize: tuple[float, float] | None = None,
        component_mode: str = "absolute",
        show_legend: bool = True,
        legend_loc: str = "best",
        dpi: int = 600,
        raw_color: str = "black",
        raw_line_color: str | Mapping[str, str] = "#00BFFF",
        fit_color: str = "red",
        bg_color: str = "gray",
        raw_size: float = 4,
        component_alpha: float = 0.35,
        hide_y_ticks: bool = False,
        show: bool = True,
    ) -> tuple[plt.Figure, np.ndarray]:
        if not isinstance(n_cols, int) or n_cols < 1:
            raise XPSDataError("n_cols 必须是正整数。")
        rows = math.ceil(len(self.dfs) / n_cols)
        figsize = figsize or (3.2 * n_cols, 2.4 * rows)
        figure, axes = plt.subplots(rows, n_cols, figsize=figsize, squeeze=False)
        flat = axes.flatten()
        for axis, (key, frame) in zip(flat, self.dfs.items(), strict=False):
            current_palette = (
                palette[key] if isinstance(palette, Mapping) and key in palette else palette
            )
            line_color = (
                raw_line_color.get(key, "#00BFFF")
                if isinstance(raw_line_color, Mapping)
                else raw_line_color
            )
            self.plot(
                frame,
                axis,
                palette=current_palette,
                component_mode=component_mode,
                show_legend=show_legend,
                legend_loc=legend_loc,
                raw_color=raw_color,
                raw_line_color=line_color,
                raw_size=raw_size,
                fit_color=fit_color,
                bg_color=bg_color,
                component_alpha=component_alpha,
                hide_y_ticks=hide_y_ticks,
            )
            axis.text(
                0.03,
                0.96,
                str(key),
                transform=axis.transAxes,
                ha="left",
                va="top",
                fontsize=self.font_size * self.special_text_scale,
                fontweight=600,
            )
        for axis in flat[len(self.dfs) :]:
            axis.axis("off")
        figure.tight_layout()
        if save_fig:
            figure.savefig(save_fig, dpi=dpi, bbox_inches="tight")
        if show:
            plt.show()
        return figure, axes


def plot_xps(
    df_r: pd.DataFrame,
    font_family: str = DEFAULT_FONT_FAMILY,
    font_size: float = DEFAULT_FONT_SIZE,
    component_mode: str = "absolute",
) -> go.Figure:
    """Build a Plotly figure for a fitted spectrum."""

    plotter = Eplotter({"preview": df_r}, font_family, font_size)
    plotter._validate_fit_df(df_r)
    if component_mode not in {"absolute", "relative"}:
        raise XPSDataError("component_mode 必须是 absolute 或 relative。")
    frame = df_r.copy()
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=plotter.FIT_REQUIRED_COLUMNS).sort_values(BE_COL)
    if frame.empty:
        raise XPSDataError("没有可用于绘图的有效数据。")
    be = frame[BE_COL].to_numpy(dtype=float)
    background = frame[BG_COL].to_numpy(dtype=float)
    components = [column for column in frame.columns if column not in plotter.FIT_REQUIRED_COLUMNS]
    figure = go.Figure()
    for index, component in enumerate(components):
        color = qualitative.Plotly[index % len(qualitative.Plotly)]
        stored = frame[component].to_numpy(dtype=float)
        values = stored if component_mode == "absolute" else background + stored
        peak_signal = stored - background if component_mode == "absolute" else stored
        mask = (
            np.isfinite(be)
            & np.isfinite(background)
            & np.isfinite(values)
            & np.isfinite(peak_signal)
        )
        x = be[mask]
        y = values[mask]
        bg = background[mask]
        signal = peak_signal[mask]
        if not mask.any():
            continue
        red, green, blue = hex_to_rgb(color)
        figure.add_trace(
            go.Scatter(
                x=np.concatenate([x, x[::-1]]),
                y=np.concatenate([y, bg[::-1]]),
                mode="lines",
                line={"width": 0},
                fill="toself",
                fillcolor=f"rgba({red},{green},{blue},0.28)",
                hoverinfo="skip",
                showlegend=False,
                legendgroup=component,
            )
        )
        figure.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=component,
                legendgroup=component,
                line={"color": color, "width": 1.4},
                hovertemplate=f"<b>{component}</b><br>Binding Energy: %{{x:.3f}} eV<br>Intensity: %{{y:.3f}}<extra></extra>",
            )
        )
        peak_index = int(np.nanargmax(signal))
        figure.add_trace(
            go.Scatter(
                x=[x[peak_index]],
                y=[y[peak_index]],
                mode="markers",
                name=f"{component} peak",
                legendgroup=component,
                showlegend=False,
                marker={"color": color, "size": 7, "symbol": "diamond"},
                hovertemplate=(
                    f"<b>{component} peak</b><br>Peak position: %{{x:.3f}} eV<br>"
                    "Peak intensity: %{y:.3f}<extra></extra>"
                ),
            )
        )
    figure.add_trace(
        go.Scatter(
            x=be,
            y=frame[INTENSITY_COL],
            mode="markers",
            name="Raw data",
            marker={"size": 4, "color": "black", "opacity": 0.65},
            hovertemplate=(
                "<b>Raw data</b><br>Binding Energy: %{x:.3f} eV<br>"
                "Intensity: %{y:.3f}<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=be,
            y=frame[FIT_COL],
            mode="lines",
            name="Fit",
            line={"color": "red", "width": 1.8},
            hovertemplate=(
                "<b>Fit</b><br>Binding Energy: %{x:.3f} eV<br>Intensity: %{y:.3f}<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=be,
            y=background,
            mode="lines",
            name="Background",
            line={"color": "gray", "width": 1.3, "dash": "dash"},
            hovertemplate=(
                "<b>Background</b><br>Binding Energy: %{x:.3f} eV<br>"
                "Intensity: %{y:.3f}<extra></extra>"
            ),
        )
    )
    _format_plotly(figure, font_family, font_size, show_legend=True)
    return figure


def plot_xps_single(
    df: pd.DataFrame,
    font_family: str = DEFAULT_FONT_FAMILY,
    font_size: float = DEFAULT_FONT_SIZE,
) -> go.Figure:
    """Build a Plotly figure for a raw/survey spectrum."""

    Eplotter._require_columns(df, [BE_COL, INTENSITY_COL])
    figure = px.line(df, x=BE_COL, y=INTENSITY_COL, labels={INTENSITY_COL: "Intensity (a.u.)"})
    _format_plotly(figure, font_family, font_size, show_legend=False)
    return figure


def _format_plotly(
    figure: go.Figure,
    font_family: str,
    font_size: float,
    show_legend: bool,
) -> None:
    figure.update_layout(
        template="plotly_white",
        hovermode="closest",
        autosize=True,
        xaxis_title=BE_COL,
        yaxis_title="Intensity (a.u.)",
        font={"family": font_family, "size": font_size},
        showlegend=show_legend,
        legend={"x": 0.01, "y": 0.99, "groupclick": "togglegroup"},
        margin={"l": 70, "r": 55, "t": 60, "b": 65},
    )
    figure.update_xaxes(autorange="reversed", showline=True, mirror=True, ticks="inside")
    figure.update_yaxes(showticklabels=False, showline=True, mirror=True, ticks="inside")


def build_spectrum_figure(
    spectrum: Spectrum,
    palette: Any = "sci_default",
    component_mode: str = "absolute",
    show_legend: bool = True,
    hide_y_ticks: bool = True,
) -> plt.Figure:
    """Create the Matplotlib figure shown inside Flet."""

    frame = spectrum.to_dataframe()
    plotter = Eplotter({spectrum.name: frame}, font_size=9)
    figure, axis = plt.subplots(figsize=(8.2, 5.0), dpi=110)
    plotter.plot(
        frame,
        axis,
        palette=palette,
        component_mode=component_mode,
        show_legend=show_legend,
        hide_y_ticks=hide_y_ticks,
    )
    axis.set_title(spectrum.name, loc="left", fontweight=600, pad=12)
    figure.tight_layout()
    return figure


def render_spectrum_preview(
    spectrum: Spectrum,
    palette: Any = "sci_default",
    component_mode: str = "absolute",
    show_legend: bool = True,
    dpi: int = 140,
) -> bytes:
    """Render a responsive, backend-independent PNG preview for Flet."""

    figure = build_spectrum_figure(
        spectrum,
        palette=palette,
        component_mode=component_mode,
        show_legend=show_legend,
    )
    buffer = BytesIO()
    try:
        figure.savefig(
            buffer,
            format="png",
            dpi=dpi,
            bbox_inches="tight",
            facecolor="white",
        )
    finally:
        plt.close(figure)
    return buffer.getvalue()


def render_spectrum_image(
    spectrum: Spectrum,
    palette: Any = "sci_default",
    component_mode: str = "absolute",
    dpi: int = 300,
) -> bytes:
    """Render a full-axis PNG suitable for downloads."""

    figure = build_spectrum_figure(
        spectrum,
        palette=palette,
        component_mode=component_mode,
        hide_y_ticks=False,
    )
    buffer = BytesIO()
    try:
        figure.savefig(
            buffer,
            format="png",
            dpi=dpi,
            bbox_inches="tight",
            facecolor="white",
        )
    finally:
        plt.close(figure)
    return buffer.getvalue()


def render_interactive_html(
    spectrum: Spectrum,
    component_mode: str = "absolute",
) -> bytes:
    """Render a self-contained Plotly document without requiring a filesystem path."""

    frame = spectrum.to_dataframe()
    figure = (
        plot_xps(frame, component_mode=component_mode)
        if spectrum.spectrum_type.value == "fit"
        else plot_xps_single(frame)
    )
    return figure.to_html(include_plotlyjs=True, full_html=True).encode("utf-8")


def export_static_figure(
    spectrum: Spectrum,
    file_path: str | Path,
    palette: Any = "sci_default",
    component_mode: str = "absolute",
    dpi: int = 600,
) -> Path:
    """Export the selected spectrum as PNG, SVG, PDF, JPG, or TIFF."""

    path = Path(file_path).expanduser()
    supported = {".png", ".svg", ".pdf", ".jpg", ".jpeg", ".tif", ".tiff"}
    if path.suffix.lower() not in supported:
        path = path.with_suffix(".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure = build_spectrum_figure(spectrum, palette, component_mode, hide_y_ticks=False)
    try:
        figure.savefig(path, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(figure)
    return path


def export_interactive_html(
    spectrum: Spectrum,
    file_path: str | Path,
    component_mode: str = "absolute",
) -> Path:
    """Export a self-contained, fully interactive Plotly HTML viewer."""

    path = Path(file_path).expanduser().with_suffix(".html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_interactive_html(spectrum, component_mode=component_mode))
    return path
