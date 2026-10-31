# L1 v1：七类对象示例

以下是格式示例，不是已产生的研究证据。假设研究项目名为 demo，示例 Run 的输入/输出文件存在，研究者确实进行了所记录确认。
所有字段约束见 [formats.md](formats.md)。每段完整 Markdown 为有效样本，紧随其后的单项替换构成该类无效样本。
验证器须区分“结构有效”和“来源真实/结论正确”；本节不能证明后者。

## Claim — C-001.md

````markdown
---
schema_version: 1
id: C-001
status: proposed
created: "2026-10-31T09:00:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T09:00:00Z"}
type: problem
importance: core
tags: [workload]
validation_plan: "在固定输入 trace 下测量队列等待分布，保留脚本与原始样本。"
---
## Statement
在指定负载下，排队等待是尾延迟的主要来源。
````

无效变体：将 `type: problem` 替换为 `type: workload`。应报告 type 非法；workload 只能是 tag。

## Run — R-001.md

````markdown
---
schema_version: 1
id: R-001
status: completed
created: "2026-10-31T10:00:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T10:10:00Z"}
model: example-model
role: reviewer
input_files: [projects/demo/brief.md, projects/demo/claims/C-001.md]
output: projects/demo/runs/20261031T100000Z-review
session_id: null
duration_seconds: null
---
## Summary
人工调用独立 reviewer；原始回答保存在 output.md，未获得 session ID 与耗时。
````

无效变体：将 `status: completed` 替换为 `status: running`。应拒绝未结束却声称可归档的 Run；不能自行补 completed。

## Evidence — E-001.md

````markdown
---
schema_version: 1
id: E-001
status: valid
created: "2026-10-31T10:15:00Z"
source:
  kind: run
  ref: R-001
  path: projects/demo/runs/20261031T100000Z-review/output.md
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T10:20:00Z"}
target: C-001
direction: supports
kind: derivation
grade: model-asserted
provenance:
  - description: "reviewer 的推导，尚未独立验证。"
    path: projects/demo/runs/20261031T100000Z-review/output.md
---
## Material
reviewer 提供了排队影响的推导；这项材料不能单独支持 Claim。
````

无效变体：仅把 grade 改为 verified 而不提供 verification。应报告缺少验证方法、结果与 artifacts。

## Objection — O-001.md

````markdown
---
schema_version: 1
id: O-001
status: open
created: "2026-10-31T10:30:00Z"
source:
  kind: run
  ref: R-001
  path: projects/demo/runs/20261031T100000Z-review/output.md
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T10:35:00Z"}
target: C-001
severity: major
---
## Content
固定请求分布不足以代表分布漂移时的生产负载。

## Response

## Ruling
````

无效变体：将 target 改为 E-001。引用虽然存在，但 Objection 只能指向 Claim。

## Decision — D-001.md

````markdown
---
schema_version: 1
id: D-001
status: active
created: "2026-10-31T11:00:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T11:00:00Z"}
related: [C-001, O-001]
---
## Context
现有推导没有覆盖漂移负载。

## Choice
保留原 Claim 的 proposed 状态，先扩充实验计划。

## Rejected alternatives
暂不把 Claim 标为 supported。

## Rationale
没有 verified 支持证据，且仍有 open major Objection。
````

无效变体：将 related 改为 []。应报告缺少所裁决的对象引用。

## Exploration — X-001.md

````markdown
---
schema_version: 1
id: X-001
status: pending
created: "2026-10-31T11:10:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T11:10:00Z"}
lens: workload-drift
---
## Content
比较固定分布与渐变分布下的排队等待。
````

无效变体：仅将 status 改为 adopted 而不提供 adopted_as。应报告缺少形成的 Claim 引用。

## Spec — S-001.md

````markdown
---
schema_version: 1
id: S-001
status: todo
created: "2026-10-31T11:20:00Z"
source: {kind: human, actor: "Tianchi YU"}
confirmed_by: {actor: "Tianchi YU", at: "2026-10-31T11:20:00Z"}
target: C-001
evidence: []
---
## Requirements
实现可固定随机种子的请求回放器，记录逐请求排队与服务时间。

## Acceptance criteria
独立会话执行 python replay.py --seed 7 --trace drift.json；退出 0，输出逐请求 CSV。
校验脚本必须验证 CSV 请求数量与 trace 一致、时间均非负，并报告 p99 及运行环境。
这只是测量完整性的验收；是否支持 Claim 须由研究者依据实际结果裁决。
````

无效变体：将 target 改为 X-001。Spec 必须对应 Claim，不能把尚未采纳的探索当作验证目标。
