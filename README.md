# Toulmin

以文件保存研究状态、由研究者裁决的个人研究工作台。

当前已完成 T1–T2：格式/协议契约、分层包与工具链，以及独立研究工作台模板和 `init`。
`new`、`status`、`handoff` 在 T3–T5 实现；第 2 阶段尚未完成。

## 初始化研究工作台

```sh
uv run --locked toulmin init /path/to/research --project tail-latency
uv run --locked toulmin init /path/to/research --project second-project
```

需要本地 Git 和支持符号链接、硬链接的文件系统。命令创建研究 AGENTS、CLAUDE 链接、Gemini 配置、
framework/、roles/、global/ 以及项目目录，并建立一个尚无提交的独立 Git 仓库。
模型由人手动调用，按生成的 AGENTS 和 reviewer/scribe 角色契约工作。

相同内容再次初始化不写文件；任何目标文件内容冲突均报错并保留原文件。
新增项目不检查或重写其他项目的文件；全局模板仍接受相同的冲突检查。
目录符号链接会被拒绝，CLAUDE.md 必须是指向根目录 AGENTS.md 的相对链接。
常规写入失败会回滚本次新增内容；强制结束进程后需检查残留文件再重试。

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

发布模板的 framework/formats.md、format-examples.md、protocols.md 是 docs 中同名文件的发布副本，
修改契约时须同步；测试会检查它们一致，安装后的 CLI 不依赖源码目录。

代码依赖只向下：`cli`（L3）→ `protocols`（L2）→ `core`（L1），L3 可直接使用 L1。
核心与协议不依赖 Typer、具体模型工具或网络；研究工作台模板与软件开发仓库分开管理。
