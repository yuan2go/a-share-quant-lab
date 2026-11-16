# A-Share Quant Lab

**独立的 A 股选股与买卖点研究应用。** 官方 [Qlib](https://github.com/microsoft/qlib) 负责因子、机器学习及研究计算；[TSP](https://github.com/shy3130/tick-stock-panel) 是可选的独立 Web 工作台。本仓库管理 A 股数据与研究协议，不 Fork 两者，也不写入 [MRA](https://github.com/yuan2go/market-regime-alpha) 的运行实例。

**当前结论（2026-11-16）**：DuckDB/Parquet 在合成数据下通过 GitHub CI；真实 Tushare 网关、Qlib Binary/LightGBM 端到端、TSP 浏览器展示均**未实测通过**。没有证据支持稳定选股优势、有效买卖点或扣费盈利；不支持自动实盘交易。

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

真实数据需要环境变量 TUSHARE_TOKEN，绝不写进公开 Git。第一次真实实验**先核对数据和模型链路，再讨论选股优势**，不要直接据历史排名生成买卖建议。

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
