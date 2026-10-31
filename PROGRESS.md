# Toulmin 开发进度

## 2026-10-31 — T4：只读状态与一致性诊断

- 状态：**Verified：T4 完成**；T5 尚未开始，第 2 阶段未完成。
- 用户授权：继续推进；本 session 实施 T4，记录实际验证并提交。
- L1 输出：core/project.py 校验项目章程，core/inspection.py 读取选定项目并检查文件布局、对象、直接引用和 brief 标记。
- L2 输出：protocols/status.py 返回结构化状态、条件和诊断；L3 新增 status 命令。没有新增依赖或改变 L1 对象字段/版本。
- 文档：README 补充用法；docs/protocols.md 和模板发布副本同步明确检查范围、unknown 与退出码；本文件和 TODO 更新。
- session ID：当前环境未提供，不编造。

### 验证结果

- **Verified**：status 专项 **40 passed**，全部 **258 passed**；Ruff 检查/格式检查与 mypy 通过（16 个源文件）。
- **Verified**：覆盖三种证据等级、支持/反对方向、证据失效，以及 fatal/major/minor 和非 open 异议。minor 与 supported 条件同时成立时分别展示，不替研究者选择状态。
- **Verified**：supported/accepted 失去支持时保留历史状态并提示人工复核；合法数据中的待裁决提示退出 0，不改阶段或对象。
- **Verified**：断引用、重复 ID、坏文件/非法状态、错误目录/文件名、缺失章程字段、非法阶段/超长章程和创建锁都明确报错，退出 1；条件变为 unknown，不宣称完整有效。
- **Verified**：brief 的本地/跨项目、非法/未闭合引用有文件及行号诊断；围栏和缩进代码示例不参与检查。未声称验证论断与证据的语义一致性。
- **Verified**：成功与错误路径前后完整目录、文件字节及 mtime 不变；不写缓存、索引、临时文件或 Git 元数据。严重度及数值 ID 排序确定，多项目互相隔离。
- **Verified**：新虚拟环境安装 wheel，在源码目录之外依次运行 init/new/status；正常路径成功、断引用路径退出 1 且条件 unknown，两条路径均保留字节和 mtime。
- 原有分层/无 CLI 可导入测试继续通过；没有调用网络、模型或独立验收 session。

### 交接

- 范围：检查选定项目的七类对象、PROJECT、brief 以及直接跨项目引用；不遍历其他项目发现入向证据/异议。错误时计数仅代表已校验部分，不是完整网络。
- L2 变更记录：明确待裁决提示与数据错误分开、不完整条件显示 unknown；只读命令不裁决 gates。L1 字段/版本未变，无数据迁移。
- 提交说明：`feat: complete T4 read-only status and consistency diagnostics`。
- 阻塞：none。
- 下一步：执行 T5，实现 handoff 草稿/确认应用、可恢复写入和全新进程恢复测试；真实研究想法的次日恢复仍须研究者试用验收。

## 2026-10-31 — T3：对象编解码、校验与确认入库

- 状态：**Verified：T3 完成**；T4–T5 尚未开始，第 2 阶段未完成。
- 用户授权：继续推进并保留进度；本 session 完成 T3，更新本文件与 TODO 后提交。
- L1 输出：core/documents.py、codec.py、schema.py、repository.py；数据结构/诊断、限定 YAML 子集、七类字段/正文约束、文件及直接引用校验、编号和排他发布。
- L2 输出：protocols/intake.py，要求人工确认，仅创建初始状态；L3 输出：new 命令及参数/错误呈现。核心与协议没有引入 CLI/模型依赖。
- 文档：README 给出可执行草稿和 new 用法；formats/protocols 明确草稿字段、确认参数、归档路径、锁与重放语义；发布模板副本已同步。
- session ID：当前环境未提供，不编造。

### 验证结果

- **Verified**：全套 **218 passed**；Ruff 检查/格式检查、mypy 通过。七类正式文档示例与逐类无效变体都进入实际测试。
- **Verified**：编码往返保留中文、代码围栏、正文分隔线；拒绝重复键、显式 tag、alias/anchor、merge、非有限值、错误类型、缺字段、未知字段/版本及非法状态条件，诊断含文件/行/字段。
- **Verified**：同/跨项目对象与来源 Run 可解析；不存在的项目/目标、错误引用类型、缺少验证记录/本地材料、原始输出不属于对应 Run 归档等情况会失败。
- **Verified**：未确认时不写正式对象；ID 按项目/类型递增，重复输入只分配新 ID，不覆盖旧对象。两个独立进程的并发创建不会占同一编号；遇锁时明确失败，可协调后重试。
- **Verified**：模拟 fsync/排他发布失败不会留下半个对象、临时文件或本次锁；目标已存在时保留原文件。逃逸路径及输入/目标目录 symlink 均被拒绝。
- **Verified**：无第三方包仍可导入 L1/L2；安装格式解析依赖但屏蔽全部 CLI 适配器时，可直接调用 L2 完成实际入库。文件 I/O 需要的 os/tempfile 等已加入架构允许列表，外部命令调用仍被检查拒绝。
- **Verified**：新虚拟环境安装 wheel 后，在源码目录外运行 init，依次创建 C-001、R-001、E-001、O-001、D-001、X-001、S-001 并重新读取及验证引用，项目阶段保持 explore；只使用测试样本，未调用模型。

