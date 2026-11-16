# 运行手册：真实数据 → DuckDB/Parquet → Qlib → TSP

**当前可使用的是入口，不是成功的实测记录。** 以下命令应由 Codex/操作者在**经授权且能访问真实数据源**的隔离环境执行。禁止把用户 Token、原始付费行情、本地数据库或含私密信息的日志提交到公开 Git。

## 0. 运行前

- 确认仓库分支/提交、Python 3.11、磁盘空间、现有数据库身份、Qlib 版本以及数据接口权限。现行 Qlib 可选依赖为 pyqlib 0.9.7；官方转换器取匹配标签 v0.9.7，不能直接假定本机其他版本兼容。
- 按本机秘密管理方式配置 TUSHARE_TOKEN；可用 TUSHARE_HTTP_URL 指向兼容 HTTPS 网关。**不得把含 Token 的 URL 用于 MCP 或日志**。
- TSP 原生界面与 Qlib 训练服务不在本仓库自动安装；第一次实验允许先完成 Qlib 研究，再联调 TSP。

## 1. 数据接口探测与小样本验证

~~~bash
python -m pip install -e '.[storage]'
aql status
aql check-source --start 20260101 --end 20261116
~~~

该探针目前只检查 **trade_cal**，不能代替 daily/adj_factor 真实权限与数据质量验证。正式导入前，先用受控小股票池及短日期窗口执行 ingest-market，核对 OHLC、手→股、千元→元、累计复权因子和应有交易日覆盖。停牌与未上市不能默认算作源缺漏；修订差异要保留证据。若源访问失败，记录接口名、权限/限频、时间窗与失败类别，禁止伪造成功。

## 2. 数据库采集

~~~bash
aql ingest-market \
  --db-path data/market.duckdb \
  --symbols-file configs/first-study-cohort.txt \
  --start 2019-01-02 --end 2026-10-30 \
  --pace-seconds 2
aql market-status --db-path data/market.duckdb
~~~

上述是**正式首轮固定样本**的配置，不应在没有小样本验证、权限和存储检查前盲目运行。重复/增量采集会生成新 capture_id。最新 COMPLETE 记录参与读操作，FAILED 记录不会被当作已收齐行情。

在单机方案中，采集前必须停止针对同一 DuckDB 文件的独立 TSP 读网关；不要指向 TSP/MRA 已有数据库。数据库不自动证明历史 PIT。

## 3. 冻结快照与官方 Qlib

~~~bash
python -m pip install -e '.[qlib]'
aql export-qlib-parquet \
  --db-path data/market.duckdb \
  --symbols-file configs/first-study-cohort.txt \
  --start 2019-01-02 --end 2026-10-30 \
  --output-dir data/first-study-parquet

git clone --depth 1 --branch v0.9.7 https://github.com/microsoft/qlib.git qlib-source
aql dump-qlib \
  --qlib-repo qlib-source \
  --snapshot-dir data/first-study-parquet \
  --provider-uri data/first-study-qlib

aql run-first-study \
  --provider-uri data/first-study-qlib \
  --manifest data/first-study-parquet/manifest.json \
  --config configs/first-study.json \
  --output-dir outputs/first-study

aql validate-artifact outputs/first-study/prediction-batch.json
~~~

现行 Parquet 快照与 Qlib 目录都拒绝覆盖已有路径；重复实验应使用新的身份/目录。快照 manifest、Qlib 转换器与研究代码版本须对应。**模型运行前需确认实际 Qlib 日期/证券索引顺序、训练标签成熟、复权链、样本交集；不能只因有 JSON 文件就宣称通过。** 首轮输出只是固定样本历史 RankIC，不是净交易收益。

## 4. 可选 TSP 历史页面联调

在停止数据库写入后启动独立的只读网关：

~~~bash
python -m ashare_quant_lab.tsp_gateway --db-path data/market.duckdb
python scripts/package_tsp_extension.py
~~~

将 integrations/tsp/tushare_aql.yaml 放进**实际运行中的 TSP** 数据源目录，重新加载并测试 daily/adj_factor，再触发小范围历史行情同步。确认 TSP 展示来自预期来源，检查 K线原始价与复权事件。然后经 TSP 的扩展导入页面安装生成的 ZIP 并重启。**只有真实研究结果已生成且经校验**，才运行：

~~~bash
aql publish-tsp \
  --study-dir outputs/first-study \
  --tsp-data-dir /path/to/real/tsp/data
~~~

TSP 原生数据仍由自身管理；不直接改 TSP 数据库。Docker 内的127.0.0.1不等于宿主机。若需要 LAN 监听，先做网络访问隔离；不要公开无认证读网关。TSP 的 Qlib 页面是历史研究展示，latest 文件不代表最新交易日信号。

## 5. GitHub Actions 与验收留痕

.github/workflows/real-qlib-study.yml 只允许人工触发，需要 Repository **Actions Secret** TUSHARE_TOKEN；**没有设置 Secret 或未运行，就不是一次真实研究**。工作流上传的是派生预测报告，公开仓库必须遵守源许可证和数据保密要求。GitHub Runner 生成的数据不会自动填充你本机 TSP。

每次真实执行保留：代码/依赖与配置身份、源采集范围、覆盖/缺口、版本与复权对账、模型/动量共用样本分母、成功与失败步骤、原生 Qlib 数据/运行检查、指标和未验证范围。若访问环境不通，交付实际失败诊断，不重命名合成测试为“真实跑通”。

相关资格条件见 [研究协议](RESEARCH-PROTOCOL.md)、[数据合同](STORE-CONTRACT.md) 和 [现行状态](ROADMAP.md)。
