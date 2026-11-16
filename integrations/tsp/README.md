# TSP 接入边界（当前非已部署系统）

本仓库**没有**复制、Fork、安装或启动 TSP。TSP v0.3.37 的公开扩展协议提供页面/后端接口，本仓库目前有对应扩展源码及打包脚本，但用户运行实例与浏览器链路尚未验证。

两种接入职责：

| 组件 | 路径 | 作用 |
| --- | --- | --- |
| 历史数据源 YAML | tushare_aql.yaml | TSP 调用本仓库只读 DuckDB 网关，按 TSP 格式提供 stock daily/adj_factor；不提供分钟、实时、ETF、指数、财务 |
| 独立研究扩展 | extension.yaml、backend/、frontend/ | 读取已发布历史研究 JSON，显示排名与截止时钟、调用 TSP 原生个股详情；无自动 BUY/SELL 或 Qlib 训练 |

首先在本项目完成真实数据采集，并停止 DuckDB 的独立写进程，才能启动 TSP 数据网关。TSP 页面同步后须核对原价、数据来源及因子事件；查询到某支股票不等于全市场数据合格。运行中的 TSP 与研究数据仍是两套独立存储，不直接写对方数据库。

命令、部署和安全细节仅维护在 [统一运行手册](../../docs/RUN-TUSHARE-QLIB.md)。首次真实Qlib实验已执行，整体未改善动量（见[结果](../../docs/WP-AQL-FIRST-REAL-RESEARCH-01-RESULTS.md)）。本轮未部署TSP；暂不因已有UI而推进买卖点或增加训练/回测系统。

上游扩展协议：[TSP v0.3.37 extension-packages.md](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/extension-packages.md)。
