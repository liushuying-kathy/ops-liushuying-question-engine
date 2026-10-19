# HANDOFF.md

| 项 | 内容 |
|---|---|
| 更新 | 2026-10-19（Asia/Shanghai） |
| 仓名 | `ops-liushuying-question-engine`（owner：liushuying-kathy；https://github.com/liushuying-kathy/ops-liushuying-question-engine） |
| 工程真源 | `【本机真源：问题引擎/】`；SQL：`【本机真源：sql/问题引擎/】` |

## 进度

| 面 | 状态 |
|---|---|
| 文档 `00`–`06` | 样张正文已复制进仓（只复制）；空壳与元材料已移出 |
| `engine/` | **已同步真源**（samples=render_v2、py 已同步真源（2026-10-19））；映射口径仓内约 80 引擎件 + samples/render_v2；全仓文件约 113 |
| git | 未 init / 未 commit / 未 push |

## Hive 导出（外置，不进仓）

| 表 | 路径 | 实测 | 验收 |
|---|---|---|---|
| A1 店日中级KPI（方案2） | `【外置数据：问题引擎/Hive_店日中级KPI_202509.csv，见 engine/data/SCHEMA.md】` | 含表头 3,270,131；数据行 3,270,130；631,424,061 字节；mtime 2026-10-19 17:44:00；52 片合计一致；最大片 93,042 行；门店×日期×中类重复 0 | 已通过 |
| A2 店日促销分解 | `【外置数据：问题引擎/Hive_店日促销分解_202509.csv，见 engine/data/SCHEMA.md】` | 含表头 89,173；24,244,169 字节；mtime 2026-10-19 16:20:46；未截断 | 已验通过 |
| A3 店品滞销探针 | `【外置数据：问题引擎/Hive_店品滞销探针_202509.csv，见 engine/data/SCHEMA.md】` | 含表头 84；9,875 字节；mtime 2026-10-19 16:21:19；未截断 | 已验通过 |

## 卡点

- 当前样张深度 ≠ 目标杜邦深度（见 `02-穷尽下钻/10_下钻深度补全_穷尽分析方案.md`）。
- 店长全链路、加盟主键、日更调度仍有【待核】/部分闭合项（见 `06-样张/03_当前状态与卡点.md`）。

## 下一步

1. 确认 owner；脚本内真源相对路径改为仓内路径【待核】；外部依赖 `grader_agent` / `sensors_common` / `workspace_config`【待核】。  
2. 渲染缺口任务出 `runs\2026-10-19_render_v2` 后替换 `engine/runs/samples/`。  
3. 用户同意后再 git init。

## 同步（2026-10-19）

- samples=render_v2、py 已同步真源（2026-10-19）
- 全仓文件数约 113（不含 .bak）
