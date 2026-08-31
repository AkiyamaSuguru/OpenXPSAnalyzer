"""Flet desktop user interface for OpenXPSAnalyzer."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import flet as ft
import numpy as np

from xps_app.analysis import SpectrumMetrics, analyze_spectrum
from xps_app.exceptions import XPSError
from xps_app.importers import project_from_avantage_folder
from xps_app.models import Spectrum, SpectrumType, XPSProject
from xps_app.multipanel import (
    MultiPanelConfig,
    export_multi_panel_figure,
    generate_panel_labels,
    render_multi_panel_figure,
)
from xps_app.plotting import (
    export_interactive_html,
    export_static_figure,
    render_interactive_html,
    render_spectrum_image,
    render_spectrum_preview,
)
from xps_app.readers import read_avantage
from xps_app.storage import load_project, save_project
from xps_app.ui_charts import build_interactive_spectrum_chart

ACCENT = "#146C7E"
ACCENT_DARK = "#0D4F5E"
ACCENT_LIGHT = "#DDF3F5"
SURFACE = "#F3F7F8"
SURFACE_TINT = "#EDF5F6"
BORDER = "#D5E1E4"
TEXT_PRIMARY = "#1E3238"
TEXT_MUTED = "#60747A"
ERROR = "#A43F46"
APP_VERSION = "0.4.0"
PROJECT_URL = "https://github.com/AkiyamaSuguru/OpenXPSAnalyzer"
PREVIEW_PAGE_SIZE = 50


class OpenXPSAnalyzerApp:
    """Stateful application shell; numerical work remains in service modules."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.project = XPSProject()
        self.selected_id: str | None = None
        self.pending_excel: Path | None = None
        self.pending_excel_data: bytes | None = None
        self.pending_excel_name = ""
        self.preview_page = 0
        self.project_title = ft.TextField(
            value=self.project.name,
            dense=True,
            border=ft.InputBorder.UNDERLINE,
            text_size=15,
            on_blur=self._rename_project,
        )
        self.spectrum_count = ft.Text("0", size=12, color=TEXT_MUTED)
        self.spectrum_list = ft.ListView(expand=True, spacing=4, padding=ft.Padding.only(right=4))
        self.selection_title = ft.Text(
            "未选择谱图",
            size=21,
            weight=ft.FontWeight.W_600,
            color=TEXT_PRIMARY,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.selection_subtitle = ft.Text(
            "导入 Avantage Excel 数据开始分析",
            color=TEXT_MUTED,
            size=12,
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.chart_host = ft.Container(
            content=self._empty_chart_state(),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, BORDER),
            border_radius=12,
            height=580,
            padding=14,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(blur_radius=18, color="#100D4F5E", offset=ft.Offset(0, 4)),
        )
        self.metrics_host = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self.preview_host = ft.Container(content=self._empty_preview_state(), height=350)
        self.palette = ft.Dropdown(
            value="sci_default",
            label="分峰色卡",
            dense=True,
            width=150,
            options=[
                ft.DropdownOption(key=value, text=label)
                for value, label in (
                    ("sci_default", "Science"),
                    ("nature", "Nature"),
                    ("okabe_ito", "Okabe–Ito"),
                    ("tableau", "Tableau"),
                    ("soft", "Soft"),
                    ("viridis", "Viridis"),
                )
            ],
            on_select=self._plot_setting_changed,
        )
        self.component_mode = ft.Dropdown(
            value="absolute",
            label="分峰数据模式",
            dense=True,
            width=168,
            options=[
                ft.DropdownOption(key="absolute", text="已包含背景"),
                ft.DropdownOption(key="relative", text="扣背景强度"),
            ],
            on_select=self._plot_setting_changed,
        )
        self.show_legend = ft.Switch(value=True, label="图例", on_change=self._plot_setting_changed)
        self.chart_view_mode = ft.SegmentedButton(
            segments=[
                ft.Segment(
                    value="interactive",
                    label="交互图",
                    tooltip="悬浮交互图",
                ),
                ft.Segment(
                    value="publication",
                    label="静态图",
                    tooltip="出版级静态预览",
                ),
            ],
            selected=["interactive"],
            show_selected_icon=False,
            width=146,
            on_change=self._plot_setting_changed,
        )
        self.preview_mode = ft.Dropdown(
            value="head",
            label="预览范围",
            dense=True,
            width=172,
            options=[
                ft.DropdownOption(key="head", text="前 30 行"),
                ft.DropdownOption(key="tail", text="后 30 行"),
                ft.DropdownOption(key="all", text="所有数据（分页）"),
            ],
            on_select=self._preview_mode_changed,
        )
        self.preview_status = ft.Text("", size=11, color=TEXT_MUTED)
        self.preview_previous = ft.IconButton(
            ft.Icons.CHEVRON_LEFT,
            tooltip="上一页",
            disabled=True,
            on_click=self._preview_previous_page,
        )
        self.preview_next = ft.IconButton(
            ft.Icons.CHEVRON_RIGHT,
            tooltip="下一页",
            disabled=True,
            on_click=self._preview_next_page,
        )
        self.import_kind = ft.Dropdown(
            value="auto",
            label="数据类型",
            options=[
                ft.DropdownOption(key="auto", text="自动识别"),
                ft.DropdownOption(key="survey", text="Survey"),
                ft.DropdownOption(key="element", text="Element / 高分辨谱"),
            ],
        )
        self.import_name = ft.TextField(label="谱图名称", autofocus=True)
        self.import_peaks = ft.TextField(
            label="分峰名称（可选）",
            hint_text="按 Excel 从左到右输入，例如 C–Si, C–O",
            helper="留空时使用 Excel 原始列名；仅 Element 数据使用。",
        )
        self.import_dialog = self._build_import_dialog()
        self.peak_names_field = ft.TextField(
            label="分峰名称",
            hint_text="按数据列顺序用英文逗号分隔",
            multiline=True,
            min_lines=2,
            max_lines=4,
        )
        self.peak_names_dialog = self._build_peak_names_dialog()
        self.about_dialog = self._build_about_dialog()
        self.multi_panel_order: list[str] = []
        self.multi_panel_selected: set[str] = set()
        self.multi_panel_labels: dict[str, str] = {}
        self.multi_panel_list = ft.ListView(expand=True, spacing=4, padding=4)
        self.multi_panel_status = ft.Text("", size=11, color=TEXT_MUTED)
        self.multi_panel_rows = ft.TextField(
            value="1",
            label="行数",
            dense=True,
            width=82,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._multi_setting_changed,
        )
        self.multi_panel_cols = ft.TextField(
            value="1",
            label="列数",
            dense=True,
            width=82,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._multi_setting_changed,
        )
        self.multi_panel_label_style = ft.Dropdown(
            value="(a)",
            label="标签格式",
            dense=True,
            width=126,
            options=[
                ft.DropdownOption(key="(a)", text="(a), (b)…"),
                ft.DropdownOption(key="a)", text="a), b)…"),
                ft.DropdownOption(key="(A)", text="(A), (B)…"),
                ft.DropdownOption(key="A", text="A, B…"),
                ft.DropdownOption(key="none", text="无标签"),
            ],
            on_select=self._multi_label_style_changed,
        )
        self.multi_panel_label_position = ft.Dropdown(
            value="upper_left",
            label="标签位置",
            dense=True,
            width=130,
            options=[
                ft.DropdownOption(key="upper_left", text="左上"),
                ft.DropdownOption(key="upper_right", text="右上"),
                ft.DropdownOption(key="lower_left", text="左下"),
                ft.DropdownOption(key="lower_right", text="右下"),
            ],
            on_select=self._multi_setting_changed,
        )
        self.multi_panel_palette = ft.Dropdown(
            value="sci_default",
            label="分峰色卡",
            dense=True,
            width=128,
            options=[
                ft.DropdownOption(key=value, text=label)
                for value, label in (
                    ("sci_default", "Science"),
                    ("nature", "Nature"),
                    ("okabe_ito", "Okabe–Ito"),
                    ("tableau", "Tableau"),
                    ("soft", "Soft"),
                    ("viridis", "Viridis"),
                )
            ],
            on_select=self._multi_setting_changed,
        )
        self.multi_panel_component_mode = ft.Dropdown(
            value="absolute",
            label="分峰模式",
            dense=True,
            width=136,
            options=[
                ft.DropdownOption(key="absolute", text="已包含背景"),
                ft.DropdownOption(key="relative", text="扣背景强度"),
            ],
            on_select=self._multi_setting_changed,
        )
        self.multi_panel_cell_width = ft.TextField(
            value="3.4",
            label="子图宽/英寸",
            dense=True,
            width=112,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._multi_setting_changed,
        )
        self.multi_panel_cell_height = ft.TextField(
            value="2.7",
            label="子图高/英寸",
            dense=True,
            width=112,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._multi_setting_changed,
        )
        self.multi_panel_dpi = ft.TextField(
            value="300",
            label="导出 DPI",
            dense=True,
            width=96,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._multi_setting_changed,
        )
        self.multi_panel_format = ft.Dropdown(
            value="png",
            label="导出格式",
            dense=True,
            width=105,
            options=[
                ft.DropdownOption(key="png", text="PNG"),
                ft.DropdownOption(key="svg", text="SVG"),
                ft.DropdownOption(key="pdf", text="PDF"),
                ft.DropdownOption(key="jpg", text="JPG"),
                ft.DropdownOption(key="tif", text="TIFF"),
            ],
            on_select=self._multi_setting_changed,
        )
        self.multi_panel_show_titles = ft.Switch(
            value=True, label="谱图标题", on_change=self._multi_setting_changed
        )
        self.multi_panel_show_legend = ft.Switch(
            value=True, label="图例", on_change=self._multi_setting_changed
        )
        self.multi_panel_hide_y_ticks = ft.Switch(
            value=True, label="隐藏 Y 刻度", on_change=self._multi_setting_changed
        )
        self.multi_panel_preview = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.GRID_VIEW_ROUNDED, size=34, color="#8AA0A6"),
                    ft.Text("选择谱图并设置布局，然后生成预览。", color=TEXT_MUTED),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, BORDER),
            border_radius=10,
            padding=10,
            height=310,
        )
        self.multi_panel_dialog = self._build_multi_panel_dialog()

    def build(self) -> None:
        self.page.title = "OpenXPSAnalyzer"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = ft.Theme(color_scheme_seed=ACCENT, use_material3=True)
        self.page.bgcolor = SURFACE
        self.page.padding = 0
        self.page.window.width = 1480
        self.page.window.height = 900
        self.page.window.min_width = 900
        self.page.window.min_height = 680
        self.page.drawer = ft.NavigationDrawer(
            selected_index=-1,
            bgcolor=ft.Colors.WHITE,
            elevation=18,
            controls=[self._build_project_drawer()],
        )
        self.page.end_drawer = ft.NavigationDrawer(
            selected_index=-1,
            bgcolor=ft.Colors.WHITE,
            elevation=18,
            controls=[self._build_analysis_drawer()],
        )
        self.page.appbar = ft.AppBar(
            leading=ft.IconButton(
                ft.Icons.MENU_ROUNDED,
                tooltip="项目数据",
                icon_color=ft.Colors.WHITE,
                on_click=self._show_project_drawer,
            ),
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.SCIENCE_OUTLINED, color=ft.Colors.WHITE, size=25),
                    ft.Column(
                        [
                            ft.Text("OpenXPSAnalyzer", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text("Avantage 数据分析工作台", size=11, opacity=0.78),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=10,
            ),
            bgcolor=ACCENT_DARK,
            color=ft.Colors.WHITE,
            actions=[
                ft.IconButton(
                    ft.Icons.CREATE_NEW_FOLDER_OUTLINED,
                    tooltip="新建项目",
                    on_click=self._new_project,
                ),
                ft.IconButton(
                    ft.Icons.FOLDER_OPEN_OUTLINED,
                    tooltip="打开 NetCDF 项目",
                    on_click=self._open_project,
                ),
                ft.IconButton(
                    ft.Icons.SAVE_OUTLINED,
                    tooltip="保存项目",
                    on_click=self._save_project,
                ),
                ft.IconButton(
                    ft.Icons.SAVE_AS_OUTLINED,
                    tooltip="项目另存为",
                    on_click=self._save_project_as,
                ),
                ft.IconButton(
                    ft.Icons.QUERY_STATS,
                    tooltip="分析结果",
                    on_click=self._show_analysis_drawer,
                ),
                ft.IconButton(
                    ft.Icons.INFO_OUTLINE,
                    tooltip="软件说明",
                    on_click=self._show_about,
                ),
                ft.Container(width=8),
            ],
        )
        self.page.add(
            ft.Container(
                content=self._build_workspace(),
                padding=ft.Padding.symmetric(horizontal=18, vertical=14),
                expand=True,
            )
        )
        self._refresh_library()
        self._refresh_metrics(None)
        self.page.update()

    def _build_project_drawer(self) -> ft.Control:
        return ft.Container(
            width=360,
            padding=18,
            expand=True,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FOLDER_COPY_OUTLINED, color=ACCENT, size=20),
                            ft.Text("项目数据", size=17, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                tooltip="收起",
                                on_click=self._close_project_drawer,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.project_title,
                    ft.Column(
                        [
                            ft.Button(
                                "单文件",
                                icon=ft.Icons.UPLOAD_FILE,
                                bgcolor=ACCENT,
                                color=ft.Colors.WHITE,
                                on_click=self._pick_excel,
                                width=320,
                            ),
                            ft.Button(
                                "文件夹",
                                icon=ft.Icons.DRIVE_FOLDER_UPLOAD_OUTLINED,
                                on_click=self._pick_folder,
                                width=320,
                                visible=not self.page.web,
                            ),
                            ft.Button(
                                "批量文件",
                                icon=ft.Icons.UPLOAD_FILE_OUTLINED,
                                on_click=self._pick_multiple_files,
                                width=320,
                            ),
                        ],
                        spacing=7,
                    ),
                    ft.Row(
                        [
                            ft.Button(
                                "保存项目",
                                icon=ft.Icons.SAVE_OUTLINED,
                                on_click=self._save_project,
                                expand=True,
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="删除选中谱图",
                                icon_color="#A13D3D",
                                on_click=self._delete_selected,
                            ),
                        ]
                    ),
                    ft.Divider(height=12, color=BORDER),
                    ft.Row(
                        [
                            ft.Text("谱图", size=13, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            self.spectrum_count,
                        ]
                    ),
                    self.spectrum_list,
                    ft.Container(
                        content=ft.Text(
                            f"OpenXPSAnalyzer · AGPL-3.0-or-later · v{APP_VERSION}",
                            size=10,
                            color=TEXT_MUTED,
                        ),
                        padding=ft.Padding.only(top=6),
                    ),
                ],
                spacing=10,
                expand=True,
            ),
        )

    def _build_workspace(self) -> ft.Control:
        settings = ft.Row(
            [
                self.chart_view_mode,
                self.palette,
                self.component_mode,
                self.show_legend,
                ft.Button(
                    "分峰命名", icon=ft.Icons.EDIT_NOTE_OUTLINED, on_click=self._open_peak_names
                ),
                ft.Button("导出图片", icon=ft.Icons.IMAGE_OUTLINED, on_click=self._export_image),
                ft.Button("交互式 HTML", icon=ft.Icons.CODE, on_click=self._export_html),
                ft.Button(
                    "多子图绘图",
                    icon=ft.Icons.AUTO_AWESOME_MOSAIC_OUTLINED,
                    on_click=self._open_multi_panel_dialog,
                ),
            ],
            wrap=True,
            spacing=8,
            run_spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [self.selection_title, self.selection_subtitle],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Button(
                                "项目数据",
                                icon=ft.Icons.FOLDER_COPY_OUTLINED,
                                on_click=self._show_project_drawer,
                            ),
                            ft.Button(
                                "分析结果",
                                icon=ft.Icons.QUERY_STATS,
                                on_click=self._show_analysis_drawer,
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.Padding.only(left=2, bottom=2),
                ),
                ft.Container(
                    content=settings,
                    bgcolor=SURFACE_TINT,
                    border=ft.Border.all(1, BORDER),
                    border_radius=12,
                    padding=10,
                ),
                self.chart_host,
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.TABLE_ROWS_OUTLINED, size=18, color=ACCENT),
                            ft.Text("数据预览", weight=ft.FontWeight.W_600),
                            self.preview_mode,
                            self.preview_status,
                            ft.Container(expand=True),
                            self.preview_previous,
                            self.preview_next,
                            ft.IconButton(
                                ft.Icons.DOWNLOAD_OUTLINED,
                                tooltip="导出当前谱图 CSV",
                                on_click=self._export_csv,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=ft.Colors.WHITE,
                    border=ft.Border.all(1, BORDER),
                    border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                ),
                self.preview_host,
                ft.Row(
                    [
                        ft.Icon(ft.Icons.VERIFIED_USER_OUTLINED, size=14, color=ACCENT),
                        ft.Text(
                            "OpenXPSAnalyzer · GNU AGPL v3 or later · Source available on GitHub",
                            size=10,
                            color=TEXT_MUTED,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _build_analysis_drawer(self) -> ft.Control:
        return ft.Container(
            width=380,
            padding=18,
            expand=True,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.QUERY_STATS, color=ACCENT, size=21),
                            ft.Text("分析结果", size=17, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                tooltip="收起",
                                on_click=self._close_analysis_drawer,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=10, color=BORDER),
                    self.metrics_host,
                ],
                spacing=8,
                expand=True,
            ),
        )

    def _build_import_dialog(self) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text("导入 Avantage 数据"),
            content=ft.Container(
                width=500,
                content=ft.Column(
                    [
                        ft.Text("Excel 前 15 行将按 Avantage 导出格式跳过。", color=TEXT_MUTED),
                        self.import_name,
                        self.import_kind,
                        self.import_peaks,
                    ],
                    spacing=14,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=self._close_dialog),
                ft.Button(
                    "导入",
                    icon=ft.Icons.UPLOAD_FILE,
                    bgcolor=ACCENT,
                    color=ft.Colors.WHITE,
                    on_click=self._confirm_import,
                ),
            ],
        )

    def _build_peak_names_dialog(self) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑分峰名称"),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    [
                        ft.Text(
                            "名称顺序必须与 Avantage 文件中从左到右的分峰顺序一致。",
                            color=TEXT_MUTED,
                        ),
                        self.peak_names_field,
                    ],
                    tight=True,
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("取消", on_click=self._close_dialog),
                ft.Button(
                    "应用",
                    icon=ft.Icons.CHECK,
                    bgcolor=ACCENT,
                    color=ft.Colors.WHITE,
                    on_click=self._confirm_peak_names,
                ),
            ],
        )

    def _build_about_dialog(self) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.SCIENCE_OUTLINED, color=ACCENT, size=28),
                    ft.Text("OpenXPSAnalyzer 软件说明", weight=ft.FontWeight.W_600),
                ]
            ),
            content=ft.Container(
                width=620,
                content=ft.Column(
                    [
                        ft.Text(
                            f"版本 {APP_VERSION} · Avantage XPS 数据分析工作台",
                            size=15,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Text(
                            "用于 Avantage Excel 数据读取、xarray 管理、NetCDF-4/HDF5 "
                            "存储、谱图分析、交互预览和可配置多子图绘制。",
                            color=TEXT_MUTED,
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("开源许可", weight=ft.FontWeight.W_600, color=ACCENT),
                                    ft.Text(
                                        "Copyright © 2026 Jay Mamun and OpenXPSAnalyzer contributors.\n"
                                        "本软件按照 GNU AGPL v3 或更高版本发布。你可以使用、修改和"
                                        "再分发；分发修改版或通过网络提供修改版时，必须按许可证提供"
                                        "相应源代码。本软件不提供任何担保。\n"
                                        f"源代码：{PROJECT_URL}",
                                        selectable=True,
                                    ),
                                ],
                                spacing=6,
                            ),
                            bgcolor=ACCENT_LIGHT,
                            border=ft.Border.all(1, "#BEDDE2"),
                            border_radius=10,
                            padding=12,
                        ),
                        ft.Text("平台支持", weight=ft.FontWeight.W_600),
                        ft.Row(
                            [
                                self._platform_badge("Web", ft.Icons.LANGUAGE),
                                self._platform_badge("macOS", ft.Icons.LAPTOP_MAC),
                                self._platform_badge("Windows", ft.Icons.WINDOW),
                            ],
                            wrap=True,
                            spacing=8,
                        ),
                        ft.Text(
                            "网页端支持上传单个或多个 Excel，并下载 NetCDF、谱图图片、HTML、"
                            "CSV 和多子图；桌面端额外支持读取本地文件夹及直接保存输出文件。"
                            "界面使用平台系统字体，"
                            "绘图会自动尝试 PingFang SC、微软雅黑、Noto CJK 等字体。",
                            size=12,
                            color=TEXT_MUTED,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
            actions=[
                ft.TextButton("查看源代码", icon=ft.Icons.CODE, url=PROJECT_URL),
                ft.Button("关闭", icon=ft.Icons.CLOSE, on_click=self._close_dialog),
            ],
        )

    def _build_multi_panel_dialog(self) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.AUTO_AWESOME_MOSAIC_OUTLINED, color=ACCENT, size=24),
                    ft.Column(
                        [
                            ft.Text("多子图绘图", size=18, weight=ft.FontWeight.W_600),
                            ft.Text(
                                "选择当前工作区谱图、调整顺序并生成一张组合图",
                                size=11,
                                color=TEXT_MUTED,
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=10,
            ),
            content=ft.Container(
                width=1020,
                height=650,
                content=ft.Row(
                    [
                        ft.Container(
                            width=355,
                            padding=ft.Padding.only(right=12),
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                "谱图选择与顺序",
                                                weight=ft.FontWeight.W_600,
                                                expand=True,
                                            ),
                                            ft.IconButton(
                                                ft.Icons.SELECT_ALL,
                                                tooltip="全选",
                                                on_click=self._select_all_multi_panel,
                                            ),
                                            ft.IconButton(
                                                ft.Icons.CLEAR_ALL,
                                                tooltip="清空选择",
                                                on_click=self._clear_multi_panel_selection,
                                            ),
                                        ],
                                        spacing=2,
                                    ),
                                    ft.Text(
                                        "勾选要绘制的谱图；使用箭头调整子图顺序；标签文本可单独编辑。",
                                        size=11,
                                        color=TEXT_MUTED,
                                    ),
                                    self.multi_panel_status,
                                    ft.Divider(height=8, color=BORDER),
                                    self.multi_panel_list,
                                ],
                                spacing=7,
                                expand=True,
                            ),
                        ),
                        ft.VerticalDivider(width=1, color=BORDER),
                        ft.Container(
                            padding=ft.Padding.only(left=12),
                            expand=True,
                            content=ft.Column(
                                [
                                    ft.Text("布局与样式", weight=ft.FontWeight.W_600),
                                    ft.Row(
                                        [
                                            self.multi_panel_rows,
                                            self.multi_panel_cols,
                                            self.multi_panel_label_style,
                                            self.multi_panel_label_position,
                                            ft.Button(
                                                "生成标签",
                                                icon=ft.Icons.REFRESH,
                                                tooltip="按当前选择和顺序重新生成标签",
                                                on_click=self._regenerate_multi_panel_labels,
                                            ),
                                        ],
                                        wrap=True,
                                        spacing=8,
                                        run_spacing=8,
                                    ),
                                    ft.Row(
                                        [
                                            self.multi_panel_palette,
                                            self.multi_panel_component_mode,
                                            self.multi_panel_cell_width,
                                            self.multi_panel_cell_height,
                                            self.multi_panel_dpi,
                                            self.multi_panel_format,
                                        ],
                                        wrap=True,
                                        spacing=8,
                                        run_spacing=8,
                                    ),
                                    ft.Row(
                                        [
                                            self.multi_panel_show_titles,
                                            self.multi_panel_show_legend,
                                            self.multi_panel_hide_y_ticks,
                                        ],
                                        wrap=True,
                                        spacing=8,
                                        run_spacing=8,
                                    ),
                                    ft.Row(
                                        [
                                            ft.Button(
                                                "生成预览",
                                                icon=ft.Icons.VISIBILITY_OUTLINED,
                                                bgcolor=ACCENT_LIGHT,
                                                color=ACCENT_DARK,
                                                on_click=self._preview_multi_panel,
                                            ),
                                            ft.Button(
                                                "导出多子图",
                                                icon=ft.Icons.DOWNLOAD_OUTLINED,
                                                bgcolor=ACCENT,
                                                color=ft.Colors.WHITE,
                                                on_click=self._export_multi_panel,
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.END,
                                        spacing=8,
                                    ),
                                    self.multi_panel_preview,
                                ],
                                spacing=10,
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                        ),
                    ],
                    spacing=0,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
            actions=[ft.TextButton("关闭", on_click=self._close_dialog)],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _empty_chart_state(self) -> ft.Control:
        return ft.Column(
            [
                ft.Icon(ft.Icons.SHOW_CHART, size=64, color="#ADC1C9"),
                ft.Text("尚无可显示的谱图", size=17, color=TEXT_MUTED),
                ft.Text("支持 Survey、拟合包络、背景与多个分峰", size=12, color="#84969F"),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        )

    def _empty_preview_state(self) -> ft.Control:
        return ft.Container(
            content=ft.Text("导入或选择谱图后显示数值数据。", color=TEXT_MUTED),
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, BORDER),
            border_radius=10,
            expand=True,
        )

    def _selected(self) -> Spectrum | None:
        return self.project.get(self.selected_id)

    async def _show_project_drawer(self, _: ft.Event[Any]) -> None:
        await self.page.show_drawer()

    async def _close_project_drawer(self, _: ft.Event[Any]) -> None:
        await self.page.close_drawer()

    async def _show_analysis_drawer(self, _: ft.Event[Any]) -> None:
        await self.page.show_end_drawer()

    async def _close_analysis_drawer(self, _: ft.Event[Any]) -> None:
        await self.page.close_end_drawer()

    def _show_about(self, _: ft.Event[Any]) -> None:
        self.page.show_dialog(self.about_dialog)

    def _open_multi_panel_dialog(self, _: ft.Event[Any]) -> None:
        if not self.project.spectra:
            self._notify("当前工作区没有可用于多子图绘制的谱图。", error=True)
            return
        self.multi_panel_order = list(self.project.spectra)
        self.multi_panel_selected = set(self.multi_panel_order)
        count = len(self.multi_panel_order)
        cols = min(3, count)
        self.multi_panel_cols.value = str(cols)
        self.multi_panel_rows.value = str(math.ceil(count / cols))
        self.multi_panel_palette.value = self.palette.value or "sci_default"
        self.multi_panel_component_mode.value = self.component_mode.value or "absolute"
        self.multi_panel_show_legend.value = bool(self.show_legend.value)
        self.multi_panel_label_style.value = "(a)"
        self.multi_panel_labels = dict(
            zip(
                self.multi_panel_order,
                generate_panel_labels(count, "(a)"),
                strict=True,
            )
        )
        self._set_multi_panel_preview_placeholder()
        self._refresh_multi_panel_list()
        self.page.show_dialog(self.multi_panel_dialog)

    def _set_multi_panel_preview_placeholder(
        self, message: str = "选择谱图并设置布局，然后生成预览。"
    ) -> None:
        self.multi_panel_preview.content = ft.Column(
            [
                ft.Icon(ft.Icons.GRID_VIEW_ROUNDED, size=34, color="#8AA0A6"),
                ft.Text(message, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        )

    def _selected_multi_panel_ids(self) -> list[str]:
        return [
            spectrum_id
            for spectrum_id in self.multi_panel_order
            if spectrum_id in self.multi_panel_selected
        ]

    def _refresh_multi_panel_status(self) -> None:
        selected_count = len(self._selected_multi_panel_ids())
        try:
            rows = int(str(self.multi_panel_rows.value).strip())
            cols = int(str(self.multi_panel_cols.value).strip())
            capacity = rows * cols
        except (TypeError, ValueError):
            self.multi_panel_status.value = f"已选择 {selected_count} 条 · 请输入有效行列数"
            self.multi_panel_status.color = ERROR
            return
        if selected_count < 1:
            self.multi_panel_status.value = "尚未选择谱图"
            self.multi_panel_status.color = ERROR
        elif rows < 1 or cols < 1 or capacity < selected_count:
            self.multi_panel_status.value = (
                f"已选择 {selected_count} 条 · 当前容量 {max(capacity, 0)}，布局不足"
            )
            self.multi_panel_status.color = ERROR
        else:
            self.multi_panel_status.value = (
                f"已选择 {selected_count} 条 · {rows} × {cols} 布局 · "
                f"{capacity - selected_count} 个空位"
            )
            self.multi_panel_status.color = TEXT_MUTED

    def _refresh_multi_panel_list(self) -> None:
        controls: list[ft.Control] = []
        for index, spectrum_id in enumerate(self.multi_panel_order):
            spectrum = self.project.get(spectrum_id)
            if spectrum is None:
                continue
            selected = spectrum_id in self.multi_panel_selected
            controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Checkbox(
                                value=selected,
                                data=spectrum_id,
                                tooltip="加入多子图",
                                on_change=self._multi_panel_selection_changed,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        spectrum.name,
                                        weight=ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        tooltip=spectrum.name,
                                    ),
                                    ft.Text(
                                        f"{spectrum.region} · {spectrum.point_count} 点",
                                        size=10,
                                        color=TEXT_MUTED,
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                            ),
                            ft.TextField(
                                value=self.multi_panel_labels.get(spectrum_id, ""),
                                data=spectrum_id,
                                hint_text="标签",
                                tooltip="可编辑，例如 (a)、(b) 或自定义文本",
                                dense=True,
                                width=66,
                                text_size=11,
                                on_change=self._multi_panel_label_changed,
                            ),
                            ft.Column(
                                [
                                    ft.IconButton(
                                        ft.Icons.ARROW_UPWARD,
                                        data=f"{spectrum_id}|-1",
                                        tooltip="上移",
                                        disabled=index == 0,
                                        icon_size=16,
                                        on_click=self._move_multi_panel_spectrum,
                                    ),
                                    ft.IconButton(
                                        ft.Icons.ARROW_DOWNWARD,
                                        data=f"{spectrum_id}|1",
                                        tooltip="下移",
                                        disabled=index == len(self.multi_panel_order) - 1,
                                        icon_size=16,
                                        on_click=self._move_multi_panel_spectrum,
                                    ),
                                ],
                                spacing=-10,
                                tight=True,
                            ),
                        ],
                        spacing=3,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=5, vertical=3),
                    bgcolor=ACCENT_LIGHT if selected else ft.Colors.WHITE,
                    border=ft.Border.all(1, "#C5DDE1" if selected else BORDER),
                    border_radius=8,
                )
            )
        self.multi_panel_list.controls = controls
        self._refresh_multi_panel_status()

    def _multi_setting_changed(self, event: ft.Event[Any]) -> None:
        self._sync_event_value(event)
        self._refresh_multi_panel_status()
        self._set_multi_panel_preview_placeholder("设置已更改，请重新生成预览。")
        if self.multi_panel_dialog.open:
            self.page.update(self.multi_panel_status, self.multi_panel_preview)

    def _multi_panel_selection_changed(self, event: ft.Event[ft.Checkbox]) -> None:
        self._sync_event_value(event)
        spectrum_id = str(event.control.data)
        if event.control.value:
            self.multi_panel_selected.add(spectrum_id)
        else:
            self.multi_panel_selected.discard(spectrum_id)
        self._refresh_multi_panel_status()
        self._set_multi_panel_preview_placeholder("谱图选择已更改，请重新生成预览。")
        self.page.update(self.multi_panel_status, self.multi_panel_preview)

    def _multi_panel_label_changed(self, event: ft.Event[ft.TextField]) -> None:
        self._sync_event_value(event)
        self.multi_panel_labels[str(event.control.data)] = str(event.control.value or "").strip()
        self._set_multi_panel_preview_placeholder("标签已更改，请重新生成预览。")
        self.page.update(self.multi_panel_preview)

    def _move_multi_panel_spectrum(self, event: ft.Event[ft.IconButton]) -> None:
        spectrum_id, direction_text = str(event.control.data).rsplit("|", 1)
        current = self.multi_panel_order.index(spectrum_id)
        target = current + int(direction_text)
        if not 0 <= target < len(self.multi_panel_order):
            return
        self.multi_panel_order[current], self.multi_panel_order[target] = (
            self.multi_panel_order[target],
            self.multi_panel_order[current],
        )
        self._refresh_multi_panel_list()
        self._set_multi_panel_preview_placeholder("谱图顺序已更改，请重新生成预览。")
        self.page.update(self.multi_panel_list, self.multi_panel_status, self.multi_panel_preview)

    def _select_all_multi_panel(self, _: ft.Event[Any]) -> None:
        self.multi_panel_selected = set(self.multi_panel_order)
        self._refresh_multi_panel_list()
        self._set_multi_panel_preview_placeholder("谱图选择已更改，请重新生成预览。")
        self.page.update(self.multi_panel_list, self.multi_panel_status, self.multi_panel_preview)

    def _clear_multi_panel_selection(self, _: ft.Event[Any]) -> None:
        self.multi_panel_selected.clear()
        self._refresh_multi_panel_list()
        self._set_multi_panel_preview_placeholder("谱图选择已更改，请重新生成预览。")
        self.page.update(self.multi_panel_list, self.multi_panel_status, self.multi_panel_preview)

    def _multi_label_style_changed(self, event: ft.Event[Any]) -> None:
        self._sync_event_value(event)
        self._regenerate_multi_panel_labels(event)

    def _regenerate_multi_panel_labels(self, _: ft.Event[Any] | None = None) -> None:
        selected_ids = self._selected_multi_panel_ids()
        labels = generate_panel_labels(
            len(selected_ids), self.multi_panel_label_style.value or "(a)"
        )
        for spectrum_id in self.multi_panel_order:
            self.multi_panel_labels[spectrum_id] = ""
        for spectrum_id, label in zip(selected_ids, labels, strict=True):
            self.multi_panel_labels[spectrum_id] = label
        self._refresh_multi_panel_list()
        self._set_multi_panel_preview_placeholder("标签已重新生成，请生成预览。")
        if self.multi_panel_dialog.open:
            self.page.update(
                self.multi_panel_list, self.multi_panel_status, self.multi_panel_preview
            )

    def _multi_panel_config(self) -> MultiPanelConfig:
        try:
            rows = int(str(self.multi_panel_rows.value).strip())
            cols = int(str(self.multi_panel_cols.value).strip())
            cell_width = float(str(self.multi_panel_cell_width.value).strip())
            cell_height = float(str(self.multi_panel_cell_height.value).strip())
            dpi = int(str(self.multi_panel_dpi.value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("行列数、子图尺寸和 DPI 必须是有效数字。") from exc
        return MultiPanelConfig(
            rows=rows,
            cols=cols,
            palette=self.multi_panel_palette.value or "sci_default",
            component_mode=self.multi_panel_component_mode.value or "absolute",
            show_titles=bool(self.multi_panel_show_titles.value),
            show_legend=bool(self.multi_panel_show_legend.value),
            hide_y_ticks=bool(self.multi_panel_hide_y_ticks.value),
            cell_width=cell_width,
            cell_height=cell_height,
            label_position=self.multi_panel_label_position.value or "upper_left",
            dpi=dpi,
        )

    def _multi_panel_data(self) -> tuple[list[Spectrum], list[str], MultiPanelConfig]:
        ids = self._selected_multi_panel_ids()
        spectra = [
            spectrum
            for spectrum_id in ids
            if (spectrum := self.project.get(spectrum_id)) is not None
        ]
        labels = [self.multi_panel_labels.get(spectrum_id, "") for spectrum_id in ids]
        config = self._multi_panel_config()
        config.validate(len(spectra))
        return spectra, labels, config

    def _preview_multi_panel(self, _: ft.Event[Any]) -> None:
        self.multi_panel_preview.content = ft.ProgressRing(color=ACCENT)
        self.page.update(self.multi_panel_preview)
        try:
            spectra, labels, config = self._multi_panel_data()
            payload = render_multi_panel_figure(
                spectra,
                config,
                labels=labels,
                file_format="png",
                preview=True,
            )
            self.multi_panel_preview.content = ft.Image(
                src=payload,
                fit=ft.BoxFit.CONTAIN,
                filter_quality=ft.FilterQuality.HIGH,
                anti_alias=True,
                gapless_playback=True,
                semantics_label="XPS 多子图预览",
            )
        except Exception as exc:
            self.multi_panel_preview.content = ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=ERROR, size=30),
                    ft.Text("无法生成多子图预览", weight=ft.FontWeight.W_600, color=ERROR),
                    ft.Text(
                        str(exc),
                        size=11,
                        color=TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                        selectable=True,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            )
        self.page.update(self.multi_panel_preview)

    async def _export_multi_panel(self, _: ft.Event[Any]) -> None:
        try:
            spectra, labels, config = self._multi_panel_data()
        except Exception as exc:
            self._notify(f"多子图设置无效：{exc}", error=True)
            return
        file_format = self.multi_panel_format.value or "png"
        file_name = f"{self._safe_filename(self.project.name)}_multi_panel.{file_format}"
        if self.page.web:
            try:
                payload = render_multi_panel_figure(
                    spectra,
                    config,
                    labels=labels,
                    file_format=file_format,
                )
                await ft.FilePicker().save_file(file_name=file_name, src_bytes=payload)
            except Exception as exc:
                self._notify(f"导出多子图失败：{exc}", error=True)
                return
            self._notify(f"多子图下载已准备：{file_name}")
            return

        path = await ft.FilePicker().save_file(
            dialog_title="导出 XPS 多子图",
            file_name=file_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=[file_format],
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(f".{file_format}")
        try:
            exported = export_multi_panel_figure(spectra, config, target, labels=labels)
        except Exception as exc:
            self._notify(f"导出多子图失败：{exc}", error=True)
            return
        self._notify(f"多子图已导出：{exported.name}")

    def _rename_project(self, _: ft.Event[Any]) -> None:
        name = self.project_title.value.strip() or "Untitled project"
        if name != self.project.name:
            self.project.name = name
            self.project.dirty = True
        self.project_title.value = name
        self.page.update(self.project_title)

    async def _pick_excel(self, _: ft.Event[Any]) -> None:
        files = await ft.FilePicker().pick_files(
            dialog_title="选择 Avantage Excel 数据",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xlsm", "xls"],
            with_data=True,
        )
        if not files:
            return
        selected = files[0]
        if not selected.path and not selected.bytes:
            self._notify("无法取得所选 Excel 的路径或文件内容。", error=True)
            return
        self.pending_excel = Path(selected.path) if selected.path else None
        self.pending_excel_data = selected.bytes
        self.pending_excel_name = selected.name
        self.import_name.value = Path(selected.name).stem
        self.import_kind.value = "auto"
        self.import_peaks.value = ""
        self.page.show_dialog(self.import_dialog)

    def _read_import_payload(
        self,
        *,
        path: Path | None,
        data: bytes | None,
        name: str,
        kind: str = "auto",
        peaks: list[str] | None = None,
    ):
        if path is not None:
            return read_avantage(path, kind=kind, peaks=peaks)
        if data is None:
            raise ValueError("没有可读取的 Excel 文件内容。")
        with tempfile.TemporaryDirectory(prefix="xps-upload-") as folder:
            temporary = Path(folder) / Path(name).name
            temporary.write_bytes(data)
            return read_avantage(temporary, kind=kind, peaks=peaks)

    async def _pick_multiple_files(self, _: ft.Event[Any]) -> None:
        files = await ft.FilePicker().pick_files(
            dialog_title="批量选择 Avantage Excel 数据",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xlsm", "xls"],
            allow_multiple=True,
            with_data=True,
        )
        if not files:
            return

        if not self.project.spectra and self.project.name == "Untitled project":
            native_paths = [Path(file.path) for file in files if file.path]
            self.project.name = (
                native_paths[0].parent.name
                if native_paths
                and all(path.parent == native_paths[0].parent for path in native_paths)
                else "Batch import"
            )

        imported_ids: list[str] = []
        failures: list[str] = []
        for file in files:
            try:
                frame = self._read_import_payload(
                    path=Path(file.path) if file.path else None,
                    data=file.bytes,
                    name=file.name,
                )
                spectrum = Spectrum.from_dataframe(
                    name=Path(file.name).stem,
                    frame=frame,
                    source_path=file.path or file.name,
                    sample=self.project.name,
                    region=Path(file.name).stem,
                )
                self.project.add(spectrum)
                imported_ids.append(spectrum.spectrum_id)
            except (XPSError, ValueError) as exc:
                failures.append(f"{file.name}: {exc}")

        if not imported_ids:
            self._notify("批量导入失败：" + "；".join(failures), error=True)
            return
        self.project_title.value = self.project.name
        self.selected_id = imported_ids[0]
        self.preview_page = 0
        self._refresh_all()
        await self.page.close_drawer()
        message = f"已批量导入 {len(imported_ids)} 条谱图。"
        if failures:
            message += f"另有 {len(failures)} 个文件失败。"
        self._notify(message, error=bool(failures))

    async def _pick_folder(self, _: ft.Event[Any]) -> None:
        folder_path = await ft.FilePicker().get_directory_path(
            dialog_title="选择包含 Avantage Excel 数据的文件夹"
        )
        if not folder_path:
            return
        try:
            imported = project_from_avantage_folder(folder_path)
        except (XPSError, ValueError) as exc:
            self._notify(str(exc), error=True)
            return
        imported_ids = list(imported.spectra)
        if not self.project.spectra:
            self.project = imported
        else:
            for spectrum in imported.spectra.values():
                self.project.add(spectrum)
        self.project_title.value = self.project.name
        self.selected_id = imported_ids[0] if imported_ids else None
        self.preview_page = 0
        self._refresh_all()
        await self.page.close_drawer()
        self._notify(
            f"已从 {Path(folder_path).name} 导入 {len(imported_ids)} 条谱图；"
            "谱图及 xarray 节点名称采用文件名 stem。"
        )

    async def _confirm_import(self, _: ft.Event[Any]) -> None:
        if self.pending_excel is None and self.pending_excel_data is None:
            self._notify("未选择 Excel 文件。", error=True)
            return
        peaks = [value.strip() for value in self.import_peaks.value.split(",") if value.strip()]
        try:
            frame = self._read_import_payload(
                path=self.pending_excel,
                data=self.pending_excel_data,
                name=self.pending_excel_name,
                kind=self.import_kind.value or "auto",
                peaks=peaks or None,
            )
            source_reference = str(self.pending_excel or self.pending_excel_name)
            default_name = Path(self.pending_excel_name).stem
            spectrum = Spectrum.from_dataframe(
                name=self.import_name.value.strip() or default_name,
                frame=frame,
                source_path=source_reference,
                sample=self.project.name,
                region=default_name,
            )
            self.project.add(spectrum)
        except (XPSError, ValueError) as exc:
            self._notify(str(exc), error=True)
            return
        self.page.pop_dialog()
        self.selected_id = spectrum.spectrum_id
        self.preview_page = 0
        self._refresh_all()
        await self.page.close_drawer()
        self._notify(f"已导入 {spectrum.name}，共 {spectrum.point_count} 个数据点。")

    def _close_dialog(self, _: ft.Event[Any]) -> None:
        self.page.pop_dialog()
        self.page.update()

    def _open_peak_names(self, _: ft.Event[Any]) -> None:
        spectrum = self._selected()
        if spectrum is None:
            self._notify("请先选择谱图。", error=True)
            return
        if not spectrum.components:
            self._notify("当前谱图没有可重命名的拟合分峰。", error=True)
            return
        self.peak_names_field.value = ", ".join(spectrum.components)
        self.page.show_dialog(self.peak_names_dialog)

    def _confirm_peak_names(self, _: ft.Event[Any]) -> None:
        spectrum = self._selected()
        if spectrum is None:
            self.page.pop_dialog()
            return
        names = [name.strip() for name in self.peak_names_field.value.split(",")]
        try:
            spectrum.rename_components(names)
        except (XPSError, ValueError) as exc:
            self._notify(str(exc), error=True)
            return
        self.project.dirty = True
        self.page.pop_dialog()
        self._refresh_all()
        self._notify(f"已更新 {spectrum.name} 的分峰名称。")

    def _refresh_all(self) -> None:
        spectrum = self._selected()
        self._refresh_library()
        self._refresh_chart(spectrum)
        self._refresh_metrics(spectrum)
        self._refresh_preview(spectrum)
        self.page.update()

    def _refresh_library(self) -> None:
        self.spectrum_list.controls.clear()
        self.spectrum_count.value = str(len(self.project))
        for spectrum_id, spectrum in self.project.spectra.items():
            kind = "拟合谱" if spectrum.spectrum_type is SpectrumType.FIT else "原始谱"
            subtitle = f"{kind} · {spectrum.point_count} 点"
            if spectrum.components:
                subtitle += f" · {len(spectrum.components)} 分峰"
            self.spectrum_list.controls.append(
                ft.ListTile(
                    leading=ft.Icon(
                        ft.Icons.MULTILINE_CHART
                        if spectrum.spectrum_type is SpectrumType.FIT
                        else ft.Icons.SHOW_CHART,
                        color=ACCENT,
                        size=21,
                    ),
                    title=ft.Text(
                        spectrum.name,
                        size=13,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=spectrum.name,
                    ),
                    subtitle=ft.Text(
                        subtitle,
                        size=10,
                        color=TEXT_MUTED,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=subtitle,
                    ),
                    selected=spectrum_id == self.selected_id,
                    selected_tile_color=ACCENT_LIGHT,
                    shape=ft.RoundedRectangleBorder(radius=8),
                    dense=True,
                    data=spectrum_id,
                    on_click=self._select_spectrum,
                )
            )

    async def _select_spectrum(self, event: ft.Event[ft.ListTile]) -> None:
        self.selected_id = str(event.control.data)
        self.preview_page = 0
        self._refresh_all()
        await self.page.close_drawer()

    @staticmethod
    def _sync_event_value(event: ft.Event[Any]) -> None:
        """Apply client event data before rebuilding controls.

        Flet web can dispatch a selection event before the server-side control
        property has been synchronized, especially for Dropdown controls.
        """

        data = getattr(event, "data", None)
        control = event.control
        if data is None:
            return
        if isinstance(control, (ft.Dropdown, ft.TextField)):
            control.value = str(data)
        elif isinstance(control, (ft.Switch, ft.Checkbox)):
            control.value = str(data).lower() == "true"
        elif isinstance(control, ft.SegmentedButton):
            if isinstance(data, (list, tuple, set)):
                selected = list(data)
            else:
                try:
                    selected = json.loads(str(data))
                except (TypeError, ValueError, json.JSONDecodeError):
                    selected = [str(data)]
            control.selected = (
                [str(value) for value in selected]
                if isinstance(selected, list)
                else [str(selected)]
            )

    def _plot_setting_changed(self, event: ft.Event[Any]) -> None:
        self._sync_event_value(event)
        spectrum = self._selected()
        if spectrum is None:
            return
        self._refresh_chart(spectrum)
        self._refresh_metrics(spectrum)
        self.page.update()

    def _refresh_chart(self, spectrum: Spectrum | None) -> None:
        if spectrum is None:
            self.selection_title.value = "未选择谱图"
            self.selection_subtitle.value = "导入 Avantage Excel 数据开始分析"
            self.chart_host.content = self._empty_chart_state()
            return
        self.selection_title.value = spectrum.name
        type_label = (
            "拟合高分辨谱" if spectrum.spectrum_type is SpectrumType.FIT else "Survey / 原始谱"
        )
        self.selection_subtitle.value = (
            f"{spectrum.sample or self.project.name}/{spectrum.region} · {type_label} · "
            f"{spectrum.point_count} 个数据点 · "
            f"xarray Dataset · {len(spectrum.components)} 个分峰"
        )
        self.selection_subtitle.tooltip = self.selection_subtitle.value
        try:
            if "interactive" in self.chart_view_mode.selected:
                self.chart_host.content = build_interactive_spectrum_chart(
                    spectrum,
                    palette=self.palette.value or "sci_default",
                    component_mode=self.component_mode.value or "absolute",
                    show_legend=bool(self.show_legend.value),
                )
            else:
                preview = render_spectrum_preview(
                    spectrum,
                    palette=self.palette.value or "sci_default",
                    component_mode=self.component_mode.value or "absolute",
                    show_legend=bool(self.show_legend.value),
                )
                self.chart_host.content = ft.Image(
                    src=preview,
                    fit=ft.BoxFit.CONTAIN,
                    filter_quality=ft.FilterQuality.HIGH,
                    anti_alias=True,
                    gapless_playback=True,
                    semantics_label=f"{spectrum.name} XPS 谱图",
                )
        except Exception as exc:
            self.chart_host.content = ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=38, color=ERROR),
                    ft.Text("谱图预览生成失败", weight=ft.FontWeight.W_600, color=ERROR),
                    ft.Text(
                        str(exc),
                        size=12,
                        color=TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                        max_lines=4,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=str(exc),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            )

    def _refresh_metrics(self, spectrum: Spectrum | None) -> None:
        self.metrics_host.controls.clear()
        if spectrum is None:
            self.metrics_host.controls.append(
                ft.Text("选择谱图后显示能量范围、峰位和拟合质量。", color=TEXT_MUTED)
            )
            return
        try:
            metrics = analyze_spectrum(spectrum, self.component_mode.value or "absolute")
        except (TypeError, ValueError, FloatingPointError) as exc:
            self.metrics_host.controls.append(
                ft.Text(f"分析失败：{exc}", color=ERROR, selectable=True)
            )
            return
        self.metrics_host.controls.extend(self._metric_summary(metrics, spectrum))
        if metrics.components:
            self.metrics_host.controls.extend(
                [
                    ft.Divider(color=BORDER),
                    ft.Text("分峰指标", weight=ft.FontWeight.W_600),
                    *[
                        ft.Container(
                            padding=10,
                            border=ft.Border.all(1, BORDER),
                            border_radius=8,
                            content=ft.Column(
                                [
                                    ft.Text(
                                        component.name,
                                        weight=ft.FontWeight.W_600,
                                        color=ACCENT,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        tooltip=component.name,
                                    ),
                                    self._key_value("峰位", f"{component.peak_position_ev:.3f} eV"),
                                    self._key_value("峰高", f"{component.peak_height:.4g}"),
                                    self._key_value("积分面积", f"{component.area:.4g}"),
                                ],
                                spacing=4,
                            ),
                        )
                        for component in metrics.components
                    ],
                ]
            )

    def _metric_summary(self, metrics: SpectrumMetrics, spectrum: Spectrum) -> list[ft.Control]:
        controls: list[ft.Control] = [
            self._key_value("样品", spectrum.sample or self.project.name),
            self._key_value("区域", spectrum.region),
            self._key_value(
                "类型", "拟合谱" if spectrum.spectrum_type is SpectrumType.FIT else "原始谱"
            ),
            self._key_value("数据点", str(metrics.point_count)),
            self._key_value("能量范围", f"{metrics.energy_min:.3f} – {metrics.energy_max:.3f} eV"),
            self._key_value("原始谱最大峰位", f"{metrics.raw_peak_position_ev:.3f} eV"),
            self._key_value(
                "强度范围", f"{metrics.intensity_min:.4g} – {metrics.intensity_max:.4g}"
            ),
        ]
        if metrics.rmse is not None:
            controls.extend(
                [
                    ft.Divider(color=BORDER),
                    ft.Text("拟合质量", weight=ft.FontWeight.W_600),
                    self._key_value("RMSE", f"{metrics.rmse:.5g}"),
                    self._key_value("MAE", f"{metrics.mae:.5g}"),
                    self._key_value(
                        "R²", "—" if metrics.r_squared is None else f"{metrics.r_squared:.6f}"
                    ),
                ]
            )
        return controls

    @staticmethod
    def _key_value(key: str, value: str) -> ft.Control:
        return ft.Row(
            [
                ft.Text(
                    key,
                    size=12,
                    color=TEXT_MUTED,
                    width=92,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    tooltip=key,
                ),
                ft.Text(
                    value,
                    size=12,
                    weight=ft.FontWeight.W_500,
                    color=TEXT_PRIMARY,
                    text_align=ft.TextAlign.RIGHT,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    tooltip=value,
                    expand=True,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    @staticmethod
    def _platform_badge(label: str, icon: ft.IconData) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=16, color=ACCENT),
                    ft.Text(label, size=12, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                ],
                spacing=6,
                tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=11, vertical=7),
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, "#BEDDE2"),
            border_radius=99,
        )

    def _refresh_preview(self, spectrum: Spectrum | None) -> None:
        if spectrum is None:
            self.preview_host.content = self._empty_preview_state()
            self.preview_status.value = ""
            self.preview_previous.disabled = True
            self.preview_next.disabled = True
            return
        full_frame = spectrum.to_dataframe()
        total = len(full_frame)
        mode = self.preview_mode.value or "head"
        if mode == "tail":
            start = max(total - 30, 0)
            frame = full_frame.iloc[start:]
            self.preview_page = 0
            self.preview_status.value = f"第 {start + 1}–{total} 行，共 {total} 行"
            self.preview_previous.disabled = True
            self.preview_next.disabled = True
        elif mode == "all":
            page_count = max(1, (total + PREVIEW_PAGE_SIZE - 1) // PREVIEW_PAGE_SIZE)
            self.preview_page = min(max(self.preview_page, 0), page_count - 1)
            start = self.preview_page * PREVIEW_PAGE_SIZE
            stop = min(start + PREVIEW_PAGE_SIZE, total)
            frame = full_frame.iloc[start:stop]
            self.preview_status.value = (
                f"第 {start + 1}–{stop} 行，共 {total} 行 · "
                f"第 {self.preview_page + 1}/{page_count} 页"
            )
            self.preview_previous.disabled = self.preview_page == 0
            self.preview_next.disabled = self.preview_page >= page_count - 1
        else:
            start = 0
            frame = full_frame.head(30)
            stop = len(frame)
            self.preview_page = 0
            self.preview_status.value = f"第 1–{stop} 行，共 {total} 行"
            self.preview_previous.disabled = True
            self.preview_next.disabled = True

        row_numbers = [int(index) + 1 for index in frame.index]
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("#", size=11, weight=ft.FontWeight.W_600))]
            + [
                ft.DataColumn(
                    ft.Text(
                        str(column),
                        size=11,
                        weight=ft.FontWeight.W_600,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=str(column),
                    )
                )
                for column in frame.columns
            ],
            rows=[
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(row_number), size=10, color=TEXT_MUTED)),
                        *[
                            ft.DataCell(
                                ft.Text(
                                    self._format_cell(value),
                                    size=10,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    tooltip=self._format_cell(value),
                                )
                            )
                            for value in row
                        ],
                    ]
                )
                for row_number, row in zip(
                    row_numbers,
                    frame.itertuples(index=False, name=None),
                    strict=True,
                )
            ],
            column_spacing=24,
            horizontal_margin=12,
            data_row_min_height=30,
            data_row_max_height=30,
            heading_row_height=36,
            border=ft.Border.all(1, BORDER),
        )
        self.preview_host.content = ft.Column(
            [ft.Row([table], scroll=ft.ScrollMode.AUTO)],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _preview_mode_changed(self, event: ft.Event[Any]) -> None:
        self._sync_event_value(event)
        self.preview_page = 0
        self._refresh_preview(self._selected())
        self.page.update()

    def _preview_previous_page(self, _: ft.Event[Any]) -> None:
        if self.preview_page > 0:
            self.preview_page -= 1
        self._refresh_preview(self._selected())
        self.page.update()

    def _preview_next_page(self, _: ft.Event[Any]) -> None:
        self.preview_page += 1
        self._refresh_preview(self._selected())
        self.page.update()

    @staticmethod
    def _format_cell(value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return "—" if not np.isfinite(number) else f"{number:.6g}"

    async def _open_project(self, _: ft.Event[Any]) -> None:
        files = await ft.FilePicker().pick_files(
            dialog_title="打开 OpenXPSAnalyzer NetCDF 项目",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["nc", "nc4", "netcdf"],
            with_data=True,
        )
        if not files:
            return
        selected = files[0]
        if not selected.path and not selected.bytes:
            self._notify("无法取得所选 NetCDF 的路径或文件内容。", error=True)
            return
        try:
            if selected.path:
                self.project = load_project(selected.path)
            else:
                with tempfile.TemporaryDirectory(prefix="xps-project-") as folder:
                    temporary = Path(folder) / Path(selected.name).name
                    temporary.write_bytes(selected.bytes)
                    self.project = load_project(temporary)
                    self.project.file_path = None
        except XPSError as exc:
            self._notify(str(exc), error=True)
            return
        self.project_title.value = self.project.name
        self.selected_id = next(iter(self.project.spectra), None)
        self.preview_page = 0
        self._refresh_all()
        self._notify(f"已打开 {selected.name}。")

    async def _save_project(self, event: ft.Event[Any]) -> None:
        if not self.project.spectra:
            self._notify("项目中没有可保存的谱图。", error=True)
            return
        if self.page.web or self.project.file_path is None:
            await self._save_project_as(event)
            return
        try:
            path = save_project(self.project, self.project.file_path)
        except XPSError as exc:
            self._notify(str(exc), error=True)
            return
        self._notify(f"项目已保存：{path.name}")

    async def _save_project_as(self, _: ft.Event[Any]) -> None:
        if not self.project.spectra:
            self._notify("项目中没有可保存的谱图。", error=True)
            return
        file_name = f"{self._safe_filename(self.project.name)}.nc"
        if self.page.web:
            try:
                with tempfile.TemporaryDirectory(prefix="xps-save-") as folder:
                    temporary = Path(folder) / file_name
                    save_project(self.project, temporary)
                    payload = temporary.read_bytes()
                self.project.file_path = None
                await ft.FilePicker().save_file(file_name=file_name, src_bytes=payload)
            except XPSError as exc:
                self._notify(str(exc), error=True)
                return
            self._notify(f"项目下载已准备：{file_name}")
            return

        path = await ft.FilePicker().save_file(
            dialog_title="保存 OpenXPSAnalyzer 项目",
            file_name=file_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["nc"],
        )
        if not path:
            return
        try:
            saved = save_project(self.project, path)
        except XPSError as exc:
            self._notify(str(exc), error=True)
            return
        self._notify(f"项目已保存：{saved.name}")

    async def _export_image(self, _: ft.Event[Any]) -> None:
        spectrum = self._selected()
        if spectrum is None:
            self._notify("请先选择要导出的谱图。", error=True)
            return
        file_name = f"{self._safe_filename(spectrum.name)}.png"
        if self.page.web:
            try:
                payload = render_spectrum_image(
                    spectrum,
                    palette=self.palette.value or "sci_default",
                    component_mode=self.component_mode.value or "absolute",
                )
                await ft.FilePicker().save_file(file_name=file_name, src_bytes=payload)
            except Exception as exc:
                self._notify(f"导出图片失败：{exc}", error=True)
                return
            self._notify(f"图片下载已准备：{file_name}")
            return

        path = await ft.FilePicker().save_file(
            dialog_title="导出出版级谱图",
            file_name=file_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["png", "svg", "pdf", "jpg", "tif"],
        )
        if not path:
            return
        try:
            exported = export_static_figure(
                spectrum,
                path,
                palette=self.palette.value or "sci_default",
                component_mode=self.component_mode.value or "absolute",
            )
        except Exception as exc:
            self._notify(f"导出图片失败：{exc}", error=True)
            return
        self._notify(f"图片已导出：{exported.name}")

    async def _export_html(self, _: ft.Event[Any]) -> None:
        spectrum = self._selected()
        if spectrum is None:
            self._notify("请先选择要导出的谱图。", error=True)
            return
        file_name = f"{self._safe_filename(spectrum.name)}.html"
        if self.page.web:
            try:
                payload = render_interactive_html(
                    spectrum,
                    component_mode=self.component_mode.value or "absolute",
                )
                await ft.FilePicker().save_file(file_name=file_name, src_bytes=payload)
            except Exception as exc:
                self._notify(f"导出 HTML 失败：{exc}", error=True)
                return
            self._notify(f"交互式 HTML 下载已准备：{file_name}")
            return

        path = await ft.FilePicker().save_file(
            dialog_title="导出交互式 Plotly HTML",
            file_name=file_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["html"],
        )
        if not path:
            return
        try:
            exported = export_interactive_html(
                spectrum, path, component_mode=self.component_mode.value or "absolute"
            )
        except Exception as exc:
            self._notify(f"导出 HTML 失败：{exc}", error=True)
            return
        self._notify(f"交互式图已导出：{exported.name}")

    async def _export_csv(self, _: ft.Event[Any]) -> None:
        spectrum = self._selected()
        if spectrum is None:
            self._notify("请先选择要导出的谱图。", error=True)
            return
        file_name = f"{self._safe_filename(spectrum.name)}.csv"
        payload = spectrum.to_dataframe().to_csv(index=False).encode("utf-8-sig")
        if self.page.web:
            await ft.FilePicker().save_file(file_name=file_name, src_bytes=payload)
            self._notify(f"CSV 下载已准备：{file_name}")
            return
        path = await ft.FilePicker().save_file(
            dialog_title="导出谱图 CSV",
            file_name=file_name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["csv"],
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        try:
            target.write_bytes(payload)
        except OSError as exc:
            self._notify(f"导出 CSV 失败：{exc}", error=True)
            return
        self._notify(f"CSV 已导出：{target.name}")

    def _delete_selected(self, _: ft.Event[Any]) -> None:
        spectrum = self._selected()
        if spectrum is None:
            self._notify("请先选择要删除的谱图。", error=True)
            return

        def confirm(_: ft.Event[Any]) -> None:
            self.page.pop_dialog()
            self.project.remove(spectrum.spectrum_id)
            self.selected_id = next(iter(self.project.spectra), None)
            self._refresh_all()
            self._notify(f"已从项目移除 {spectrum.name}。")

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("移除谱图"),
                content=ft.Text(
                    f"确定从当前项目移除“{spectrum.name}”吗？原始 Excel 文件不会被删除。"
                ),
                actions=[
                    ft.TextButton("取消", on_click=self._close_dialog),
                    ft.Button("移除", bgcolor="#A13D3D", color=ft.Colors.WHITE, on_click=confirm),
                ],
            )
        )

    def _new_project(self, _: ft.Event[Any]) -> None:
        def reset(_: ft.Event[Any] | None = None) -> None:
            if _ is not None:
                self.page.pop_dialog()
            self.project = XPSProject()
            self.project_title.value = self.project.name
            self.selected_id = None
            self.preview_page = 0
            self.pending_excel = None
            self.pending_excel_data = None
            self.pending_excel_name = ""
            self._refresh_all()

        if self.project.dirty and self.project.spectra:
            self.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("新建项目"),
                    content=ft.Text("当前项目有未保存更改。确定放弃这些更改并新建项目吗？"),
                    actions=[
                        ft.TextButton("取消", on_click=self._close_dialog),
                        ft.Button(
                            "放弃并新建", bgcolor="#A13D3D", color=ft.Colors.WHITE, on_click=reset
                        ),
                    ],
                )
            )
        else:
            reset()

    def _notify(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                ft.Text(message, color=ft.Colors.WHITE),
                bgcolor="#A13D3D" if error else ACCENT,
                show_close_icon=True,
                close_icon_color=ft.Colors.WHITE,
                duration=4500,
            )
        )

    @staticmethod
    def _safe_filename(name: str) -> str:
        forbidden = '<>:"/\\|?*'
        cleaned = "".join("_" if character in forbidden else character for character in name)
        return cleaned.strip(" .") or "xps-spectrum"


# Backward-compatible import for integrations built against versions before 0.4.0.
XPSAnalyzerApp = OpenXPSAnalyzerApp


def main(page: ft.Page) -> None:
    """Application entry point used by ``src/main.py``."""

    OpenXPSAnalyzerApp(page).build()
