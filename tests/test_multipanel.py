from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from xps_app.exceptions import XPSDataError
from xps_app.models import Spectrum
from xps_app.multipanel import (
    MultiPanelConfig,
    build_multi_panel_figure,
    export_multi_panel_figure,
    generate_panel_labels,
    render_multi_panel_figure,
)


def test_panel_labels_support_styles_and_more_than_26_items() -> None:
    labels = generate_panel_labels(28, "(a)")

    assert labels[:3] == ["(a)", "(b)", "(c)"]
    assert labels[25:] == ["(z)", "(aa)", "(ab)"]
    assert generate_panel_labels(2, "(A)") == ["(A)", "(B)"]
    assert generate_panel_labels(2, "none") == ["", ""]


def test_multi_panel_figure_respects_selection_order_layout_and_labels(
    raw_frame: pd.DataFrame,
    fitted_frame: pd.DataFrame,
) -> None:
    spectra = [
        Spectrum.from_dataframe("Survey", raw_frame),
        Spectrum.from_dataframe("C 1s", fitted_frame),
    ]
    config = MultiPanelConfig(rows=2, cols=2, show_legend=False)

    figure = build_multi_panel_figure(spectra, config, labels=["(a)", "custom"])

    assert len(figure.axes) == 4
    assert figure.axes[0].get_title() == "Survey"
    assert figure.axes[1].get_title() == "C 1s"
    assert [text.get_text() for text in figure.axes[0].texts] == ["(a)"]
    assert [text.get_text() for text in figure.axes[1].texts] == ["custom"]
    assert figure.axes[0].xaxis_inverted()
    assert figure.axes[1].xaxis_inverted()
    assert figure.axes[2].axison is False
    assert figure.axes[3].axison is False
    plt.close(figure)


def test_multi_panel_validates_capacity_and_exports(
    tmp_path: Path,
    raw_frame: pd.DataFrame,
    fitted_frame: pd.DataFrame,
) -> None:
    spectra = [
        Spectrum.from_dataframe("Survey", raw_frame),
        Spectrum.from_dataframe("C 1s", fitted_frame),
    ]
    with pytest.raises(XPSDataError, match="无法容纳"):
        build_multi_panel_figure(spectra, MultiPanelConfig(rows=1, cols=1))

    config = MultiPanelConfig(rows=1, cols=2, dpi=100)
    preview = render_multi_panel_figure(spectra, config, preview=True)
    target = export_multi_panel_figure(
        spectra,
        config,
        tmp_path / "selected_panels.png",
        labels=["(a)", "(b)"],
    )

    assert preview.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(preview) > 10_000
    assert target.stat().st_size > 10_000
