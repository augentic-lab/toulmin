# 第 2 阶段：骨架实施计划

依据：`docs/design.md` 第 3–8、10、12、13 节。2026-10-31 用户提供项目 Git 身份并要求继续推进，按下列推荐方案实施 T1。
本文件集中保存技术选型、验收标准和决定；设计修订及格式/协议细节分别保存在 docs/design.md、docs/formats.md、docs/protocols.md。

## 技术选型建议

选型已采用；适用性的理由是工程判断，实际工具链验证结果见 PROGRESS.md。

| 部分 | 推荐 | 理由与取舍 |
| --- | --- | --- |
| 语言 | Python >=3.12；开发先固定 3.12，uv 管理环境与锁文件 | 当前任务以文本、文件、协议和测试为主；以后可接实验脚本。比 Go/Rust 少一些开发负担，代价是需要 Python 运行环境；没有前端需求，不优先 TypeScript。版本是保守基线，不代表最新版。 |
| CLI | Typer，仅置于 L3 | 类型注解驱动参数定义，适合四个子命令；支持 CliRunner 测试。argparse 可减少依赖，但参数与帮助维护更繁琐；不同时叠加多个 CLI 框架。 |
| Markdown | 正文视为不透明文本；只识别文件起始处的 YAML front matter 边界 | 骨架不需要渲染或分析 Markdown AST，避免重排正文、代码块和手写说明。缺少结束分隔符应报错；正文内的 `---` 不得误判。以后需要分析 brief 链接时再评估 markdown-it-py。 |
| YAML | ruamel.yaml，明确采用安全的标准类型子集并拒绝重复键 | 提供重复键检查和保留注释的编辑能力；不允许任意对象构造或未知 YAML tag。比简单 PyYAML 配置多一些约束，但更适合人机共同编辑。正文完整保留；不承诺 YAML 头字节级往返不变。 |
| 数据模型 | 标准库 dataclasses + Enum + 显式校验 | 七类对象规模可控，保持 L1 与框架解耦；语法校验与跨对象语义校验分开。暂不增加 Pydantic。 |
| 测试 | pytest + tmp_path + Typer CliRunner | 可隔离真实仓库、测试错误路径和命令输出；补充安装后的子进程冒烟测试，防止只测到进程内调用。 |
| 开发检查 | Ruff、mypy、uv.lock | 格式、静态检查、类型与环境复现各自有明确职责；T1 才解析具体依赖版本。 |

已查阅的官方依据（2026-10-31；这些能力有文档依据，适合本项目仍属建议）：

