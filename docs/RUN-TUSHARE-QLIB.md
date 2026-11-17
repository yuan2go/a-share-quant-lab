# 运行手册：真实数据 → DuckDB/Parquet → 官方 Qlib

原研究工作包只运行独立 Python 应用。其后用户追加授权启动独立 TSP 并加载真实展示数据，见[TSP本地验收](TSP-REAL-DATA-20261117.md)，不改写原有TSP/MRA实例。研究实际验收见 [真实研究记录](WP-AQL-FIRST-REAL-RESEARCH-01-RESULTS.md)。本地成功、合成原生联调和公开 CI 是分别记录的证据。

## 外置盘环境与一键运行

本轮所有数据、模型、缓存、临时文件与日志保存至 `/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-FIRST-REAL-RESEARCH-01/20261116`。Token 仅从已授权进程环境读取；私有凭据文件须留在外置盘、权限0600、Git之外。不要在命令行参数、URL或日志中输出秘密。

```bash
export AQL_DATA_ROOT=/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-FIRST-REAL-RESEARCH-01/20261116
mkdir -p "$AQL_DATA_ROOT/tmp" "$AQL_DATA_ROOT/cache" "$AQL_DATA_ROOT/logs"
export TMPDIR="$AQL_DATA_ROOT/tmp"
export PIP_CACHE_DIR="$AQL_DATA_ROOT/cache"
export MPLCONFIGDIR="$AQL_DATA_ROOT/cache/matplotlib"
python3 -m venv "$AQL_DATA_ROOT/venv"
"$AQL_DATA_ROOT/venv/bin/python" -m pip install -e '.[qlib]'
git clone --depth 1 --branch v0.9.7 https://github.com/microsoft/qlib.git "$AQL_DATA_ROOT/qlib-source"
# 先通过私有环境配置 TUSHARE_TOKEN；TUSHARE_HTTP_URL 可指定兼容 HTTPS 源。
"$AQL_DATA_ROOT/venv/bin/python" scripts/run_first_real_research.py \
  --data-root "$AQL_DATA_ROOT" --qlib-repo "$AQL_DATA_ROOT/qlib-source" \
  > "$AQL_DATA_ROOT/logs/real-run.log" 2>&1
```

环境与官方转换器已有时直接复用，禁止覆盖冻结目录。每次执行自动创建唯一 `runs/real-*`：三接口小窗口 → 重复采集一致性 → 冻结完整采集 → 源单位与复权昨收交叉核对 → Parquet → 官方 Binary 全字段/日历对账 → Alpha158/LightGBM → 共同分母 RankIC。`execution.json` 持续保存阶段结果；失败返回2，原始失败和未运行范围保留。成功也只是固定样本回顾性研究。

Qlib 固定 `pyqlib==0.9.7`，MLflow 限定2.x：实际联调发现3.18拒绝默认文件记录器。MLflow记录器和Qlib缓存均在研究输出旁，避免隐式写入系统盘或新建其他数据库。模型使用原冻结参数，禁止按结果调参。

## 单阶段诊断与复跑

```bash
"$AQL_DATA_ROOT/venv/bin/aql" check-source --start 20260901 --end 20260930
"$AQL_DATA_ROOT/venv/bin/aql" market-status --db-path "$AQL_RUN/market.duckdb"
"$AQL_DATA_ROOT/venv/bin/aql" export-qlib-parquet \
  --db-path "$AQL_RUN/market.duckdb" --symbols-file configs/first-study-cohort.txt \
  --start 2019-01-02 --end 2026-10-30 --capture-id CAPTURE_ID \
  --output-dir "$AQL_RUN/new-parquet"
"$AQL_DATA_ROOT/venv/bin/aql" dump-qlib --qlib-repo "$AQL_DATA_ROOT/qlib-source" \
  --snapshot-dir "$AQL_RUN/new-parquet" --provider-uri "$AQL_RUN/new-binary"
"$AQL_DATA_ROOT/venv/bin/aql" run-first-study --provider-uri "$AQL_RUN/new-binary" \
  --manifest "$AQL_RUN/new-parquet/manifest.json" --config configs/first-study.json \
  --output-dir "$AQL_RUN/new-study"
"$AQL_DATA_ROOT/venv/bin/aql" validate-artifact "$AQL_RUN/new-study/prediction-batch.json"
```

`AQL_RUN` 必须设置为本轮确切的外置盘运行目录，`CAPTURE_ID` 取执行记录。默认快照选择覆盖完整请求与证券集合的最新单个 COMPLETE capture；可以显式固定旧完整批次。部分增量不会再隐式拼接研究快照，TSP最新原始记录查询维持原职责。旧 manifest 缺完整开市日历或旧 Binary 缺全文件身份时需新建投影，不能补一个伪校验字段绕过。