### 交接

- L1 影响：实现既定 v1 字段和状态约束，明确 Run 归档基本 UTC 命名；未新增对象字段/版本，尚无实际旧研究数据需要迁移。L2 确认接口细化见 docs/protocols.md。
- 边界：new 校验候选对象的直接引用，不递归遍历循环网络；全项目一致性诊断属于 T4。格式/来源记录有效不代表研究结论真实，确认参数也不是身份认证。
- 强制终止进程可能遗留 `.toulmin-new.lock` 或临时文件；工具不会自动删锁，操作者须检查当前状态与活动写入 session 后再恢复。
- 提交说明：`feat: complete T3 object validation and confirmed intake`。
- 阻塞：none。
- 下一步：执行 T4，复用 Repository 和 schema 实现只读 status、证据/异议条件判断及 brief 引用诊断；不自动更改状态或阶段。

## 2026-10-31 — T2：工作台模板与 init

- 状态：**Verified：T2 完成**；T3–T5 尚未开始，第 2 阶段未完成。
- 用户授权：进行下一步研究和推进；本 session 实施 T2 并提交，未调用模型或建立真实研究项目。
- 输出：`src/toulmin/cli/initialize.py`、打包模板、init 命令、专项测试、README 用法及协议细化；L1/L2 的 Python 模块未改变。
- 模板：研究 AGENTS、CLAUDE 相对链接、Gemini 项目设置、L0 原则、L1/L2 发布文档、reviewer/scribe 契约、global 占位、项目章程/brief/八个对象与交接目录。
- session ID：当前环境未提供，不编造。

### 验证与实现边界

- **Verified**：init 专项 **34 passed**；全部测试 **93 passed**，包含原有核心/协议分层检查。Ruff 检查/格式检查与 mypy 通过。
- **Verified**：文件/链接/目录冲突在写入前拒绝；重复运行的文件字节及 mtime 不变；新项目保留旧项目修改，嵌套研究仓库不改变父 Git 元数据。
- **Verified**：故障注入覆盖发布文件、创建符号链接和复制 Git 元数据失败；仅清理本次创建内容。并发抢占目标文件时保留另一写入者的文件，不宣称成功。
- **Verified**：wheel 包含隐藏设置、空目录占位和完整框架文档。安装至新的虚拟环境，在源码目录之外成功运行 init、无变化重跑、新增项目与 Git status；新 Git 仓库没有初始提交。
- **Verified**：Gemini 的 `context.fileName` 已核对官方配置说明；原设计中的 `contextFileName` 拼写已修正，来源链接记在 docs/protocols.md。
- 文档发布副本通过测试与 docs 中原文比较，避免安装包依赖源码目录或契约漂移；README 说明同步要求。
- 适用条件：需要本地 Git，以及支持符号链接/硬链接的文件系统；全局模板修改后重跑 init 会报冲突而保留文件。强制结束进程后可能残留文件/Git 元数据，需检查再重试；常规错误回滚已测试。

### 交接

- 本轮没有新增研究结论或 gate 裁决；初始化命令只生成模板与本地 Git，不自动提交、不调用模型。
- 提交说明：`feat: complete T2 workbench templates and init`。
- 阻塞：none。
- 下一步：执行 T3，按 docs/formats.md 实现七类对象编解码、完整校验和 new，复用本轮模板建立测试项目。

## 2026-10-31 — T1：契约与可测试包

- 状态：**Verified：T1 完成**；T2–T5 尚未开始，第 2 阶段未完成。
- 用户授权：仅在本项目设置 Git 身份并继续推进；按 TODO Q1–Q9 的推荐方案执行。
- Git 身份：Tianchi YU / yu-tianchi@outlook.com，`git config --show-origin` 确认两项均来自 `.git/config`；未修改全局配置。
- 输出：正式 AGENTS、设计修订、docs/formats.md、docs/format-examples.md、docs/protocols.md、README、Python 包、uv.lock 和测试配置。
- 代码范围：L1 的规范 ID/项目引用，L2 的会话读取顺序，L3 的 help/version 入口；完整文件编解码与四条研究命令尚未实现。
- 隔离环境：uv 0.13.6、CPython 3.12.16 位于项目 .tools/，依赖在 .venv/，缓存位于 .uv-cache/；均已忽略，不替换系统 Python 或修改 shell 配置。
- session ID：当前环境未提供，不编造。

