# AGENTS.md

在本仓工作的硬约束。

## 允许 / 禁止

| 项 | 规则 |
|---|---|
| 允许 | `.md` / `.csv` / `.json` / `.yaml` / `.yml` / `.sql` / `.py`；配套 `.gitignore` / `.env.example` / `requirements.txt` / `.gitkeep` |
| ps1 | 只放行 `engine/scripts/scheduled_run.ps1` |
| 禁止 | office、图片、压缩包、`.txt` / `.log`；明文口令、令牌、连接串 |
| HTML | 默认禁止；仅放行 `engine/demo/QDM全真演示稿_*.html` 锁版样张，且必须保留 RENDER-ONLY 注释并核对提交前后 SHA256 |
| 外置 | 全量 `problems.json` / `report.json`、历史 runs、`engine_output/`、`engine_runs/`、全量 Hive 导出、原始看板和截图 |
| 密钥 | 运行时用 `bdp-sso get-token` 或本机环境变量；`.env.example` 只放占位 |

## 写作

- 正文写中文全称；叶子码仅括号内，或查 `05-措辞与对照/11_节点中文对照表.md`。
- 不发明数字与口径；缺证据标【待核】，读不到的产物不得签为 PASS。
- 外发行动句统一「现在复查」。
- 深度以 `02-穷尽下钻/10_下钻深度补全_穷尽分析方案.md` 为准；当前样张深度不等于目标深度。
- 数值分解不等于业务因果；输出区分数值事实、诊断线索、已确认原因。
- 根 README 维护当前入口，逐日事实写入 `logs/`；不把本机路径、沙箱路径、预览内部标识或跨对话提示词写进产品说明。

## 修改边界

- 文档轮不得混入 `engine/` 代码或冻结配置变更。
- 改渲染不动计算口径，改引擎不动 schema 契约，除非任务明确授权。
- `thresholds.yaml`、`metric_tree.yaml` 及锁定锚变更必须单独 diff、复核并留痕。
- 发布与校验采用 fail-closed；校验器自身报错也视为失败，不得手工放行。

## 提交

未经用户明确同意，不做 git init / commit / push。提交前只暂存本轮白名单文件，核对暂存清单与敏感信息；已推送历史不得 amend 或重写。
