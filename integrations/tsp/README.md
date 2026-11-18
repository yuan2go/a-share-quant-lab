# TSP 接入边界

已按追加授权启动官方 TSP v0.3.37 独立实例，没有修改上游内核，没有改写用户原有 TSP/MRA 目录。实际数据、权限阻断和外置盘启动命令见[本地运行记录](../../docs/TSP-REAL-DATA-20261117.md)。

| 组件 | 作用 |
| --- | --- |
| `tushare_aql.yaml` | 可选只读AQL DuckDB网关，仅stock daily/adj_factor。TSP量手/额元，AQL库存股/元。写库与读网关不能并行。 |
| `tushare_source/` | 官方源码插件，连接授权HTTPS网关；只声明实际验证的daily/adj_factor/financial，TSP自行保存展示Parquet和24小时私有响应缓存。 |
| `extension.yaml`、`backend/`、`frontend/` | 展示已发布历史研究JSON，显示截止时钟与阴性结果，打开原生个股K线；无自动训练或交易。 |

`python scripts/package_tsp_source.py /外置盘路径/aql-tushare-source.zip` 生成不含行情/凭据的安装包，通过官方数据源设置安装。凭据只从进程环境/本机密钥读取，URL不得携带凭据。

单股票RT可查不等于TSP全市场实时可用：通配批量实测403（缺批量权限）；历史/实时分钟403；五档没有已验证授权接口。用户已确认保留受阻状态。免费来源仅试取样本，尚未接入此插件。

展示缓存不是历史PIT数据库。原Qlib阴性实验独立保留，页面有数据不证明预测改善或交易盈利。

上游协议：[源码插件](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/plugin-development.md)、[研究扩展](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/extension-packages.md)。

v0.2.0 的 Qlib 研究页增加私有方向预测、到期标签、损失及跨日期配对。先按[运行手册](../../docs/RUN-TUSHARE-QLIB.md#方向诊断配对复盘与页面)生成并发布方向摘要，再在独立验证宿主安装 ZIP。旧排名保留在同页折叠区。2026-11-18 验证使用独立端口 3038 与新 data_dir。
