# 第 2 阶段人工验收（待执行）

程序和自动恢复测试通过，不等于此项通过。需要研究者选定真实系统研究想法，并在实际次日用全新会话恢复。
本清单不是已发生的实验记录；未填写的结果不得写成通过。研究工作台与 Toulmin 软件仓库分开。

## 首日

1. 确定真实想法、项目 slug 和独立研究目录；环境需要 Git、Python >=3.12，交接写入需要 POSIX 与支持链接/同步的文件系统。
2. 用 `toulmin init <研究目录> --project <slug>` 创建工作台。填写 PROJECT 的 Goal/Constraints 和 brief，保持 PROJECT 在 40 行以内。
3. 将真实 Claim 草稿放到该项目 runs 的子目录，写 source、type、importance 和 Statement，按 README 的 new 命令人工确认入库。
   记下 C-ID 和文件路径；命题仍是 proposed，不宣称已得到支持。
4. 开启全新独立 reviewer 会话，只提供研究 AGENTS、roles/reviewer.md、brief 和指定 Claims。
   不提供创作讨论或交接记录；模型由研究者手动调用。保留原始输出和真实可得的 model/role/session 信息，未知不猜测。
5. 将输出存到 runs/YYYYMMDDTHHMMSSZ-name/，归档 Run（明确 completed/failed）。研究者逐条审阅并确认需要纳入的 Objection，
   Objection.source 指向该 Run 和原始文件；不直接覆写 Claim，也不把评审输出当作裁决。
6. 运行 `toulmin status <slug> --root <研究目录>`。核对 open Objection、目标 Claim 与原始来源；如需裁决，由研究者另建 Decision。
7. 在 runs 子目录写会话摘要：session_id、recent_decisions、next_step，以及 Done、Decisions、Open questions。
   用 `handoff --input` 生成草稿，研究者审阅后以 --apply/--confirmed-by/--confirm 应用。
8. 审查研究仓库 diff 并提交，消息引用相关 C/O/R/D-ID。记录首日日期、会话 ID、对象/交接路径与提交。

## 实际次日

1. 开启全新交互会话，不提供首日讨论史；只按研究 AGENTS、PROJECT 和 last_handoff 指定的 sessions 文件入场。
2. 要求该会话用文件回答：项目目标是什么、哪些 major/fatal 反对意见未决、下一步做什么、对应原始评审在哪里。
3. 运行 status 核对其回答；必要时再按任务选择对象文件和原始输出，不能重新粘贴首日讨论帮助恢复。
4. 记录实际日期/新会话 ID、所读文件、回答与核对结果。若恢复丢失信息，记录失败与修复，不勾选通过。
5. 研究者明确判定通过/未通过；做一次阶段回顾：哪些反对意见改变方向、哪些步骤负担过大、交接丢失了什么。

## 记录模板

将真实记录保存在研究工作台 runs 的有日期子目录；在软件仓库 PROGRESS 记录路径与研究者结果。

| 项目 | 待填写内容 |
| --- | --- |
| 真实想法与研究目录 | 待研究者选择 |
| 首日日期 / session ID | 未执行；不可填写模拟值 |
| Claim / Run / Objection / Decision 路径 | 未创建 |
| 原始输出 / 已应用 handoff / Git 提交 | 未创建 |
| 次日日期 / 新 session ID / 入场文件 | 未执行 |
| 恢复核对：目标 / 未决异议 / 下一步 / 来源 | 未执行 |
| 研究者裁决与阶段回顾 | 待验收 |

四条命令和自动测试的完成不推进研究 PROJECT.stage，也不代表软件路线图第 2 阶段已经通过人工验收。
