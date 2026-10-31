# Toulmin

以文件保存研究状态、由研究者裁决的个人研究工作台。

当前已完成 T1–T4：格式/协议契约、分层包与工具链、研究工作台模板，以及 `init`、`new`、只读 `status`。
`handoff` 在 T5 实现；第 2 阶段尚未完成。

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

## 确认创建对象

先在工作台的项目 runs 子目录保存 Markdown 草稿，例如 `projects/tail-latency/runs/manual/claim.md`：

```markdown
---
source: {kind: human, actor: "Researcher"}
type: problem
importance: core
---
## Statement
在目标 trace 下，排队等待是尾延迟的主要来源。（示例：待验证的命题。）
```

```sh
uv run --locked toulmin new claim tail-latency --root /path/to/research \
  --input projects/tail-latency/runs/manual/claim.md \
  --confirmed-by "Researcher" --confirm
```

命令返回新文件路径；ID、创建时间和确认记录在入库时生成，不改写草稿。
支持 claim、evidence、objection、decision、exploration、spec、run；具体字段见 [格式说明](docs/formats.md)。
模型产物必须先归档原始输出并记录 Run，再以 source.ref/path 追溯来源；Run 结果须明确写 completed 或 failed。
本地文件路径均相对工作台根目录；跨项目对象引用写为 project/ID。
遇到 `.toulmin-new.lock` 时会失败而保留锁，确认没有运行中的写入 session 并检查残留后再恢复；工具不擅自移除其他 session 的锁。

## 查看状态与一致性问题

```sh
uv run --locked toulmin status tail-latency --root /path/to/research
```

显示已存阶段、下一步、Claim 状态、有效 verified 支持证据数量，以及按 fatal/major/minor 排序的 open objections。
是否存在 open objection 与是否满足 supported 条件分别显示，minor objection 可以与满足 supported 条件同时存在。
满足或失去条件只产生人工复核提示，已有状态和阶段始终保留。

检查范围为选定项目的七类对象、PROJECT、brief 显式引用及直接跨项目引用；不扫描其他项目来发现入向证据/异议，
也不推断 brief 自然语言与证据的语义一致性。围栏代码块和行首缩进四格/制表符的代码示例不检查引用。
损坏文件、断引用、无效 ID/状态、缺失目录或创建锁会退出 1，条件显示 unknown；此时计数仅表示已校验部分。
合法数据的待裁决提示退出 0；参数用法错误退出 2。命令不写对象、缓存、索引或 Git 元数据。

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
