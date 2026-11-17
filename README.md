# A-Share Quant Lab

**独立的 A 股选股与买卖点研究应用。** 官方 [Qlib](https://github.com/microsoft/qlib) 负责因子、机器学习及研究计算；[TSP](https://github.com/shy3130/tick-stock-panel) 是可选的独立 Web 工作台。本仓库管理 A 股数据与研究协议，不 Fork 两者，也不写入 [MRA](https://github.com/yuan2go/market-regime-alpha) 的运行实例。

**当前研究结论**：已实际完成真实 Tushare → DuckDB → Parquet → 官方 Qlib Binary → Alpha158/LightGBM 的固定样本研究。665个配对日期、19,919个证券日期对中，模型平均 RankIC **-0.00115**，20日动量 **0.01136**，差值 **-0.01251**；整体未改善。详见[实际研究记录与验收边界](docs/WP-AQL-FIRST-REAL-RESEARCH-01-RESULTS.md)。暂不推进买卖点开发；严格 PIT、独立 OOS、扣费收益仍未证明。

**方向预测实验已完成**：WP-AQL-DIRECTION-FORECAST-01 独立研究T+1收盘至T+11收盘是否上涨的概率。33次月更、665日真实滚动中，校准模型log loss比B0/B1分别高0.00730/0.00760，**整体无增益，不采用**。截至2026-11-17的30股无标签推理及预测留存已运行，未来表现待成熟复盘。见[方向研究结果](docs/WP-AQL-DIRECTION-FORECAST-01-RESULTS.md)和[冻结协议](docs/RESEARCH-PROTOCOL.md#方向预测实验-wp-aql-direction-forecast-01)。

**本地工作台（2026-11-17）**：按追加授权已启动官方 TSP v0.3.37 独立实例，加载一年全市场日线、财务与板块快照。真实验证三类能力（日线、复权、财务），其余保留权限/覆盖阻断。数据、日志、临时文件、缓存均在外置盘，见[本地验收](docs/TSP-REAL-DATA-20261117.md)。页面可用不升级研究结论。

## 研究数据与输出

~~~text
Tushare HTTP (令牌仅在私有环境)
    ↓
DuckDB：采集批次、原始行情、累计复权因子、交易日历
    ├─ 只读历史行情 → TSP 自身数据与 K 线页面
    └─ 冻结 Parquet 快照及 SHA256 → Qlib 官方 Binary
                                              ↓
                                     Alpha158/LightGBM
                                     对照20日动量排序
                                              ↓
                                     历史 RankIC/预测产物
                                              ↓
                                     TSP 只读研究扩展页
~~~

DuckDB 是**本项目的本地行情来源记录**，Parquet 和 Qlib Binary 为可重建的研究投影；TSP 自行管理展示缓存。原来的直接 CSV 研究导出已退出现行链路。CSV 和数据库谁快尚无可比性能实测。

## 从这里开始

Python 3.11+；仅检查本地实现，不访问行情：

~~~bash
python -m pip install -e '.[storage]'
aql status
python -m unittest discover -s tests -v
~~~

真实数据需要环境变量 TUSHARE_TOKEN，绝不写进公开 Git。本轮数据、模型和日志全部保存在外置 DevSSD，路径及命令见运行手册。复跑实验**保持冻结样本和参数，先核对数据和模型链路**，不要直接据历史排名生成买卖建议。

## 文档职责与优先级

| 阅读顺序 | 文件 | 作用 |
| --- | --- | --- |
| 1 | [AGENTS.md](AGENTS.md) | Codex 权限、证据纪律和变更原则 |
| 2 | [项目状态与下一验收](docs/ROADMAP.md) | 已验证范围、唯一优先工作及受阻条件 |
| 3 | [研究协议](docs/RESEARCH-PROTOCOL.md) | 冻结的首轮选股比较、标签、评价和升级条件 |
| 4 | [数据合同](docs/STORE-CONTRACT.md) | DuckDB/Parquet/Qlib 血缘与已知数据限制 |
| 5 | [架构边界](docs/ARCHITECTURE.md) | Qlib、TSP、研究应用、MRA 的责任划分 |
| 按需 | [真实数据运行手册](docs/RUN-TUSHARE-QLIB.md) | 命令、权限、复现、故障判断 |
| 按需 | [研究产物合同](docs/RESEARCH-ARTIFACT.md) | 预测 JSON 的**结构**，非盈利证明 |
| 按需 | [TSP 集成说明](integrations/tsp/README.md) | 可选页面接入和部署边界 |

实现事实以当前代码及对应真实运行证据为准；文档说明不能自动升级为已实现/已通过。当前30只固定股票只是回顾性研究样本，并非历史动态股票池，不能宣称严格 PIT 或真实未见样本。

MIT License。
