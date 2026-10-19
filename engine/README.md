# engine · 怎么跑

可跑代码与配置（2026-10-19 已从工程真源复制，见 `待确认后拷贝_路径映射.md`；真源 `【本机真源：问题引擎/】` 不受影响）。

## 准备

1. Python 环境：`pip install -r requirements.txt`（草案【待核】，见仓根）。
2. 本机 `.env`：按仓根 `.env.example` 填 `BDP_SSO_TOKEN`、`HIVE_MCP_URL` 等；勿提交真值。
3. 令牌：`bdp-sso get-token`，或设环境变量 `BDP_SSO_TOKEN`。
4. 全量数据外置，路径与验收数见 `data/SCHEMA.md`。

## 日更主路径

| 步 | 入口 | 作用 |
|---|---|---|
| 1 | `scripts/run_batch.py` | 取数 → 检测 → 排序 → 渲染，写 runs |
| 2 | `scripts/render_run_sample.py` | 从 run 抽样渲染清单 |
| 3 | `scripts/scheduled_run.ps1` | Windows 计划任务外壳（ps1 白名单唯一项） |

取数 / 对账：`scripts/recon/`（Hive 依赖 `HIVE_MCP_URL`；神策脚本依赖外部 `sensors_common` / `workspace_config`【待核】）。

脚本内路径仍按工程真源布局（如 `问题引擎/scripts/...`、`sql/问题引擎/...`）编写，在本仓直接运行前需改相对路径【待核】。

## 子目录

| 目录 | 内容 |
|---|---|
| `config/` | 判据 yaml 6 份 |
| `engine/` | 检测 / 树 / 渲染（含 `detectors/`） |
| `scripts/` · `scripts/recon/` | 主路径 5 · 取数对账 16（4 个 grader 脚本已移出至 99-待清理） |
| `sql/` · `sql/recon/` | 24 · 探针 3 |
| `demo/` | 经营诊断预警原型 md 3 份 |
| `runs/samples/` | 2026-10-18 角色清单（待 render_v2 后替换） |
| `data/` | `SCHEMA.md`；`fixtures/` 小样未建 |