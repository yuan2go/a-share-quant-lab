# A-Share Quant Lab

A股选股、买卖点与交易价值研究实验室。**独立 Python 应用依赖 Microsoft Qlib**，使用独立的 Tick Stock Panel (TSP) 作为可选的现成 Web 研究工作台。不 Fork Qlib 或 TSP，也不更改 market-regime-alpha (MRA)。

> 当前阶段（2026-11-16）：DuckDB/Parquet 数据链已经通过合成行情 GitHub CI；用户数据网关、实际 Qlib 模型训练、TSP 本机运行、样本外净收益均未验证。代码和测试通过不代表策略盈利。

## 当前数据与研究架构

~~~text
Tushare HTTPS (token only from local environment / Actions secret)
             |
             v
DuckDB local market store (data/market.duckdb)
    |  immutable COMPLETE/FAILED source captures, incremental revisions
    |---- TSP read-only daily/adj_factor adapter --> TSP native market pages
    |
    v
Frozen per-stock Parquet + SHA256 manifest
    |
    v
Official Qlib dump_bin.py --> Qlib Binary
    |
    v
Qlib Alpha158 + LightGBM vs simple momentum
    |
    v
Historical ranking diagnostics --> read-only TSP Qlib study extension
~~~

**DuckDB 是本研究项目的行情来源数据库，Parquet/Qlib Binary 是可重建的研究投影，TSP 使用自己的数据底座显示行情。** 不创建并行的 PostgreSQL 行情主库，不重写 Qlib 模型、因子或 TSP 的原生 K线。旧 CSV 中间导出代码已退出当前链路；历史仍由 Git 保存。

## 交付与验证边界

| 模块 | 已实现 | 本次已验证 |
| --- | --- | --- |
| Tushare HTTP | trade_cal / daily / adj_factor 接口和数据单位校验 | 合成数据；真实网关权限未知 |
| DuckDB | 原价、累计复权因子、交易日历、采集批次及最新完整版本查询 | CI 真实 DuckDB 读写与失败隔离 |
| Parquet | 压缩、版本化、SHA256、原始批次血缘 | CI 真实 Parquet 写入/读取 |
| Qlib | 使用官方 Parquet-to-Binary 转换器，Alpha158+LightGBM 研究入口 | 代码校验；未运行真实模型 |
| TSP | DuckDB 只读行情接口、研究页面扩展包 | 尚未在用户 TSP 实例中安装 |
| 交易 | 不支持真实自动下单 | 尚无可证明的净收益 |

## 安装入口

Python 3.11+，本地数据存储：

~~~bash
python -m pip install -e '.[storage]'
aql status
python -m unittest discover -s tests -v
~~~

完整 Qlib 实验使用隔离环境安装研究依赖：

~~~bash
python -m pip install -e '.[qlib]'
~~~

**私密数据令牌使用 TUSHARE_TOKEN 环境变量或 GitHub Actions Secret。** 不要提交到这个公开仓库。

使用说明：[Tushare/DuckDB/Parquet/Qlib/TSP 运行手册](docs/RUN-TUSHARE-QLIB.md) · [数据存储合同](docs/STORE-CONTRACT.md) · [现行架构](docs/ARCHITECTURE.md) · [研究协议](docs/RESEARCH-PROTOCOL.md) · [状态](docs/ROADMAP.md)。

首轮30只股票来自固定当代样本，不能宣称无幸存者偏差、严格 PIT 或真实交易有效。预测排名 RankIC 不等于盈利概率或费用后收益。允许 NO_TRADE 和 DO_NOT_ADOPT。

MIT License。
