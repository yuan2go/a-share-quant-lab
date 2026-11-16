# 独立 TSP 真实展示数据验收

首次研究完成后，用户追加授权启动网页、拉取数据并将数据/日志/缓存全部保存外置盘。此记录不改写首次研究的历史验收。

## 实例与启动

官方TSP v0.3.37独立checkout及环境在 `/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-FIRST-REAL-RESEARCH-01/20261116/diagnosis`，分别为 `tsp-source`、`tsp-venv`、`tsp-data`。未改上游内核或用户原有TSP/MRA目录。TSP自身管理展示Parquet，不写入AQL DuckDB。

运行证据根为 `/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-TSP-DATA-BOOTSTRAP-20261116`，简称BOOT。`runtime/logs`、`runtime/cache`、`runtime/tmp`与原生 `tsp-data/logs` 均在外置盘；源码依赖与构建产物也在外置盘。实际可写文件审计没有发现本项目写入内置盘；共享且早于本任务的全局uv/pip缓存未当作本项目文件迁移。

停止本任务旧实例后，前台启动：

```bash
TSP_BASE=/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-FIRST-REAL-RESEARCH-01/20261116/diagnosis
BOOT=/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-TSP-DATA-BOOTSTRAP-20261116
python3 scripts/run_tsp_external.py \
  --tsp-source "$TSP_BASE/tsp-source" --python "$TSP_BASE/tsp-venv/bin/python" \
  --data-dir "$TSP_BASE/tsp-data" --runtime-dir "$BOOT/runtime" \
  --credential-env "$TSP_BASE/../credentials.env" --port 3018
```

凭据文件0600，仅含TUSHARE_TOKEN/TUSHARE_HTTP_URL。启动器强制已挂载的外置卷，固定DATA_DIR、临时目录、XDG/uv/pip/npm/matplotlib/字节码缓存；挂载缺失拒绝启动。只绑定127.0.0.1，首页 `http://127.0.0.1:3018/`，历史研究页 `/aql-research`。冷启动等待预热，不重复启动同端口。

## 实际覆盖

| 数据 | 结果 |
| --- | --- |
| 源采集 | 484个日期/API任务；日线1,332,180行、累计因子1,335,706行，无失败 |
| TSP股票 | 当代5,579只；有效日线和enriched各1,328,772行，242日（2025-11-17至2026-11-16），证券日期唯一 |
| 排除 | 409条零成交/无效OHLC，全部匹配同日停牌事件；当代池涉及318条；原响应/清单保留 |
| 复权 | 4,849个单次事件、3,715只涉及变化，保留前窗口基准 |
| 环境 | 242天原生市场环境；长窗口首段存在预热限制 |
| 指数/ETF | 核心4指数968日线；1,766只ETF维表，10只种子ETF2,420日线，并非全ETF覆盖 |
| 财务 | 指标60,829、利润60,990、资负60,474、现金流60,767条整行报告期投影；各5,579只、2024Q1至2026Q3 |
| 股本 | 5,572条2026-11-16观测，公告时钟未知，不虚构公告日期 |
| 板块 | 395/395概念、775/777行业有当前成分；股票覆盖5,578/5,579只；主线6,718/6,489行 |

使用官方instrument/kline/index/financial服务、指标pipeline、ext_data写入器和市场环境/主线计算，未另建数据库、训练或回测引擎。空策略库、未配置AI、没有持仓/成交/触发记录保留真实状态，不造记录填页面。

## 修复与运行证据

- 初期429包含“请开启gzip”，曾误判为限流。协商gzip并有界解压后完整采集通过，旧失败日志保留。
- AQL库存股，TSP要求手：显示网关改为股/100，研究导出保持股。日线成交额千元转元；单股RT量股转手、额元保持。样本RT/EOD量额比1.00000016/1.00000001，符合源显示精度。
- 全市场日线流式、因子按日期维护状态，避免百万字典累积。零成交无效OHLC不伪造K线。
- 财务按实际公告/更新标记选整行修订，报告期唯一；合并累计报表不混母公司/单季。原始及修复前展示表保留私有备份。
- 18:00 CST前选择此前已完成交易日，修复跨午夜空股本。RT显式请求trade_time，缺时不发布，避免写成当日假行情。
- 展示成功响应缓存24小时，不是历史修订库；更换网关须用独立数据目录。研究历史身份由原AQL采集层承担。

BOOT中的 `download-state.json`、`full-native-publish.json`、`native-bootstrap.json`、`native-dimensions.json`、`native-verification.json`、`exclusion-summary.json`、`remaining-capability-probes.json`、`safe-permission-reasons.json`、`storage-audit.json` 及脚本/日志可复核。公开Git不含付费明细或令牌。

## 独立验收与阻断

真实验证 **3/7：daily、adj_factor、financial**。原先4/7仅按代码声明，不证明全市场RT可用；实测后撤下realtime声明。`stk_mins`、`rt_min`、`rt_min_daily`返回403；通配`rt_k`返回403并提示缺少批量权限，单股可查。五档无已验证授权接口，一档不当五档。用户确认没有额外授权，保留阻断，不枚举单股绕过批量限制。

免费源按[AKShare官方行情文档](https://akshare.akfamily.xyz/data/stock/stock_quote.html)及源码试取小样本：东财分钟、腾讯盘口/目录存在可取数据，新浪样本受TLS影响。盘中延迟、稳定性、全市场分钟和再分发许可均未证明，未登记为已接入。

浏览器实际核对市场看板广度/指数/榜单、财务报告期及指标、历史研究阴性结果。当前股票池/板块成分回看历史不具PIT资格；展示通过不证明预测改善、可成交、扣费盈利或实盘就绪。原冻结Qlib实验未重训、未更换样本或参数。

官方单位/权限参考：[TSP插件合同](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/plugin-development.md)、[日线](https://tushare.pro/document/2?doc_id=27)、[RT](https://tushare.pro/document/2?doc_id=372)、[实时分钟](https://tushare.pro/document/2?doc_id=374)、[日累计分钟](https://tushare.pro/document/2?doc_id=457)。
