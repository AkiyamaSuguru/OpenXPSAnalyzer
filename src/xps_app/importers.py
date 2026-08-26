"""Higher-level import workflows built on the Avantage readers."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from xps_app.exceptions import XPSDataError
from xps_app.models import Spectrum, XPSProject
from xps_app.readers import EXCEL_SUFFIXES, read_avantage


def list_avantage_files(folder_path: str | Path) -> list[Path]:
    """Return supported Excel files in deterministic filename order."""

    folder = Path(folder_path).expanduser()
    if not folder.is_dir():
        raise XPSDataError(f"找不到 XPS 数据文件夹：{folder}")
    files = sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in EXCEL_SUFFIXES
        ),
        key=lambda path: path.name.casefold(),
    )
    if not files:
        raise XPSDataError(f"文件夹中没有 .xls、.xlsx 或 .xlsm 文件：{folder}")
    return files


def read_avantage_folder(
    folder_path: str | Path,
    peaks_by_region: Mapping[str, Sequence[str]] | None = None,
) -> OrderedDict[str, pd.DataFrame]:
    """Read a regular Avantage folder, naming each result with ``Path.stem``."""

    result: OrderedDict[str, pd.DataFrame] = OrderedDict()
    for path in list_avantage_files(folder_path):
        peaks = peaks_by_region.get(path.stem) if peaks_by_region else None
        try:
            result[path.stem] = read_avantage(path, kind="auto", peaks=peaks)
        except Exception as exc:
            raise XPSDataError(f"读取 {path.name} 失败：{exc}") from exc
    return result


def project_from_avantage_folder(
    folder_path: str | Path,
    peaks_by_region: Mapping[str, Sequence[str]] | None = None,
) -> XPSProject:
    """Build an xarray-backed project whose names follow folder/file stems."""

    folder = Path(folder_path).expanduser()
    files = list_avantage_files(folder)
    sources = {path.stem: path for path in files}
    frames = read_avantage_folder(folder, peaks_by_region=peaks_by_region)
    project = XPSProject(name=folder.name)
    for region, frame in frames.items():
        project.add(
            Spectrum.from_dataframe(
                name=region,
                frame=frame,
                source_path=sources[region],
                sample=folder.name,
                region=region,
            )
        )
    return project
