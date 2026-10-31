# L1 文件契约 v1

状态：T1 冻结的骨架契约，依据 TODO.md Q1–Q9 的推荐方案及用户“继续推进”的授权。
本文件定义待实现的完整格式；T1 只实现 ID、引用和会话读取顺序，文件编解码与完整校验属于 T3。
英文机器字段是规范；Python 类与 CLI 均不能重新定义其含义。

## 文件和标识

- UTF-8、LF；对象文件第一行必须是 `---`，下一条独立 `---` 行结束 YAML 头。余下所有字节是 Markdown 正文，读取、写回不得重排正文。
- YAML 头为一个 mapping，只接受 string、bool、int、有限 float、null、list、string-keyed mapping。重复键、显式 tag、锚点/alias、merge key、多文档头均拒绝；不构造 Python 对象。
- 每个对象必有整数 `schema_version: 1`；bool 不算 int。未知版本报错，不进行自动迁移。未知字段拒绝；自定义数据只放 `extensions`（可选 mapping，键采用 `namespace.name`）。
- 日期/时间字段均为带引号的 RFC 3339 字符串，必须有时区；生成时使用 UTC `Z`。不依赖 YAML 自动日期转换。示例：`"2026-10-31T10:00:00Z"`。
- 项目名是小写 ASCII 字母/数字组成的片段，以单个 `-` 分隔，例如 `tail-latency`；不允许斜杠、点、空格或空片段。
- 七类对象在“项目 + 类型”内编号，从 1 开始，至少三位：`C-001`、`C-999`、`C-1000`。禁止 `C-1`、`C-000`、`C-0001` 等别名。
- 文件名必须等于 ID 加 `.md`，且位于类型对应目录。删除不作为正常操作，旧对象应保留，因此已用编号不回收。并发创建必须排他分配或明确冲突失败。
- 引用为 `C-001` 或 `other-project/C-001`；前者在当前项目解析，后者相对同一工作台根目录解析。绝对路径、`..` 与符号链接逃逸不允许。
- 机器记录的文件路径统一相对工作台根目录，以 `/` 分隔；引用外部来源使用单独的 URL 字段，不混为本地路径。
- 对象文件中不维护重复的 ID 索引。跨对象引用存在性、类型与来源文件存在性由仓库校验层检查，不由字符串解析器判断。

| kind（new 参数） | 前缀 / 目录 | 初始 status | 可读取的 status |
| --- | --- | --- | --- |
| claim | C / claims | proposed | proposed, challenged, supported, accepted, refuted |
| evidence | E / evidence | valid | valid, invalidated |
| objection | O / objections | open | open, answered, accepted, deferred |
| decision | D / decisions | active | active, superseded |
| exploration | X / explorations | pending | pending, adopted, dropped |
| spec | S / specs | todo | todo, in-progress, awaiting-acceptance, passed, failed |
| run | R / runs | 显式提供 completed 或 failed | completed, failed |

类型由 ID 前缀及目录确定，不在 metadata 再写 `kind`；Evidence 的 `kind` 字段专指证据种类。
Run 归档发生在人工模型会话结束后，不虚构 running/completed。原始输出放在 `runs/<UTC时间>-<局部名称>/`，Run 元数据为 `runs/R-001.md`。
草稿只用 Run 内局部标识，确认进入正式对象目录时才取得对象 ID。

## 公共字段与来源

所有对象必填：`schema_version`、`id`、`status`、`created`、`source`、`confirmed_by`。
所有非 Run 对象可选 `decisions`（Decision 引用列表，默认空）；所有对象可选 `extensions`。

`source` 为以下二选一，不接受混合或缺项：

- 人工原创/人工归档：`{kind: human, actor: "Tianchi YU"}`；actor 是非空署名。
- 取自模型 Run：`{kind: run, ref: R-001, path: "projects/demo/runs/20261031T100000Z-review/output.md"}`。
  ref 必须指向 Run，path 必须存在且属于该 Run.output 下；模型、角色与 session 通过 Run 追溯，不复制可漂移字段。

`confirmed_by` 为 `{actor: "Tianchi YU", at: "2026-10-31T11:00:00Z"}`，表示人工确认入库的记录，不是身份认证。
Run 自身由人工归档，source 必须是 human，不能自引用；model、role、session_id 由 Run 元数据记录。
所有字符串除明确允许空的章节和 null 字段外，必须在去除空白后非空；列表元素按规定类型逐项校验。

## 各类型字段与正文

正文使用下面规定的唯一二级标题。规定的必填章节需有非空内容；章节名区分大小写，不能重复。
正文中的 Claim statement、Objection content 等只保存一次，不再放 metadata；程序不根据自由文本自动认定“结论已证实”。

