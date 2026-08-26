# XPS Analyzer

一个使用 Flet 构建的 Avantage XPS 数据分析应用。它把 Excel 读取、xarray 数据管理、NetCDF 项目存储、悬浮交互图和出版级绘图整合在一个清晰的跨平台工作流中，可运行于网页、macOS 和 Windows。

项目的产品原则、数据契约、交互取舍和工程演进边界见 [《XPS Analyzer 软件设计哲学手册》](DESIGN_PHILOSOPHY.md)。

## 主要功能

- 读取 Avantage 处理后的 `.xlsx`、`.xlsm` 和 `.xls` 数据，自动跳过前 15 行。
- 支持 Survey 原始谱、带拟合/背景的高分辨谱，以及任意数量的拟合分峰。
- 导入 Element 数据时可按 Excel 从左到右的顺序重命名分峰。
- 每条谱图由 `xarray.Dataset` 管理；整个项目以 `xarray.DataTree` 保存为 `.nc` 文件。
- 支持一次导入整个 Avantage 文件夹，文件夹名作为样品名、文件名 stem 作为谱图和 DataTree 节点名。
- 项目数据与分析结果分别收纳在左右抽屉中，主工作区可集中展示谱图和数据。
- 数据表可切换“前 30 行”“后 30 行”和“全部数据”；全部模式按 50 行分页，避免大文件阻塞界面。
- 内置结合能反向坐标、原始数据、拟合包络、背景和分峰填充绘图。
- 提供 Science、Nature、Okabe–Ito、Tableau、Soft、Viridis 色卡。
- 计算能量范围、最大峰位、RMSE、MAE、R²、分峰峰位/峰高/积分面积。
- 应用内提供 Flet 原生交互谱图，鼠标悬浮可查看结合能、强度和曲线名称；也可切换出版级静态预览。
- 多子图设置子窗口可从当前工作区自定义选择、排序谱图，设置行列布局、自动或手动编辑 `(a)`、`(b)` 等标签，并在导出前预览组合图。
- 可导出 600 dpi PNG/SVG/PDF/JPG/TIFF、当前数据 CSV 和自包含交互 HTML。
- 可导出自包含的 Plotly HTML，保留悬停提示和图例分组开关。

> 名称说明：NetCDF 目前的正式版本是 **NetCDF-4**，底层存储使用 HDF5；并不存在正式的“NetCDF5”格式。本项目使用 `h5netcdf` 写入 NetCDF-4/HDF5，满足 xarray 的完整读写与压缩需求。

## 运行

