from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from xps_app.analysis import analyze_spectrum
from xps_app.models import Spectrum
from xps_app.plotting import (
    Eplotter,
    build_spectrum_figure,
    export_interactive_html,
    export_static_figure,
    plot_xps,
    plot_xps_single,
    render_interactive_html,
    render_spectrum_image,
    render_spectrum_preview,
)


def test_fit_metrics_are_exact_for_exact_envelope(fitted_frame: pd.DataFrame) -> None:
    spectrum = Spectrum.from_dataframe("C 1s", fitted_frame)

    metrics = analyze_spectrum(spectrum)

    assert metrics.rmse == 0.0
    assert metrics.mae == 0.0
    assert metrics.r_squared == 1.0
    assert [metric.name for metric in metrics.components] == ["C–C", "C–O"]
    assert all(metric.area > 0 for metric in metrics.components)


def test_matplotlib_figures_reverse_binding_energy_axis(
    raw_frame: pd.DataFrame, fitted_frame: pd.DataFrame
) -> None:
    plotter = Eplotter({"Survey": raw_frame, "C 1s": fitted_frame})
    figure, axes = plotter.plots(n_cols=2, show=False)

    assert all(axis.xaxis_inverted() for axis in axes.flatten())
    plt.close(figure)

    single = build_spectrum_figure(Spectrum.from_dataframe("C 1s", fitted_frame))
    assert single.axes[0].xaxis_inverted()
    plt.close(single)


def test_static_and_html_export(
    tmp_path: Path, raw_frame: pd.DataFrame, fitted_frame: pd.DataFrame
) -> None:
    fitted = Spectrum.from_dataframe("C 1s", fitted_frame)
    image = export_static_figure(fitted, tmp_path / "c1s.png", dpi=120)
    html = export_interactive_html(fitted, tmp_path / "c1s.html")

    assert image.stat().st_size > 1_000
    assert html.stat().st_size > 10_000
    assert "plotly" in html.read_text(encoding="utf-8").lower()
    assert len(plot_xps(fitted_frame).data) >= 5
    assert len(plot_xps_single(raw_frame).data) == 1


def test_flet_preview_is_a_png(fitted_frame: pd.DataFrame) -> None:
    preview = render_spectrum_preview(Spectrum.from_dataframe("中文谱图 C 1s", fitted_frame))

    assert preview.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(preview) > 10_000


def test_in_memory_renderers(fitted_frame: pd.DataFrame) -> None:
    fitted = Spectrum.from_dataframe("C 1s", fitted_frame)

    image = render_spectrum_image(fitted, dpi=100)
    html = render_interactive_html(fitted)

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) > 10_000
    assert b"plotly" in html.lower()
    assert b"Raw data" in html
