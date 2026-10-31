# Toulmin

以文件保存研究状态、由研究者裁决的个人研究工作台。

当前实现范围为 T1：包与 CLI 入口、L1 ID/引用、L2 入场文件顺序，以及格式和协议契约。
`init`、`new`、`status`、`handoff` 在 T2–T5 实现，目前不可使用；第 2 阶段尚未完成。

## 开发

需要 Python >=3.12 和 uv；`.python-version` 将开发解释器固定到 3.12 系列。

```sh
uv sync --locked --dev
uv run --locked toulmin --help
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/toulmin
```

本机为避免修改系统解释器与 shell 配置，将 uv/Python 安装在被 git 忽略的 `.tools/`。
在本机 shell 中可先设置（仅影响当前 shell；其他机器已有 uv 时无需设置）：

```sh
export PATH="$PWD/.tools/bin:$PATH"
export UV_CACHE_DIR="$PWD/.uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
```

## 项目文档

- [设计](docs/design.md)、[L1 格式](docs/formats.md)、[七类示例](docs/format-examples.md)、[L2 协议](docs/protocols.md)。
- [仓库协作规则](AGENTS.md)、[实施任务](TODO.md)、[会话进度](PROGRESS.md)。

代码依赖只向下：`cli`（L3）→ `protocols`（L2）→ `core`（L1），L3 可直接使用 L1。
核心与协议不依赖 Typer、具体模型工具或网络；研究工作台模板与软件开发仓库分开管理。
