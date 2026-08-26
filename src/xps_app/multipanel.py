"""Configurable publication-style multi-panel XPS figures."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt

from xps_app.exceptions import XPSDataError
from xps_app.models import Spectrum
from xps_app.plotting import Eplotter

SUPPORTED_EXPORT_FORMATS = {"png", "svg", "pdf", "jpg", "jpeg", "tif", "tiff"}


@dataclass(frozen=True, slots=True)
class MultiPanelConfig:
    """Layout and style settings for one multi-panel figure."""

    rows: int
    cols: int
    palette: str = "sci_default"
    component_mode: str = "absolute"
    show_titles: bool = True
    show_legend: bool = True
    hide_y_ticks: bool = True
    cell_width: float = 3.4
    cell_height: float = 2.7
    label_position: str = "upper_left"
    dpi: int = 300

    def validate(self, spectrum_count: int) -> None:
        if spectrum_count < 1:
            raise XPSDataError("请至少选择一条谱图。")
        if self.rows < 1 or self.cols < 1:
            raise XPSDataError("行数和列数必须是正整数。")
        if self.rows * self.cols < spectrum_count:
            raise XPSDataError(
                f"当前 {self.rows} × {self.cols} 布局只有 {self.rows * self.cols} 个位置，"
                f"无法容纳 {spectrum_count} 条谱图。"
            )
        if self.component_mode not in {"absolute", "relative"}:
            raise XPSDataError("分峰数据模式必须是 absolute 或 relative。")
        if not 2.0 <= self.cell_width <= 10.0:
            raise XPSDataError("单个子图宽度必须在 2–10 英寸之间。")
        if not 1.8 <= self.cell_height <= 10.0:
            raise XPSDataError("单个子图高度必须在 1.8–10 英寸之间。")
        if self.label_position not in {
            "upper_left",
            "upper_right",
            "lower_left",
            "lower_right",
        }:
            raise XPSDataError("未知的子图标签位置。")
        if not 72 <= self.dpi <= 1200:
            raise XPSDataError("导出 DPI 必须在 72–1200 之间。")


def _alphabetic_code(index: int, uppercase: bool = False) -> str:
    """Return a, b, ..., z, aa, ab ... for a zero-based index."""

    if index < 0:
        raise ValueError("index must be non-negative.")
    letters: list[str] = []
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("a") + remainder))
    result = "".join(reversed(letters))
    return result.upper() if uppercase else result


def generate_panel_labels(count: int, style: str = "(a)") -> list[str]:
    """Generate sequential panel labels which remain editable in the UI."""

    if count < 0:
        raise ValueError("count must be non-negative.")
    if style == "none":
        return [""] * count
    if style not in {"(a)", "a)", "(A)", "A"}:
        raise XPSDataError(f"未知的标签格式：{style}")
    uppercase = "A" in style
    labels = []
    for index in range(count):
        code = _alphabetic_code(index, uppercase=uppercase)
        if style in {"(a)", "(A)"}:
            labels.append(f"({code})")
        elif style == "a)":
            labels.append(f"{code})")
        else:
            labels.append(code)
    return labels


def build_multi_panel_figure(
    spectra: Sequence[Spectrum],
    config: MultiPanelConfig,
    labels: Sequence[str] | None = None,
) -> plt.Figure:
    """Build one ordered multi-panel figure from selected workspace spectra."""

    selected = list(spectra)
    config.validate(len(selected))
    resolved_labels = list(labels) if labels is not None else generate_panel_labels(len(selected))
    if len(resolved_labels) != len(selected):
        raise XPSDataError(
            f"子图标签数量错误。期望 {len(selected)} 个，实际 {len(resolved_labels)} 个。"
        )

    frames = {spectrum.name: spectrum.to_dataframe() for spectrum in selected}
    plotter = Eplotter(frames, font_size=9)
    figure, axes = plt.subplots(
        config.rows,
        config.cols,
        figsize=(config.cell_width * config.cols, config.cell_height * config.rows),
        squeeze=False,
    )
    flat = axes.flatten()
    positions = {
        "upper_left": (0.025, 0.965, "left", "top"),
        "upper_right": (0.975, 0.965, "right", "top"),
        "lower_left": (0.025, 0.035, "left", "bottom"),
        "lower_right": (0.975, 0.035, "right", "bottom"),
    }
    x, y, horizontal, vertical = positions[config.label_position]

    for index, (axis, spectrum) in enumerate(zip(flat, selected, strict=False)):
        plotter.plot(
            spectrum.to_dataframe(),
            axis,
            palette=config.palette,
            component_mode=config.component_mode,
            show_legend=config.show_legend,
            hide_y_ticks=config.hide_y_ticks,
        )
        axis.set_title(spectrum.name if config.show_titles else "", pad=8, fontweight=600)
        label = resolved_labels[index].strip()
        if label:
            axis.text(
                x,
                y,
                label,
                transform=axis.transAxes,
                ha=horizontal,
                va=vertical,
                fontsize=plotter.font_size * 1.15,
                fontweight=600,
                zorder=10,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1.5},
            )

    for axis in flat[len(selected) :]:
        axis.axis("off")
    figure.tight_layout()
    return figure


def render_multi_panel_figure(
    spectra: Sequence[Spectrum],
    config: MultiPanelConfig,
    labels: Sequence[str] | None = None,
    file_format: str = "png",
    preview: bool = False,
) -> bytes:
    """Render a multi-panel figure to bytes for previews and web downloads."""

    normalized = file_format.lower().lstrip(".")
    if normalized not in SUPPORTED_EXPORT_FORMATS:
        raise XPSDataError(f"不支持的多子图导出格式：{file_format}")
    figure = build_multi_panel_figure(spectra, config, labels=labels)
    buffer = BytesIO()
    try:
        figure.savefig(
            buffer,
            format=normalized,
            dpi=min(config.dpi, 140) if preview else config.dpi,
            bbox_inches="tight",
            facecolor="white",
        )
    finally:
        plt.close(figure)
    return buffer.getvalue()


def export_multi_panel_figure(
    spectra: Sequence[Spectrum],
    config: MultiPanelConfig,
    file_path: str | Path,
    labels: Sequence[str] | None = None,
) -> Path:
    """Export one configured multi-panel figure to a desktop path."""

    path = Path(file_path).expanduser()
    suffix = path.suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_EXPORT_FORMATS:
        path = path.with_suffix(".png")
        suffix = "png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        render_multi_panel_figure(
            spectra,
            config,
            labels=labels,
            file_format=suffix,
        )
    )
    return path
