---
name: 问题引擎-run
description: >-
  问题引擎权威跑批与验收。触发词：问题引擎跑批、ENGINE_RUN_DIR、经营发现引擎、
  run_batch、10-18样张、tree_bundle_grader、场景回归。工程真源工作区的取数→跑批→Grader→重渲染；仓内快照不等于一键复现。
---

# 问题引擎 · 跑批与验收（B5-4）

真北文档：仓内 `00-愿景与读序/门店经营诊断问题引擎_落地方案.md`（版本以文件头为准）；当前接手状态见根 `HANDOFF.md`。

## 标准流程（工程真源工作区；历史权威样张 `runs/2026-10-18`）

> 以下命令使用工程真源目录结构，不是仓内一键复现命令。仓内代码快照的路径适配、外部依赖和数据前置见 `engine/README.md`；未满足前置时不得伪报跑批或验收通过。

在工程工作区根目录 PowerShell：

```powershell
cd <工作区根目录>
$env:ENGINE_RUN_DIR="问题引擎/runs/2026-10-18"
$env:PYTHONPATH="tools\qdm_bdapp"

# 全量（含 bdapp + 神策）
python 问题引擎\scripts\run_batch.py

# 仅复用 data/问题引擎 CSV（改引擎不重取数）
$env:SKIP_SENSORS="1"
$env:SKIP_BDAPP="1"
python 问题引擎\scripts\run_batch.py
```

验收（须 `report.checks.passed`）：

```powershell
python 问题引擎\scripts\run_tree_bundle_grader.py   # 阈值 70%，产出 tree_bundle_grader_report.*
python 问题引擎\scripts\run_scenario_regression.py # S01–S12，会自动补跑树 Grader
```

仅改呈现、不重跑 L1：

```powershell
python 问题引擎\scripts\render_run_sample.py
```

## 关键产物

| 文件 | 用途 |
|------|------|
| `problems.json` / `report.json` | L1 真源 |
| `problem_trees.json` | L3 树真源 `problem_tree.v1` |
| `problems_ranked.json` | L2 含 `tree_path` |
| `问题清单_公司重要问题榜.md` 等 | 角色投影 |
| `tree_bundle_grader_report.json` | B5-2 确定性评分 |

## 取数注意

- 商分 ADS：`python -m qdm_bdapp`，SQL 在 `sql/问题引擎/`
- 日大类全月 SQL 可能超时 → 先用 `引擎_大分类日KPI_202509样周.sql`，或 `scripts/fetch_category_daily_202509.py` 分片合并
- 神策：`SKIP_SENSORS=1` 可跳过会员/水果段

## Agent 约束

- 判据在 `run_batch` / `engine/`，**不要用 LLM 填数**
- 缺数只写空缺状态行（如 `CAT_MID` / `统计月无分区`）
- 改阈值只动 `问题引擎/config/thresholds.yaml`，不改不等式顺序

## 锁版与评审线（2026-11-02 增补）

真北锚：当前评审基准 `QDM全真演示稿_中金咨询版_20261103.html`（SHA256 `44bea57bc7dd19ddaf459f4964e5d6fe3365081d92ecc68a358ccd4993d838ca`；历史《加深修订版》与上一版 `6e8610a2…` 存档不退化）。当前样张已随本更新包附带，历史 A 轮评审套件仍另行核验；引擎锚 canonical `146b738d…cdcd1`、gate_metrics `412ecd65…1035`、六计数 31,642 / 420 / 0 不变。

- **锁版锁锚不锁稿**：锁的是锚（hash）不是稿。措辞/数值级改动走修订轮（锚不动、hash 更新入册）；结构级改动走改版轮（重锁锚、旧版存档不退化）。
- **锁版硬门槛**：提交前后样张 SHA256 对账逐字符一致；禁词 grep 全 0；各页容器 parentElement=BODY，当前展示页 offsetHeight>0（切页白屏 = P0 结构缺陷）；数值多重集对基准稿 diff 为空；锁定注释（含 render-only 禁外发）在 </body> 前。
- **manifest 纪律**：manifest 自引用条目哈希数学上不可满足（不动点悖论），一律豁免（写 `excluded:self-referential` 或不列）；产物哈希以 manifest 与实际上传字节比对为准，回报正文内嵌哈希表允许转录滞后，以上传字节为准。
- **渲染规范**：comm 层按 comm 渲染规范 v5 / v5.1（R1–R17）施工：对比基准标注铁律、周日型/月末型必有回顾段（含零报告句）、角色下钻补齐（区总品类矩阵 / 运营经理督导组两级）、门店名=店名（店号）、归因厚度（一句话实质归因+五块展开+pp 对平）、执行项三要素、咨询体禁工程用语（引擎 issue / fail-closed / 红队等禁出正文，留【待结转】【待补】诚实标注）。规范全文在外置施工文档《QDM下一步关键提示词_20261031.md》，未随本仓分发时不得声称已核对全文。
- **字段三态解锁（轮次九同构）**：新字段一律 探针→体检→内部勾稽→三态裁决，禁止跳步、禁止以「100% 非空」直接判 confirmed；无独立参照最高只给「限定版 confirmed」；解禁权在业务评审，施工侧禁止自行放行进 enrich、禁止进任何诊断输出。
- **渲染验证口径**：playwright 查切页用 innerText / scrollHeight；未展示 tab 因 display:none 出现 offsetHeight=0 属正常，不是缺陷；切为当前展示页后仍无内容或高度为 0 才是缺陷。
- **当前样张验收记录**：七个角色页在桌面与手机视口均完成切页、非空内容、章节标题、脚本错误与横向溢出检查；风险门店 49＝37＋5＋7，二区与六区合计 27÷49＝55.1%；蔬菜与猪肉折让分项差额分别保留 74 元、33 元/店日【待核】，未手工调平。
- **仓库同步纪律**：样张锁版 HTML 入 `engine/demo/`（`.gitignore` 有例外行）；提交前后 SHA256 对账；push 用干净 worktree，禁止带未提交 engine 脏改的树。
