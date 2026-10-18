# OpenXPSAnalyzer

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![CI](https://github.com/AkiyamaSuguru/OpenXPSAnalyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/AkiyamaSuguru/OpenXPSAnalyzer/actions/workflows/ci.yml)

OpenXPSAnalyzer 是一个使用 Flet 构建的开源 Avantage XPS 数据后处理应用。它把 Excel 读取、xarray 数据管理、NetCDF 项目存储、悬浮交互图和出版级绘图整合在一个清晰的跨平台工作流中，可运行于网页、macOS 和 Windows。

项目的产品原则、数据契约、交互取舍和工程演进边界见 [《OpenXPSAnalyzer 软件设计哲学手册》](DESIGN_PHILOSOPHY.md)。

> OpenXPSAnalyzer 只处理 Avantage 已导出的数据，不替代数据采集、背景处理或峰拟合。项目与 Thermo Fisher Scientific 无隶属或官方合作关系；Avantage 及相关商标归其各自权利人所有。
> 开发者不对软件提供任何保证，使用时请自行核对数据，避免错误。

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
OpenXPSAnalyzer/
├── pyproject.toml              # uv 依赖、Flet 构建和工具配置
├── uv.lock                     # 可复现依赖锁
├── README.md
├── DESIGN_PHILOSOPHY.md        # 产品与技术设计哲学手册
├── CONTRIBUTING.md             # 贡献流程与开发约定
├── SECURITY.md                 # 安全问题报告方式
├── LICENSE                     # GNU AGPL v3 标准许可证正文
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

## 贡献

欢迎提交问题、功能建议和 Pull Request。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，并确保测试和静态检查通过。

## 许可说明

Copyright © 2026 Jie Ma and OpenXPSAnalyzer contributors.

**本项目只开源代码**。除代码以外的一切（作者的姓名与个人信息、设计与内容）均归作者所有，保留所有权利。

- **代码：[GNU AGPL-3.0](LICENSE)（`AGPL-3.0-only`），强 Copyleft 许可证**。包括 `src/` 中的应用与 Python 包、`tests/` 中的测试，以及 `pyproject.toml` 等项目文件。你可以使用、研究、修改与分享本软件，也可以收费提供副本或服务；分享修改后的版本，或将其作为网络服务（例如网页版应用）运行时，必须以同一许可证向获得它或通过网络使用它的所有人提供全部源代码，保留版权与许可声明，并注明所作的修改。本软件不提供任何担保。
- **保留：作者的姓名与个人信息**。Jie Ma（AkiyamaSuguru）以及有关作者的任何信息。
- **保留：设计**。作者徽标的一切形式，以及作者为本项目创作的标志、图标、启动画面和其他设计元素，无论以何种形式出现在何处，包括今后加入本仓库的。
- **保留：内容**。本说明、《软件设计哲学手册》及其他文档的文字，以及图片、数据等其他非代码内容。
- **名称**：修改后的版本不得以“OpenXPSAnalyzer”或作者的标识作为自己的名称，须另行命名以区别于原版；本项目不授予这些名称与标识的任何商标权利（AGPL 第 7 条第 (c)、(e) 项）。

AGPL 不涵盖的一切均保留所有权利：未经作者书面许可，**禁止以任何形式使用**，无论商业或非商业用途，包括文本与数据挖掘及 AI 训练。法律允许的合理使用（个人学习、研究，或注明出处的适当引用）无需许可，请遵守这一界限；按 AGPL 的要求保留代码中的版权与许可声明，同样无需许可。

如基于本代码发布修改版，请另行命名，并将所有保留内容替换为你自己的。如需许可，请通过[主页书信页](https://akiyamasuguru.github.io/?lang=zh#letter)上的地址或 GitHub（[@AkiyamaSuguru](https://github.com/AkiyamaSuguru)）联系作者。

### License

**Only the code is open source.** Everything else (the author's name and personal information, the design and the content) belongs to the author, with all rights reserved.

- **Code: [GNU AGPL-3.0](LICENSE) (`AGPL-3.0-only`), a strong copyleft license.** The application and Python package in `src/`, the tests in `tests/` and the project files such as `pyproject.toml`. You may use, study, change and share it, and you may charge for copies or services. If you share a changed version, or run one as a network service (the web version of the app, for example), you must offer its full source code under the same license to everyone who receives it or uses it over the network, keep the copyright and license notices, and mark your changes. It comes with no warranty.
- **Reserved: the author's name and personal information.** Jie Ma (AkiyamaSuguru) and any details about the author.
- **Reserved: design.** The author's emblem in every form, and the logo, icons, splash artwork and other design elements the author made for this project, in whatever form and wherever they appear, including any added to this repository later.
- **Reserved: content.** The text of this README, the design handbook and the other documents, and any other content that is not code, such as images and data.
- **Name.** A modified version must not use the name "OpenXPSAnalyzer" or the author's marks as its own name; give it a different name that sets it apart from the original. No trademark rights to these names and marks are granted (AGPL sections 7(c) and 7(e)).

Everything the AGPL does not cover is reserved: **no use in any form** without the author's written permission, commercial or not, including text and data mining and AI training. Fair use that the law allows (personal study, research, or a brief quotation that names its source) needs no permission; please keep within it. Keeping the copyright and license notices in the code, as the AGPL requires, needs none either.

If you publish a modified version, give it a different name and replace everything reserved with your own. To ask for permission, write to the author at the address on the letter page of the author's homepage (https://akiyamasuguru.github.io/#letter), or through GitHub ([@AkiyamaSuguru](https://github.com/AkiyamaSuguru)).
