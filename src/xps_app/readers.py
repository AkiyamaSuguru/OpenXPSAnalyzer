"""Readers for Excel files exported/processed by Thermo Avantage."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pandas as pd

from xps_app.constants import BE_COL, BG_COL, FIT_COL, INTENSITY_COL
from xps_app.exceptions import XPSDataError

ReaderKind = Literal["auto", "survey", "element"]
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
SURVEY_STEMS = {"survey", "xpssurvey", "wide", "widescan", "fullspectrum", "全谱"}


def _read_excel(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise XPSDataError(f"找不到 Excel 文件：{path}")
    if path.suffix.lower() not in EXCEL_SUFFIXES:
        raise XPSDataError("Avantage 数据必须是 .xlsx、.xlsm 或 .xls 文件。")

    try:
        frame = pd.read_excel(path, skiprows=15)
        descriptive_header = pd.read_excel(
            path,
            header=None,
            skiprows=14,
            nrows=1,
        )
    except Exception as exc:  # pandas exposes engine-specific exception types
        raise XPSDataError(f"无法读取 Excel 文件：{exc}") from exc

    # Avantage frequently adds completely empty spacer columns.  Do not drop a
    # useful signal merely because one individual measurement is missing.
    active_columns = ~frame.isna().all(axis=0)
    active_positions = [index for index, active in enumerate(active_columns) if active]
    frame = frame.loc[:, active_columns].copy()
    header_hints: list[str] = []
    for position in active_positions:
        if position >= descriptive_header.shape[1]:
            header_hints.append("")
            continue
        value = descriptive_header.iloc[0, position]
        header_hints.append("" if pd.isna(value) else str(value).strip())
    frame.attrs["avantage_header_hints"] = header_hints
    if frame.empty:
        raise XPSDataError("跳过前 15 行后没有找到 XPS 数据。")
    return frame


def _numeric_spectrum(frame: pd.DataFrame, required: Sequence[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=list(required)).reset_index(drop=True)
    if result.empty:
        raise XPSDataError("必要列中没有可用的数值数据。")
    return result


def survey_reader(file_path: str | Path) -> pd.DataFrame:
    """Read survey data from an Excel workbook processed by Avantage."""

    raw = _read_excel(file_path)
    if raw.shape[1] < 2:
        raise XPSDataError(f"Survey 数据至少需要 2 列，实际只有 {raw.shape[1]} 列。")
    survey = raw.iloc[:, :2].copy()
    survey.columns = [BE_COL, INTENSITY_COL]
    return _numeric_spectrum(survey, (BE_COL, INTENSITY_COL))


def element_reader(
    file_path: str | Path,
    peaks: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Read a fitted high-resolution element spectrum from Avantage Excel.

    ``peaks`` must follow the left-to-right component order in the workbook.
    When omitted, the peak labels already present in Excel are retained.
    """

    element = _read_excel(file_path)
    if element.shape[1] < 4:
        raise XPSDataError(
            "Element 数据至少需要结合能、强度、拟合曲线和背景 4 列；"
            f"实际只有 {element.shape[1]} 列。"
        )

    names = [str(name).strip() for name in element.columns]
    header_hints = list(element.attrs.get("avantage_header_hints", []))
    names[0] = BE_COL
    names[1] = INTENSITY_COL
    names[2] = FIT_COL
    names[-1] = BG_COL

    if peaks:
        clean_peaks = [str(peak).strip() for peak in peaks]
        expected = element.shape[1] - 4
        if len(clean_peaks) != expected:
            raise XPSDataError(
                f"输入峰值数量错误。期望 {expected} 个，实际传入 {len(clean_peaks)} 个。"
            )
        if any(not peak for peak in clean_peaks):
            raise XPSDataError("峰名称不能为空。")
        if len(set(clean_peaks)) != len(clean_peaks):
            raise XPSDataError("峰名称不能重复。")
        names[3:-1] = clean_peaks
    else:
        for index in range(3, len(names) - 1):
            if index >= len(header_hints):
                continue
            hint = _component_name_from_header(header_hints[index])
            if hint:
                names[index] = hint

    if len(set(names)) != len(names):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise XPSDataError(f"数据列名重复：{duplicates}")

    element = element.copy()
    element.columns = names
    return _numeric_spectrum(element, (BE_COL, INTENSITY_COL, FIT_COL, BG_COL))


def _component_name_from_header(value: str) -> str:
    """Convert Avantage's descriptive header into a useful component label."""

    cleaned = " ".join(str(value).replace("\n", " ").split()).strip()
    prefixes = ("拟合峰值", "Fitted Peak", "Peak")
    for prefix in prefixes:
        if cleaned.casefold().startswith(prefix.casefold()):
            cleaned = cleaned[len(prefix) :].strip(" :-")
            break
    return cleaned


def detect_avantage_kind(file_path: str | Path) -> Literal["survey", "element"]:
    """Identify an Avantage file using its regular filename and export headers."""

    path = Path(file_path)
    normalized_stem = "".join(
        character for character in path.stem.casefold() if character.isalnum()
    )
    if normalized_stem in SURVEY_STEMS or "survey" in normalized_stem:
        return "survey"

    raw = _read_excel(path)
    hints = [value.casefold() for value in raw.attrs.get("avantage_header_hints", [])]
    has_fit_envelope = any(
        any(token in hint for token in ("拟合包封", "fit envelope", "fitted envelope"))
        for hint in hints
    )
    has_background = any(
        any(token in hint for token in ("backgnd", "background", "背景")) for hint in hints
    )
    if has_fit_envelope and has_background and raw.shape[1] >= 4:
        return "element"
    if raw.shape[1] == 2:
        return "survey"
    if any(hints) and not has_fit_envelope:
        return "survey"
    # Compatibility fallback for exports that do not contain the descriptive row.
    return "element" if raw.shape[1] >= 4 else "survey"


def read_avantage(
    file_path: str | Path,
    kind: ReaderKind = "auto",
    peaks: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Unified application interface for Avantage Excel imports."""

    if kind not in {"auto", "survey", "element"}:
        raise XPSDataError(f"未知的数据类型：{kind}")
    if kind == "survey":
        return survey_reader(file_path)
    if kind == "element":
        return element_reader(file_path, peaks=peaks)

    detected = detect_avantage_kind(file_path)
    if detected == "survey":
        return survey_reader(file_path)
    if detected == "element":
        return element_reader(file_path, peaks=peaks)
    raise XPSDataError("无法自动识别数据类型；请选择 Survey 或 Element。")