`check-source` 同时检查 `trade_cal`、`daily`、`adj_factor`，返回各接口状态、覆盖及均价维度检查；缺凭据不请求，接口失败不回显上游正文。单位依据 [Tushare daily 官方合同](https://tushare.pro/document/2?doc_id=27)。完整采集另留原始响应哈希；除权昨收与累计因子交叉核对只证明源内部一致，不能替代公告/现金分红与历史公开可用时点。

独立 TSP 只读网关与同文件写入不能并行。主运行器仅创建本轮新库，不接触其他运行实例；使用其他路径前须核对身份与锁。

## 必要工程验证

```bash
"$AQL_DATA_ROOT/venv/bin/python" -m unittest discover -s tests -v
"$AQL_DATA_ROOT/venv/bin/python" scripts/native_qlib_smoke.py \
  --root "$AQL_DATA_ROOT/runs/new-synthetic-native" --qlib-repo "$AQL_DATA_ROOT/qlib-source"
```

后一命令明确使用确定性合成数据，仅检查真实官方 Qlib 软件链。输出被标注 `SYNTHETIC_ENGINEERING_ONLY`，不允许引用其 RankIC 作为市场研究。CI同样分别保留基础检查和原生合成联调。

## 产物与发布边界

私有运行目录包含原始响应、DuckDB、快照、Binary、模型、逐日指标、全量证券日期配对预测/标签、运行/依赖身份、失败诊断和重复实验结果。只向公开 Git提交脱敏汇总报告及代码；本轮不运行公开 Actions 行情任务，不上传授权边界未明确的派生明细，原研究阶段不部署TSP页面；追加授权的本地部署单独记录。手动工作流是另一个执行环境，其存在不代表本机或真实研究验收通过。

`validate-artifact` 只校验JSON结构。`prediction-batch.json` 是测试段末日的历史评分，假定T日18:00信息截止；不证明当时实际生成、数据按该时刻可得或评分可交易。买卖点、费用、订单和账户收益未实施。

## 方向概率研究：WP-AQL-DIRECTION-FORECAST-01

独立于旧排名配置。先读[冻结协议](RESEARCH-PROTOCOL.md#方向预测实验-wp-aql-direction-forecast-01)。沿用原30股授权环境，历史滚动复用旧冻结源；最新数据仅写新外置盘capture、Parquet和Binary，使用已有DuckDB，不引入数据库服务。不会重启TSP/MRA或部署定时任务。所有逐股概率/标签、模型与付费行情留私有盘。

```bash
export AQL_ENV=/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-FIRST-REAL-RESEARCH-01/20261116
export AQL_HISTORY="$AQL_ENV/runs/real-20261116T144032Z-791e7d7c"
export AQL_DIRECTION_ROOT=/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-DIRECTION-FORECAST-01/20261117
export AQL_RUN="$AQL_DIRECTION_ROOT/new-run-unique"
# TUSHARE_TOKEN / TUSHARE_HTTP_URL 从既有私有环境配置，不放命令参数。
mkdir -p "$AQL_DIRECTION_ROOT"
"$AQL_ENV/venv/bin/python" scripts/run_direction_research.py \
  --run-dir "$AQL_RUN" --qlib-repo "$AQL_ENV/qlib-source" \
  --historical-run "$AQL_HISTORY" --phase all \
  > "$AQL_DIRECTION_ROOT/new-run-unique.log" 2>&1
```

`--phase prepare` 只采集/审计/转换新的完整历史至最近已完成日；通过当前源的SSE/SZSE日历及18:00操作门槛确定信号日，未来交易日历只用来标记T+1/T+11日期。18:00不代表已经证明历史公开时钟。`--phase study` 只用历史冻结数据；`--phase latest` 使用已prepare的快照，按冻结日程训练最新月份并执行无标签推理及初次复盘。每阶段保留唯一execution文件；已有数据/预测/研究路径拒绝覆盖。重试应选新目录或以下独立CLI，不删除失败证据。

独立命令可复现历史、重训本月或**只加载模型推理**：

```bash
"$AQL_ENV/venv/bin/aql" run-direction-study \
  --provider-uri "$AQL_HISTORY/binary" --manifest "$AQL_HISTORY/parquet/manifest.json" \
  --config configs/direction-study.json --output-dir "$AQL_RUN/new-study"
"$AQL_ENV/venv/bin/aql" train-direction-latest \
  --provider-uri "$AQL_RUN/binary" --manifest "$AQL_RUN/parquet/manifest.json" \
  --output-dir "$AQL_RUN/new-latest-training"
# MODEL_RECORD_SHA256 取上条命令结果并保留为可信身份，不能来自未验证的陌生模型。
"$AQL_ENV/venv/bin/aql" infer-direction \
  --provider-uri "$AQL_RUN/binary" --manifest "$AQL_RUN/parquet/manifest.json" \
  --model-dir "$AQL_RUN/new-latest-training/model" \
  --model-record-sha256 "$MODEL_RECORD_SHA256" \
  --calendar-clock "$AQL_RUN/calendar-clock.json" --output "$AQL_RUN/new-prediction.json"
# 标签成熟后使用新的完整快照/Binary；不要修改原预测。
"$AQL_ENV/venv/bin/aql" review-direction \
  --prediction "$AQL_RUN/new-prediction.json" --provider-uri "$AQL_NEW_CAPTURE/binary" \
  --manifest "$AQL_NEW_CAPTURE/parquet/manifest.json" --output "$AQL_NEW_CAPTURE/review-unique.json"
```

calendar-clock过期（24小时）、新交易日尚未抓取或当前月模型未更新时，重新prepare到**新目录**；可对新快照infer，模型训练快照与推理快照分别记录。过期数据明确STALE；尚未结束的信号日明确BLOCKED；某股票回溯区间缺行情会使其无输出，不能填价。标签未成熟的review保留PENDING而非负例；成熟复盘新增原预测SHA、实际标签、原概率及单样本log loss/Brier，不覆盖之前review。

`study-report.json`、`daily-loss.parquet`、`observations.parquet`、逐月`models/*/model-record.json`提供公共评价范围、各自输出范围、逐年/逐证券/校准曲线和块区间。`prediction.json`是实际生成时点的新推理，不能用历史测试末日替代。原始/校准概率分列；TEMPORAL_PLATT_FITTED只证明独立时段拟合，不能称概率可靠性通过。公开CI只运行明确标记SYNTHETIC_ENGINEERING_ONLY的原生链，真实市场报告与其分开。
