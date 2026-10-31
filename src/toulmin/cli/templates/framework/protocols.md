# L2 骨架协议 v1

本文件细化设计第 6–8 节；修订原因是统一草稿权限、人工裁决和阶段映射。
CLI、Python 调用与手工编辑遵守同一协议；T1 提供读取顺序函数，T2 实现 init，T3 实现 new，T4 实现 status，handoff 在 T5 实现。

## 入场和退出

1. 读取工作台 AGENTS.md。
2. 读取 projects/<project>/PROJECT.md，再读取其 last_handoff 指向的 sessions 文件；新项目没有交接时明确说明。
3. 声明本 session 的单一任务、角色、输入和输出位置；只读取所需对象，不加载全项目讨论史。
4. 完成任务后把研究草稿/原始输出归档到 runs，记录模型、角色、输入、时间和可得的 session ID。
5. 起草交接；研究者审阅并确认后写 sessions、更新 PROJECT 最近决定/下一步/last_handoff，阶段须另有明确裁决。
6. 审查 diff 并提交，提交消息引用相关对象 ID；不自动 push。缺少身份或权限时保留内容并报告失败。

研究工作台的会话记录为 PROJECT + sessions；本软件开发仓库仍使用 PROGRESS + TODO，二者不可混用。

## 权限与确认

reviewer 只读取 brief、相关 claims 和角色契约，不读取创作讨论、其他 reviewer 输出，也不改写对象。
模型的只读会话通过终端输出研究草稿，由操作者保存至 runs；“只读”不要求模型自行写归档文件。
scribe/expander/development lead 的研究草稿均先进入 runs，表格中的 sessions/explorations/specs 是确认后的目的地。
实现者只改授权代码仓库；其测试报告先归档，不得自行修改验收条件或决定 passed。

new 的人工调用或明确确认参数记录 confirmed_by；来自模型的内容还必须指定可追溯 Run。
确认标记不是身份认证，模型不得自行填一个研究者姓名当成授权。仅仅读取草稿不代表确认。
对象初次创建与更改已有状态相区分：骨架不提供自动 rule，不自动采纳任何模型建议。
手工改变已有状态或项目阶段时，研究者创建 Decision 并关联被修改对象/PROJECT.recent_decisions。

## Claim 条件与现存状态

- has_open_objection：至少一个指向该 Claim 的 open Objection。
- eligible_for_supported：至少一个 valid + verified + supports Evidence，且无 open fatal/major Objection。
- open minor 可与 eligible_for_supported 同时为真。status 同时报告这些事实，不强选 challenged 或 supported。
- accepted 需要满足 supported 条件并有研究者 Decision；refuted 需要研究者 Decision 说明反证/已接受的异议。
- refutes Evidence 不计作支持，invalidated Evidence 不参与判定，model-asserted/intuition 不能单独满足支持条件。
- 已 accepted 的 Claim 失去证据后保留历史状态并报告不一致，不能自动降级。状态条件未满足属于待裁决诊断；语法、非法状态或断引用才是数据错误。

## 阶段与 gates

Explore → G1 → Critique → G2 → Brief final → G3 → Build → G4 → Accept → G5 → Done。
Spec 是 G3 前形成的产物，不单设阶段。G1–G5 的条件采用设计第 7 节表格。
G2 的暂缺证据用 Claim.validation_plan 记录最小验证实验，不使用不存在的 pending Claim 状态。
骨架 status 只显示事实与条件，不自动作出 gate 决定；handoff 不承担阶段推进。

## 四条命令的契约

所有项目命令接受 `--root <research-root>`，默认当前目录；project 显式提供，不扫描猜测项目。
成功退出 0，数据/文件/冲突错误退出 1，参数用法错误退出 2。建议或待裁决提示本身不使合法数据退出失败。
错误写 stderr，结果写 stdout；默认不请求网络、不调用模型、不提交 git。

