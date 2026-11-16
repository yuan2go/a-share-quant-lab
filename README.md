# A-Share Quant Lab

面向 **A 股选股、买卖点研究及人工投资决策** 的可复现实验室。

**状态：仓库初始化（bootstrap）。** 本仓库尚未完成真实 A 股数据接入、模型训练、样本外收益验证、TSP 联调或实盘资格。这里的规则、模型与周期是研究假设，不是已证实的交易能力。

## 我们要回答的问题

1. 哪些股票在明确的未来交易周期内具有可重复的相对收益预测信息？
2. 入场/退出规则能否在**相同候选、交易约束与费用**下改善扣费净收益，而不仅改变胜率？
3. 何时应当持有、退出，或者 **不交易**？

首先比较简单规则与 Qlib 模型，随后分别检验买点与卖点是否有独立的经济贡献。

## 技术选择与边界

| 组件 | 责任 | 本仓库状态 |
| --- | --- | --- |
| [Microsoft Qlib](https://github.com/microsoft/qlib) | 因子、模型训练、预测、可复现实验与研究回测 | 计划通过 Python 依赖调用；已有本地 Qlib 安装不等于本仓库已集成 |
| 本仓库 | A 股数据时点验证、研究协议、选股与择时规则、预测产物和验证 | 已建立基础包、数据只读探针与预测产物校验；尚无真实模型 |
| [Tick Stock Panel (TSP)](https://github.com/shy3130/tick-stock-panel) | React/FastAPI 研究页面、股票详情、图表和可视化 | 计划通过独立扩展消费研究结果；尚未集成 |
| [market-regime-alpha](https://github.com/yuan2go/market-regime-alpha) | 现有独立研究证据、模拟执行与人工决策系统 | 本仓库暂不接入、不修改其数据库/运行实例 |

**本仓库不 Fork 或复制 Qlib/TSP 内核，不构建第二套通用量化平台或自动实盘下单系统。** 数据采集与训练发生在独立环境；TSP 扩展原则上只读取已经计算并完成身份检查的研究产物。

## 快速开始（目前仅基础功能）

推荐 Python 3.11。初始安装不自动下载行情、不安装重量级 ML 依赖，也不会访问券商或提交订单。

```bash
git clone https://github.com/yuan2go/a-share-quant-lab.git
cd a-share-quant-lab
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
python -m pip install -e .
aql --help
aql status
python -m unittest discover -s tests -v
```

需要在隔离的研究环境中安装官方 Qlib 时，先确认 Python/系统依赖与已安装版本，再选择：

```bash
python -m pip install -e '.[qlib]'
# 仅对本地已准备好的 Qlib 数据运行只读探针；不下载或修改数据
aql probe-qlib --provider-uri /path/to/qlib_data/cn_data --instrument SH600519 --start 2025-01-01 --end 2025-01-31
```

这里的 `SH600519` 是 **Qlib 内部代码示例**，不同于常见的 `600519.SH`；本仓库暂未实现全市场证券编码映射。探针仅查询本地 `$close` 数据是否可读，**不是预测或回测**。如本地 Qlib 与可选依赖版本不一致，应先测试版本兼容性，不要直接替换已有环境。

预测结果校验（输入必须来自实际实验，且按 [产物合同](docs/RESEARCH-ARTIFACT.md) 声明来源与时点）：

```bash
aql validate-artifact /path/to/your-prediction-batch.json
```

## 初始研究协议

- **市场**：沪深 A 股；股票池需按历史可交易状态动态重建，保留退市、停牌和历史 ST 等事实。
- **频率**：日线盘后分析；10 个交易日为首个预测目标，5/20 日作为对照；周频为初始组合调仓基线；每日检查风险。
- **选股**：简单动量基线，对比 Qlib Alpha158 + LightGBM。
- **买点**：下次可执行时点固定入场、趋势过滤、突破入场，分别检验。
- **卖点**：固定研究持有期、趋势失效、预测排名退化，分别检验。
- **验证**：信息可得时间、训练/测试隔离、退市与公司行为、交易成本、A 股交易规则、可成交性、样本外净收益与回撤。预测准确率不等于盈利能力。
- **权限**：研究与观察，不自动开仓，不直接使用真实账户。

详见 [研究协议](docs/RESEARCH-PROTOCOL.md)、[架构边界](docs/ARCHITECTURE.md)、[工程状态与后续顺序](docs/ROADMAP.md)。

## 当前已实现与尚未实现

**已实现**：Python 包与 CLI、可选 Qlib 数据只读探针、预测批次结构校验、必要的标准库单元测试和 CI。

**尚未实现/验证**：自动行情同步、股票池 PIT 证明、Alpha158/LightGBM 训练流水线、信号生成、买卖点策略、交易回测、自然前瞻、TSP 实际扩展页面和任何实盘接口。

本仓库的示例与测试 fixture 只用于结构与工程验证，绝不作为历史预测、胜率或真实交易证据。

## 维护原则

关键实验必须绑定源数据身份、模型/配置版本、信息截止时点与实际发布时点，保留失败和阴性结果。只有可复现的真实研究证据才能支持模型采用。开发前请阅读 [AGENTS.md](AGENTS.md)。

许可证：MIT，具体见 [LICENSE](LICENSE)。
