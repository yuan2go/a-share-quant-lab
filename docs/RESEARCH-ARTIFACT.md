# 预测产物合同 V1：结构验证，不是投资资格

当前实现：src/ashare_quant_lab/contracts.py 与 artifacts.py；TSP 扩展消费由 tsp_publish.py 和 integrations/tsp 提供。

## 输入结构

| 字段 | V1 含义 |
| --- | --- |
| schema_version | 整数1 |
| run_id | 一次研究产物的唯一标识（由生产者提供） |
| created_at | **实际生成**时间，带时区的 ISO 8601 |
| signal_cutoff | 该历史信号所声称的**研究截止时点**，不证明当时实际发布 |
| market | CN-A |
| forecast_horizon_days | 未来交易日数量，非自然日 |
| model_id | 模型标识；V1仍只绑定部分配置与脚本；完整依赖/模型参数、model.txt SHA256、源代码摘要另见study-report.json |
| universe_id | 当前为固定研究样本哈希，**不是历史动态成分证明** |
| data_snapshot_id | 快照 manifest 的摘要身份；摘要不能代替内容/PIT 检验 |
| predictions | 唯一证券代码及有限浮点评分的数组，可为空；代码如600519.SH |

~~~json
{
  "schema_version": 1,
  "run_id": "example-not-a-real-run",
  "created_at": "2026-11-16T18:00:00+08:00",
  "signal_cutoff": "2026-09-30T18:00:00+08:00",
  "market": "CN-A",
  "forecast_horizon_days": 10,
  "model_id": "example-untrained",
  "universe_id": "example-fixed-cohort",
  "data_snapshot_id": "example-no-real-data",
  "predictions": []
}
~~~

示例只用于格式说明，**不是真实行情、模型预测或交易信号**。命令 aql validate-artifact 仅验证字段、时间格式、证券代码、非有限分数与去重等结构要求；不能证明数据在历史截止时可得，也不能证明模型真正运行、跨批次统计正确或盈利。

## 研究输出与发布限制

- 模型分数一般只是数值排序，不直接等于收益率、胜率、上涨概率或 BUY/SELL。
- 当前 study-report.json 保存共同有效日期/证券分母、年度RankIC、模型参数/版本与模型哈希；daily-rank-ic.json及paired-observations.parquet保留完整核对明细，均在外置盘。RankIC、样本数量、研究状态和经济净收益缺失应明确展示；研究程序未跑通时不要生成看似可信的评分。
- 当前 publish-tsp 会将历史结果放在 TSP 的 latest-* 路径，**latest 指最近发布的历史实验，不是最新交易日信号**；不得据此宣称实时荐股。
- 完整金融数据资格还需源时点/股票池版本、训练配置与代码版本、标签成熟度、模型/推理身份、成本及真实可成交路径。需在后续研究产物版本中落实，不能通过给 V1 增加文字来冒充已有能力。

失效结果（NO_DATA、FAILED、NOT_QUALIFIED、NO_TRADE）必须和真实无候选结果区分，保留原始失败记录。

## 方向预测产物（独立于排名batch v1）

`infer-direction`输出`kind=DIRECTION_PREDICTION, schema_version=1`。共同元数据包括实际generated_at、data_through、expected_latest_completed_session、T+1/T+11明确日期、严格上涨事件定义、model_id/model_record_sha256、训练分段与标签截止、训练/推理两个snapshot身份、snapshot_exported_at/source_capture_ids、calibration_status及RESEARCH_ONLY采用状态。逐股包含symbol、raw_probability、calibrated_probability、B0/B1概率及数据质量；不可输出时保留null与原因，不伪称0概率或震荡。

模型只加载原生LightGBM文本（binary objective、158列）、显式可信model-record SHA及相同官方特征/处理器定义，不加载任意pickle、不把排名batch转成概率。原预测独占新文件创建；成熟复盘`DIRECTION_MATURITY_REVIEW`为另一个新文件，绑定原预测SHA、原模型、原推理快照与复盘快照，附加成熟/缺失/PENDING标签，原概率不变。文件身份用于本地可复现，不是WORM、历史PIT或交易保证。
