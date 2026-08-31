# Contributing to OpenXPSAnalyzer

感谢你愿意改进 OpenXPSAnalyzer。项目欢迎错误报告、功能建议、文档改进、测试数据说明和代码贡献。

## 开始之前

- 先搜索现有 Issues，避免重复报告。
- 涉及新的科学计算、数据格式或界面流程时，建议先创建 Issue 讨论输入、输出、算法定义和兼容性。
- 请勿提交含有个人信息、实验室机密或无权公开的 Avantage 数据。若问题需要样本，请优先制作可公开的最小复现数据。
- 安全问题不要发布为公开 Issue，请按照 [SECURITY.md](SECURITY.md) 报告。

## 本地开发

项目要求 Python 3.11–3.12 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/AkiyamaSuguru/OpenXPSAnalyzer.git
cd OpenXPSAnalyzer
uv sync --all-groups
uv run flet run
```

网页模式：

```bash
uv run flet run --web
```

提交前运行：

```bash
uv run ruff check .
uv run pytest
```

## Pull Request 约定

1. 每个 PR 聚焦一个明确问题，并说明用户可见变化。
2. 任何科学计算变化必须写明公式、单位、有限值与边界处理，并添加自动测试。
3. 改变 NetCDF 数据结构前必须讨论 schema 兼容和迁移方案。
4. Web、macOS 和 Windows 行为有差异时，应在 PR 中说明验证范围。
5. 更新功能时同步更新 README、软件说明或设计哲学手册中的相关内容。
6. 不要提交生成物、虚拟环境、私有测试数据或密钥。

## 许可

提交贡献即表示你有权提供该贡献，并同意按照项目的 `AGPL-3.0-or-later` 许可证发布。你保留自己贡献的著作权。