| 类型 | 额外必填 metadata | 可选或条件字段 | 必填正文章节 |
| --- | --- | --- | --- |
| Claim | `type`、`importance` | `tags: list[str]` 默认空；`validation_plan: str`；`decisions` | `Statement` |
| Evidence | `target: Claim引用`、`direction`、`kind`、`grade`、`provenance` | grade=verified 时必须有 `verification` | `Material`；invalidated 时另需 `Invalidation` |
| Objection | `target: Claim引用`、`severity` | `decisions` | `Content`；另保留 `Response`、`Ruling`，初始可空 |
| Decision | `related: list[对象引用]`（非空） | superseded 时需 `superseded_by: Decision引用` | `Context`、`Choice`、`Rejected alternatives`、`Rationale` |
| Exploration | `lens: str` | adopted 时需 `adopted_as: Claim引用` | `Content`；dropped 时另需 `Rationale` |
| Spec | `target: Claim引用` | `evidence: list[Evidence引用]` 默认空，passed 时非空 | `Requirements`、`Acceptance criteria` |
| Run | `model: str`、`role: str`、`input_files: list[str]`、`output: str`、`session_id: str或null`、`duration_seconds: 非负数或null` | input_files 可空；未知 session/耗时填 null，不猜测 | `Summary`；failed 时另需 `Failure` |

枚举：

- Claim.type：problem、magnitude、mechanism、novelty、assumption、deployability。workload/hardware 作为 tags，不新增类型。
- Claim.importance：core、secondary。G2 的 pending 用非空 `validation_plan` 表示，Claim.status 不增加 pending。
- Evidence.direction：supports、refutes；kind：measurement、literature、derivation、experiment、computation；grade：verified、model-asserted、intuition。
- Objection.severity：fatal、major、minor。
- Evidence.provenance：非空记录列表，每条含非空 `description`，并且有且仅有 `path` 或 `url`。path 必须存在；url 为 http/https URL，骨架不联网验证其内容。
- Evidence.verification：`{method: str, result: str, artifacts: list[str]}`；artifacts 非空、文件存在。格式完整只证明提供了验证记录，不证明科学结论正确，证据等级仍由研究者确认。

条件规则：answered Objection 的 Response 非空；accepted/deferred 的 Ruling 非空，accepted 还需 Decision 引用。
accepted/refuted Claim 必须关联至少一个 Decision；refuted 的决定应说明反证或接受的异议。
superseded Decision 必须保留旧正文；禁止自动删除失效证据或被否决的探索。

## PROJECT.md 与 brief

PROJECT 的 YAML 头必填：`schema_version: 1`、`project`、`stage`、`recent_decisions: list[Decision引用]`、`next_step: str`、`last_handoff: str或null`。
stage 枚举：explore、critique、brief-final、build、accept、done。模板初值 explore，recent_decisions=[]，last_handoff=null。
正文必填 `Goal`、`Constraints`，文件保持 40 行以内；不能为了缩短而丢弃手写内容，超出限制时报告而非截断。
`last_handoff` 是 sessions 下的文件名；只指向已确认应用的交接，不指向草稿。废弃项目保留原阶段并在 Decision 中记原因，不自行添加 abandoned 阶段。

brief 手写，章节包括 Problem、Why now、Magnitude、Closest prior work、Objections and responses、Kill criteria、Minimal validation experiment。
显式对象引用写为 `[[C-001]]` 或 `[[other-project/E-001]]`；只检查这些标记的语法、对象存在性，代码块内的标记不作为引用。
其他 Markdown 链接与自然语言不属于骨架一致性校验范围。

## 交接草稿与已应用记录

草稿不是第八类研究对象：保存在 runs 的独立归档目录，带格式版本、project、session_id（未知为 null）、created、
`base_project_sha256`、`recent_decisions`、`next_step`。正文为 Done、Decisions、Open questions、Next step 四节。
recent_decisions 只能引用已存在的研究者决定，空列表表示本次无新增决定；next_step 为应用时更新的唯一下一步文本，正文 Next step 指向该字段避免双份事实。
应用后 sessions 记录保存草稿路径/摘要、应用者与应用时间；PROJECT 的 last_handoff 指向它。
会话文件名以 UTC 时间加随机后缀避免碰撞；重复应用按草稿内容摘要识别，不能重复追加。
T5 负责定义并测试两文件更新的可恢复事务实现；格式不把“进程退出成功”等同于完整写入。

## 错误与兼容性

语法/字段错误必须包含文件路径、字段名，能定位时给出行号；不得跳过坏文件后宣称整个项目有效。
读文件允许所有合法现存状态；new 只创建初始状态（Run 必须明确提供结果）。状态变化由研究者裁决并记录 Decision。
不导入没有 schema_version 的旧草案；本仓库尚无已持久化的 v0 研究对象，因此本次无数据迁移脚本。未来版本变更需要影响评估与针对已有数据的迁移脚本。

七类有效示例与逐类无效变体见 [format-examples.md](format-examples.md)。