### 验证结果

- **Verified**：`uv sync --locked --dev --offline` 成功，`uv run --locked --offline pytest -q` 为 **59 passed**；Ruff 检查/格式检查通过，mypy 对 7 个源文件无错误；CLI --help/--version 可运行。
- **Verified**：测试覆盖非法/非规范 ID、路径型引用、会话读取顺序，以及 L1/L2 向上依赖检测；在 `python -I -S` 无第三方包且主动屏蔽 CLI 的子进程中导入并调用核心/协议成功。
- **Verified**：全新虚拟环境从锁文件离线同步成功；构建 sdist/wheel，改为安装 wheel 后在仓库外运行入口与全部 59 项测试成功，导入位置为该环境 site-packages。
- **Verified**：七类样本 YAML 头可解析，公共字段存在、类别完整、文档本地链接有效；此检查不等同于尚未实现的完整 schema/引用校验器。
- **Verified**：wheel 和 sdist 不含 .tools、.venv、.uv-cache 或 .git。构建时的缓存路径提示经归档内容检查排除；跨文件系统硬链接退化为复制，不影响安装结果。
- 首轮测试发现 CLI 帮助换行导致文本断言失败，已改为比较归一化空白；同时消除了 pytest 参数迭代器弃用提示。

### 交接

- 决定：Q1–Q9 按推荐方案采用；关键定义见 docs/formats.md 与 docs/protocols.md。L0 未变，L2 权限和阶段图已统一；没有旧研究数据需要迁移。
- 提交范围：规划文档、T1 代码/测试/锁文件，以及本任务明确修订的设计文档；不包含隔离工具、缓存或打包产物。提交说明为 `feat: complete T1 contracts and testable package`。
- 阻塞：none。
- 下一步：执行 T2，生成独立研究工作台/项目模板并实现 init，按 TODO 的重复初始化、冲突、路径及项目隔离要求验收。
- 阶段限制：真实研究项目的次日恢复与独立人工验收留在 T5，本 session 的自测不代替它们。

## 2026-10-31 — 第 2 阶段实施前规划

- 状态：规划草案已写；等待研究者确认，T1–T5 均未开始。
- 本轮任务：阅读 `docs/design.md`，起草仓库规则、技术建议、任务验收标准与开工前待决事项；不实现代码。
- 输出：`AGENTS.md`、`TODO.md`、本文件。设计原文未修改。
- session ID：当前环境未提供，不编造。

### 发现与验证

- **Verified**：已完整读取设计文档；第 13 节前四项要求骨架前决定。第 7 节图与 gate 表存在阶段映射差异，第 6 节角色目录写权限与 AI 输出先归档 runs 的规则需要统一。
- **Verified**：初始仓库没有提交；已有未跟踪文件 `docs/design.md`，本轮不擅自暂存该文件。
- **Verified**：`python3 --version` 返回 3.7.5；`command -v uv` 未找到命令。建议工具链尚不能运行。
- **Verified**：`git var GIT_AUTHOR_IDENT` 退出 128，报告 Author identity unknown；Git 姓名与邮箱未配置，不能完成本轮提交。
- **Guess（建议）**：Python >=3.12 + Typer + ruamel.yaml + pytest；Markdown 正文原样保存，L1 不依赖任何 CLI。理由与官方资料链接见 TODO.md。
- **Verified**：三份草案通过 UTF-8/LF、尾随空白、代码围栏及本地文档路径检查；TODO 恰有五项任务、每项含验收标准，Q1–Q10 齐全；`git diff --check --no-index /dev/null <文件>` 未报告格式问题。
- 未运行代码测试：仓库没有实现、测试或依赖配置；上述检查只证明规划文档的结构，不代表骨架可用。

### 决定与阻塞

- 用户已确定：本轮只规划，完成后等待确认。
- 尚未确认：TODO.md 的 Q1–Q9（类型、brief、证据等级、技术栈/MCP、知识库范围、生命周期、确认边界、ID、仓库与命令语义）。
- 提交阻塞：Q10，缺少研究者提供的 Git 作者姓名和邮箱；未设置虚构身份，也未修改全局配置。
- 尚无提交；文件留在工作区供审阅。未开始安装依赖、修改实现或研究状态。
- 下一步：研究者确认规划并提供 Git 作者身份；按确认结果修订文档、提交规划，再开始 T1。