| 命令 | 输入及输出 | 写入边界 |
| --- | --- | --- |
| init <root> --project <name> | 初始化模板及项目，建立 Git 仓库但不提交 | 创建缺少项；已有相同模板无变化，冲突拒绝；再次新增项目不重写全局文件 |
| new <type> <project> | 完整草稿与人工确认；返回新 ID/路径 | 只创建一个正式对象；AI 草稿必须先归档，目标已有则拒绝；无占位“有效对象” |
| status <project> | PROJECT、相关对象及 brief 显式引用；返回摘要与诊断 | 完全只读，包括不写缓存/索引、不更新 mtime |
| handoff <project> | 依据用户提供的完成内容生成可审阅草稿 | 默认只写 runs；--apply <draft> 确认后才写 sessions 与 PROJECT 的非裁决字段 |

init 在写入前检查本次全部目标；已有文件必须与对应模板相同，否则报冲突且不写入任何计划文件。
其他项目不在本次计划内，已有修改会保留；全局模板依旧检查冲突。已相同文件连 mtime 也不改变。
发布完整文件时采用排他创建，常规 I/O 失败回滚本次新增项；强制结束进程不承诺事务完成，重试前须检查残留。
目录 symlink 一律拒绝；唯一计划内链接是 CLAUDE.md → AGENTS.md。Git 只做本地 init，不提交或调用模型。
Gemini 配置采用 `context.fileName`，见[官方配置说明](https://geminicli.com/docs/reference/configuration/)。

T3 的 new 接口采用完整 Markdown 草稿文件（--input，路径相对 --root），需要 --confirm 与 --confirmed-by。
无确认、不完整或引用无效时保留原稿并失败；仅创建初始状态。Run 还必须显式给出 completed/failed，失败记录不会被丢弃。
遇到项目创建锁时等待操作者协调后重试，不自动移除锁；若进程被强制中止，须检查完整对象、临时文件和锁，再决定恢复。
此项是 L2 入库协议的实现细化，未改变人工裁决权或入场/退出顺序。

T4 的 status 只读取选定项目的 PROJECT、七类对象目录与 brief，并校验这些记录的直接引用。
引用外部项目只加载明确指向的对象，不扫描其余对象或发现其他项目的入向证据/异议；条件统计只使用选定项目中的有效记录。
open objections 按 fatal/major/minor、数值 ID 排序；Claims 按数值 ID 排序。本文的两个条件独立呈现，不据此改写 status 或 stage。
任何数据/布局/引用错误或创建锁使退出码为 1，并把条件标为 unknown；可读取的状态与部分计数仍展示，计数不代表完整网络。
合法数据的条件与已存状态不一致只是待裁决提示，退出 0。命令不创建缓存、索引、临时文件或修改 Git。
brief 检查字面 [[reference]] 标记，报告非法/缺失/未闭合引用；围栏及行首四格/制表符缩进代码示例跳过。
这只是引用完整性检查，不证明研究论断正确，也不检查自然语言与网络的语义一致性。
这次 L2 修订明确检查范围与不完整数据的报告方式，不改变数据字段、人工裁决权或 gates。

handoff 生成草稿时保存 PROJECT 的原始字节摘要。应用前若摘要不同，拒绝覆盖并要求重新基于当前文件起草。
应用必须保留 Goal/Constraints 等正文与其他 metadata；添加本次已有 Decision 引用、更新 next_step 和 last_handoff；禁止更新 stage。
中断后应能恢复完整应用或保留原文并明确报告；相同草稿重复应用无额外副作用。实现策略和故障注入测试在 T5 完成。

## 阶段验收

先通过命令集成测试，再由研究者使用真实研究想法完成写 Claim → 独立手动评审 → 确认 Objection → 交接 → 次日新会话恢复。
自动化只能模拟重启，不能替代真实两日试用或研究者最终验收。实施 session 的自测不算独立评审。