要求 Python 3.11–3.12 和 [uv](https://docs.astral.sh/uv/)。桌面模式能够直接访问文件夹，是文件夹导入的推荐方式。当前暂不把 Python 3.13 列入支持范围，以避免 macOS 隐藏虚拟环境中可编辑包路径未被加载的问题。

```bash
uv sync
uv run flet run
```

网页模式：

```bash
uv run flet run --web
```

网页端受浏览器安全限制不能直接读取本地目录，可使用“批量文件”一次选择多个 Excel 文件；保存的 NetCDF、图片、CSV、HTML 和多子图会通过浏览器下载。macOS 与 Windows 桌面端均支持目录选择和直接保存输出文件。

界面使用系统字体，绘图依次尝试 PingFang SC、Hiragino Sans GB、Microsoft YaHei、Noto Sans CJK SC、Arial Unicode MS 和 DejaVu Sans，避免中英文及数学符号被截断或显示为方框。

运行测试与静态检查：

```bash
uv run pytest
uv run ruff check .
```

## 导入约定

Survey 文件会读取有效数据的前两列，并重命名为：

```text
Binding Energy (eV), Intensity
```

Element 文件按以下位置解释列：

```text
第 1 列: Binding Energy (eV)
第 2 列: Intensity
第 3 列: Fitting Curve
中间列: 拟合分峰（可在导入窗口重命名）
最后列: Background
```

“分峰数据模式”有两种：

- `已包含背景`：Avantage 分峰列已经包含 Background，填充区域从背景到分峰曲线。
- `扣背景强度`：分峰列是相对强度，显示和峰位计算时自动加上 Background。

## 可复用应用接口

```python
from xps_app.readers import survey_reader, element_reader, read_avantage
from xps_app.models import Spectrum, XPSProject
from xps_app.storage import save_project, load_project
from xps_app.analysis import analyze_spectrum
from xps_app.plotting import Eplotter, plot_xps, plot_xps_single
from xps_app.multipanel import MultiPanelConfig, export_multi_panel_figure
```

这些接口与 Flet UI 解耦，可用于 notebook、批处理脚本或后续自动化分析。

## 项目结构

```text
XPSapp/
├── pyproject.toml              # uv 依赖、Flet 构建和工具配置
├── uv.lock                     # 可复现依赖锁
├── README.md
├── DESIGN_PHILOSOPHY.md        # 产品与技术设计哲学手册
├── LICENSE                     # Jay Mamun 专有软件许可
├── src/
│   ├── main.py                 # Flet 标准入口
│   ├── assets/                 # 打包资源目录
│   └── xps_app/
│       ├── app.py              # 页面、对话框和交互状态
│       ├── analysis.py         # 拟合质量与分峰指标
│       ├── constants.py        # 标准列名和文件模式
│       ├── exceptions.py       # 用户可读异常
│       ├── importers.py        # 文件夹批量导入与文件名映射
│       ├── models.py           # xarray Spectrum / XPSProject
│       ├── multipanel.py       # 自定义选择、布局、标签与多子图导出
│       ├── plotting.py         # Matplotlib / Plotly 绘图接口
│       ├── readers.py          # Avantage Excel 读取接口
│       ├── storage.py          # NetCDF-4/HDF5 持久化
│       └── ui_charts.py        # Flet 原生悬浮交互谱图
└── tests/
    ├── conftest.py
    ├── test_analysis_plotting.py
    ├── test_models_storage.py
    ├── test_multipanel.py
    ├── test_readers.py
    ├── test_ui_charts.py
    └── test_real_b1_sic.py
```

## NetCDF 数据模型

项目文件采用与 GMA 工作流一致的 `xarray.DataTree` 层级：

```text
/{样品文件夹名}/{Excel 文件名 stem}
```

例如批量导入 `B1_sic` 后会得到 `/B1_sic/C1s`、`/B1_sic/O1s`、`/B1_sic/survey` 等节点。每个叶节点都是独立的 `xarray.Dataset`，因此不同谱图可以拥有不同的数据点数和分峰数量，不需要填充数据。节点属性保留样品名、区域名、源文件、谱图类型、创建时间、单位、唯一 ID 与 schema 版本。

`project_to_dataset()` 仍提供带 `spectrum`、`point`、`component` 维度的扁平分析视图，便于跨谱图统计；实际项目持久化使用 DataTree。

## 文件夹导入与多子图接口

```python
from xps_app.importers import project_from_avantage_folder
from xps_app.storage import save_project

project = project_from_avantage_folder("/path/to/B1_sic")
save_project(project, "B1_sic.nc")

from xps_app.multipanel import MultiPanelConfig, export_multi_panel_figure

selected = [project.spectra[key] for key in list(project.spectra)[:4]]
config = MultiPanelConfig(rows=2, cols=2, dpi=600)
export_multi_panel_figure(
    selected,
    config,
    "B1_sic_multi_panel.png",
    labels=["(a)", "(b)", "(c)", "(d)"],
)
```

程序优先使用文件名规则识别 `survey`，并结合 Avantage 的“拟合包封/Background”描述行区分拟合谱。未手动传入化学键名称时，会从描述行生成 `C1s Scan A` 等分峰名；之后可在 Flet 界面中使用“分峰命名”按照 GMA 的化学态映射进行修改。应用内“多子图绘图”使用同一接口，并提供谱图勾选、顺序调整、行列容量检查、标签位置、色卡、图例、尺寸、DPI 和格式设置。

## 著作权

Copyright © 2026 Jay Mamun. All rights reserved.

本项目为专有软件，软件及源代码著作权归 Jay Mamun 所有。未经书面许可，不得复制、修改、分发、再授权、出售或基于本软件创建衍生作品。完整条款见 [LICENSE](LICENSE)。
