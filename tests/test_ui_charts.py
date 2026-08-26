from __future__ import annotations

from types import SimpleNamespace

import flet as ft
import pandas as pd

from xps_app.app import XPSAnalyzerApp
from xps_app.models import Spectrum
from xps_app.ui_charts import build_interactive_spectrum_chart


def test_interactive_chart_has_reversed_energy_and_hover_data(
    fitted_frame: pd.DataFrame,
) -> None:
    spectrum = Spectrum.from_dataframe("C 1s", fitted_frame)

    control = build_interactive_spectrum_chart(spectrum)
    chart = control.controls[0]

    assert chart.interactive is True
    assert chart.min_x == 0.0
    assert chart.max_x == 12.0
    assert len(chart.data_series) == 5
    assert len(chart.bottom_axis.labels) == 6
    assert chart.bottom_axis.labels[0].value == 0.0
    tooltip = chart.data_series[0].points[0].tooltip.text
    assert tooltip.startswith("Raw data:")
    assert "292.000 eV" in tooltip
    assert "·" in tooltip


def test_interactive_chart_can_hide_legend(fitted_frame: pd.DataFrame) -> None:
    spectrum = Spectrum.from_dataframe("C 1s", fitted_frame)

    control = build_interactive_spectrum_chart(spectrum, show_legend=False)

    assert len(control.controls) == 1


def test_web_selection_event_value_is_synchronized() -> None:
    dropdown = ft.Dropdown(value="head")
    segment = ft.SegmentedButton(
        segments=[ft.Segment(value="interactive"), ft.Segment(value="publication")],
        selected=["interactive"],
    )

    XPSAnalyzerApp._sync_event_value(SimpleNamespace(control=dropdown, data="all"))
    XPSAnalyzerApp._sync_event_value(SimpleNamespace(control=segment, data=["publication"]))

    assert dropdown.value == "all"
    assert segment.selected == ["publication"]
