# AGENTS.md

在本仓工作的硬约束。

## 允许 / 禁止

| 项 | 规则 |
|---|---|
| 允许 | `.md` / `.csv` / `.json` / `.yaml` / `.yml` / `.sql` / `.py`；配套 `.gitignore` / `.env.example` / `requirements.txt` / `.gitkeep` |
| ps1 | 只放行 `engine/scripts/scheduled_run.ps1` |
| 禁止 | office、图片、`.html`、压缩包、`.txt` / `.log`；明文口令 / 令牌 / 连接串 |
| 外置 | 全量 `problems.json` / `report.json`、历史 runs、全量 Hive 导出（见 `HANDOFF.md`） |
| 密钥 | 运行时用 `bdp-sso get-token` 或本机环境变量；`.env.example` 只放占位 |

## 写作

- 正文写中文全称；叶子码仅括号内，或查 `05-措辞与对照/11_节点中文对照表.md`。
- 不发明数字与口径；缺证据标【待核】。
- 外发行动句统一「现在复查」。
- 深度以 `02-穷尽下钻/10_下钻深度补全_穷尽分析方案.md` 为准；当前样张深度不等于目标深度。
- 不写元材料路径（对照文、审核包、过程目录）进仓内文档。

## 提交

未经用户明确同意，不做 git init / commit / push。