- [Python 版本状态](https://devguide.python.org/versions/)；[uv 锁定与同步](https://docs.astral.sh/uv/concepts/projects/sync/)。
- [Typer 类型注解](https://typer.tiangolo.com/tutorial/)；[Typer 测试接口](https://typer.tiangolo.com/tutorial/testing/)。
- [ruamel.yaml 重复键规则](https://yaml.dev/doc/ruamel.yaml/api/)；[编辑保留能力及限制](https://yaml.dev/doc/ruamel.yaml/detail/)。
- [pytest 临时目录](https://docs.pytest.org/en/stable/how-to/tmp_path.html)。

环境事实：**Verified**：原默认 Python 为 3.7.5；T1 在 .tools/ 安装 uv 与 Python 3.12，并使用项目 .venv，不替换系统 Python、不修改全局 PATH。

## 开工决定记录

Q1–Q9 按用户“继续推进”的授权采用推荐方案；Q10 已按用户明确给出的姓名邮箱仅设置于本仓库。
Q1–Q4 对应第 13 节明确要求先解决的四项；其余是阅读设计时发现的骨架契约缺口。

| 编号 | 必须决定的问题 | 推荐方案 | 影响 |
| --- | --- | --- | --- |
| Q1 | Claim type 是否针对系统研究细化？ | 固定 problem、magnitude、mechanism、novelty、assumption、deployability 六类；workload/hardware 等作为 tags，避免不断扩张枚举。 | L1 schema、模板、G1 检查。 |
| Q2 | brief 从网络生成初稿，还是手写并检查一致性？ | 手写 brief；骨架只提供结构与显式对象引用检查，status 另行生成网络摘要。不从正文语义推断一致性，也不回写 brief。 | Markdown 处理、模板与 status 范围。 |
| Q3 | Evidence grade 是否细化？ | 保持 verified / model-asserted / intuition 三档；重复次数、方差、环境、复现方法记在 provenance/正文，重复测量不另设等级。verified 仍需可追溯的验证方法与结果。 | Evidence schema、supported 判定。 |
| Q4 | 语言与交互接口是否采用上表？本阶段是否提供 MCP？ | 采用 Python 技术栈；骨架仅 CLI + 可导入的 L1/L2，MCP 推迟。不预建空泛插件体系。 | 包布局、安装与测试。 |
| Q5 | 全球知识库现在实现多少？第 13 节第六项是否提前影响模板？ | 只创建 global/profile.md 与 papers、assumptions、calibration 占位目录；本阶段文献使用项目内 Evidence，知识库功能留到第 6 阶段。 | init 的输出范围。 |
| Q6 | 第 7 节阶段图与 gate 表如何统一？G2 的 pending 如何表达？ | 采用表格口径：Explore → Critique → Brief final → Build → Accept → Done，对应 G1–G5；Spec 是 Brief final 后、G3 前准备的产物，不单设阶段。G2 的待验证用独立验证计划字段表达，不新增 Claim 的 pending 状态。 | PROJECT.stage、模板、status、handoff。 |
| Q7 | 第 6 节角色权限与“所有 AI 输出先进 runs”冲突；第 4 节状态条件是否自动生效？ | 研究产物一律先写 runs，角色目录表示确认后的目的地；人工确认后 new 才创建正式对象。status 只报告条件与现存状态不一致，绝不自动升降级；阶段及已有状态由研究者修改并记录 Decision。 | new、status、权限与追溯。 |
| Q8 | 第 5 节递增 ID 与示例中带日期的 Run ID 如何统一？草稿何时获得正式 ID？ | 七类对象均在“项目 + 类型”内递增（C-001、R-001 等）；runs/R-001.md 保存 Run 元数据，原始输出置于带时间的子目录并被引用。草稿使用 Run 内局部标识，确认入库时分配正式 ID；跨项目引用使用 project/ID。 | 文件布局、来源引用、分配冲突测试。 |
| Q9 | 软件仓库与研究仓库是否分开？谁创建项目，handoff 是否直接改文件/提交？ | 本仓库维护软件与模板；init 在指定目录生成独立研究仓库，并以 --project 创建首个项目，后续可复用。handoff 默认生成草稿，人工确认后 --apply 写交接与 PROJECT 的非裁决字段；阶段不自动改，git commit 按退出协议人工/显式执行。 | 模板归属、四条命令契约、写入边界。 |
| Q10 | 规划及后续提交使用哪个 Git 姓名与邮箱？ | Tianchi YU / yu-tianchi@outlook.com；仅配置本仓库 user.name / user.email，已核对来源为 .git/config。 | 本轮与每个 session 的提交。 |

Q7 的实现限制：本地 CLI 的确认参数只是记录使用者声明，不能证明操作者必然是研究者；骨架依赖人工流程与 git 审查，不设计身份认证系统。

可后置问题：第 13 节的 synthesizer 轮换及校准统计格式留到第 3 阶段（Decision 基础来源/理由字段现在确定）；Zotero 留到第 6 阶段；配额策略留到自动编排前；外部 prompt 复用留到角色扩充时。骨架只提供最小手动 reviewer 与 scribe 契约，先自行编写。

## 五个实施任务

顺序：T1 → T2 → T3 → T4 → T5。T1 之后的命令与测试路径是拟议验收接口，尚不存在。
每项代码交付均须通过 AGENTS.md 中全套检查；任务完成不自动代表阶段通过研究者验收。

### T1 — 冻结骨架契约与建立可测试包

- [x] 输出：确认后的设计修订、L1 格式说明、L2 协议说明、AGENTS.md 正式版、Python 包与测试/检查配置。
- [x] 文档验收：Q1–Q9 均有决定与理由；明确七类对象必填字段、正文职责、字段类型、状态初值、非法状态处理、来源格式、schema_version、日期格式及引用规则。给每类对象至少一个有效/无效示例。
- [x] 数据边界验收：来源中的 model/role/run/session、人工 actor 与原始输出路径可追溯；Claim.statement 等正文内容有明确位置，不维护两份不一致副本。Run 元数据与原始输出相区分。
- [x] 工具链验收：干净环境运行 `uv sync --locked --dev` 成功；`uv run --locked toulmin --help` 退出 0；开发检查全部通过。
- [x] 分层验收：`uv run --locked pytest -q tests/unit/test_architecture.py` 在屏蔽 CLI/适配器导入的条件下仍能导入并调用 L1/L2；静态依赖检查能发现向上依赖及 L1 的外部命令调用。

T1 验证：59 项测试通过，Ruff/mypy 通过；全新环境安装 wheel 后再次通过 59 项测试。七类示例已检查 YAML 语法，完整 schema 校验器属于 T3，未声称其已实现。

### T2 — 仓库模板、项目模板与 init

- [ ] 输出：独立研究 AGENTS.md 模板、CLAUDE.md 链接、Gemini 指令文件配置、framework/、roles/、global/、tools/ 与项目布局。只生成配置，不调用任何模型工具。
- [ ] 行为验收：在临时目录执行 `toulmin init <root> --project demo`，第 5 节目录齐全；PROJECT 包含目标、阶段、约束、最近决定、下一步且模板不超过 40 行；brief 有第 1 节要求的各项结构；Git 可追踪空目录所用占位文件。
- [ ] 协议验收：生成的工作台指令包含入场顺序、退出步骤、人工确认边界与最小手动 reviewer/scribe 契约；不混入本软件仓库的 TODO/PROGRESS 开发流程。
- [ ] 写入验收：重复 init 不改变任何已有文件字节；冲突文件报错且不覆盖；路径逃逸及跨根目录符号链接报错。无法创建链接时给出明确失败，不留下声称成功的半成品。
- [ ] 项目验收：对同一 root 再指定新项目只添加该项目；其他项目内容不变。init 可建立 git 仓库，但不自动制造初始提交。
- [ ] 执行：`uv run --locked pytest -q tests/cli/test_init.py`。

### T3 — 七类对象读写、校验与 new

- [ ] 输出：文件格式编解码、引用/来源校验、ID 分配与 `toulmin new <type> <project>`；必填内容经提示或文件输入提供，不把占位符伪装为有效研究对象。
- [ ] 类型验收：参数化测试覆盖 Claim、Evidence、Objection、Decision、Exploration、Spec、Run；生成文件可重新读取，ID 前缀、必填字段、初始状态及目录符合 T1 契约。
- [ ] 解析验收：中文正文、代码块、正文中的 `---` 往返保留；重复 YAML 键、未知 tag、错误字段类型、缺失头结束符、未知格式版本均报错并显示文件与字段位置。
- [ ] 引用验收：支持同项目与跨项目引用；不存在的项目/目标、错误对象类型、不完整 provenance 均不生成正式对象；人工从 Run 导入 Objection 后能沿来源找到原始输出。
- [ ] 写入验收：不同项目/类型各自递增，已用 ID 不覆盖；两个并发创建不能占用同一 ID（可安全重试或明确失败）。写入失败不留下半个对象，输入路径不能逃逸工作台根目录。
- [ ] 确认验收：未确认的 AI 草稿留在 runs；确认入库记录 actor、来源与相关决定/确认记录，重放不覆盖原对象。
- [ ] 执行：`uv run --locked pytest -q tests/unit/test_objects.py tests/cli/test_new.py`。

### T4 — 只读 status 与条件一致性诊断

- [ ] 输出：`toulmin status <project>` 展示阶段、Claim 状态、按严重度排列的 open objections、下一步及数据问题；输出从当前文件生成。
- [ ] 判定验收：只有 model-asserted/intuition、仅有 refutes 证据、证据 invalidated、存在 open fatal/major 时均不能判为满足 supported；有效 verified supports 且无上述阻碍时才报告满足条件。
- [ ] 人工边界验收：满足条件只输出建议，不写回 supported/accepted，不自动推进 gate；accepted 之后证据失效时保留记录并显示不一致。open minor 与 supported 条件的交叉按 T1 确认规则报告，不暗自选择状态。
- [ ] 完整性验收：悬空引用、重复 ID、无法解析对象或无效现存状态给出可定位诊断和非零退出码，不能静默跳过并显示成功；合法数据的待裁决建议不当作解析失败。
- [ ] brief 验收：检查约定格式的显式对象引用并报告不存在的对象；不声称验证了手写论断与证据的语义一致性。
- [ ] 只读验收：运行前后目录清单、文件内容哈希及 mtime 不变；不生成缓存/索引。测试覆盖多个项目的隔离与确定性排序。
- [ ] 执行：`uv run --locked pytest -q tests/cli/test_status.py`。

### T5 — handoff、恢复流程与真实项目试用

- [ ] 输出：`toulmin handoff <project>`、人工应用步骤、入场/退出文档及手动试用记录。指定项目后命令无需猜测当前项目，不依赖网络或模型。
- [ ] 草稿验收：默认只在 runs 中形成可审阅草稿，含做了什么、决定/待决、开放问题、下一步、session ID；不能自动虚构讨论内容或未知 ID，未知项明确标注。
- [ ] 应用验收：确认后用 `--apply <draft>` 写 sessions 与 PROJECT 的最近决定/下一步，保留目标/约束/手写内容；不得改变阶段或对象状态。草稿生成后 PROJECT 被改动时拒绝覆盖；重复应用不产生重复交接，写入中断可恢复且无静默数据损失。
- [ ] 自动验收：`uv run --locked pytest -q tests/cli/test_handoff.py tests/integration/test_resume.py`；安装后的子进程测试依次执行 init → new claim → 归档手动评审输出 → 确认创建 objection → status → handoff → 全新进程恢复，仅靠落盘文件得到相同待办与来源链。
- [ ] 人工阶段验收：研究者选一个真实研究想法，当日写 Claim、在独立会话手动评审、确认纳入 Objection、交接并提交；**次日**用新的会话仅按入场协议恢复，正确说出目标、未决反对意见和下一步，并定位原始评审记录。
- [ ] 通过凭据：两日日期/session 信息、相关对象与交接路径、实际命令结果、研究者明确验收及一次阶段回顾。不得用模拟次日测试替代真实试用；没有研究者确认时任务保持“程序完成、阶段待验收”。

## 规划交付状态

- [x] 阅读设计并起草 AGENTS.md、技术建议、五项任务与待决清单。
- [x] 创建 PROGRESS.md 记录实际验证与环境阻塞。
- [x] 研究者要求继续推进，Q1–Q9 按推荐方案实施。
- [x] 提供 Git 作者身份（Q10），仅配置本项目。
- [x] 开始 T1；实现进度与验收结果见各任务及 PROGRESS.md。
