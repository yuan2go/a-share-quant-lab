# Tushare、TSP、Qlib 官方契约核对

核对日：2026-11-17。仓库基线：`b01f0c4486808595e1364e07c28ab6129c0cb380`。范围是官方文档/源码与本地静态调用链；没有发出授权行情请求、没有重新训练，没有改写历史研究证据。

## Tushare 调用清单与限额

下表数值是核对当日官方页面的单次响应上限。未列出数值或参数不等于服务器一定没有上限或不支持参数；不能把猜测升级为已验证契约。

| API | 本仓库调用 | 官方已明示的边界 | offset/limit 文档证据 |
| --- | --- | --- | --- |
| `fund_adj` | `Provider.get_adj_factors(asset_type='etf')`，单代码时间窗或全市场单日 | 2,000，可循环 | 输入表明确列出两个参数；[官方](https://tushare.pro/document/2?doc_id=199) |
| `fund_daily` | `iter_daily(asset_type='etf')`，始终逐代码时间窗 | 5,000，按代码/日期循环 | 该接口输入表未列；[官方](https://tushare.pro/document/2?doc_id=127) |
| `fina_indicator` | `get_financials('metrics')` 的 ≤100 个股票分支，逐代码、约1,100自然日起始范围 | 100，按日期多次请求；普通版只能单股票 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=79) |
| `fina_indicator_vip` | >100 个股票，逐报告期全市场 | 官方允许按季度获取全市场，参数与普通版一致；页面没有单独说明 VIP 数值上限 | **UNKNOWN**，不能直接套普通版100或默认6,000；[官方](https://tushare.pro/document/2?doc_id=79) |
| `daily` | `iter_daily` 股票>100时按日全市场，否则逐代码时间窗；独立研究采集另走 `query_partitioned` | 6,000，建议按交易日期取全市场 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=27) |
| `daily_basic` | 股票维表补充股本、financial/shares，同一最新交易日 | 6,000，按日循环 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=32) |
| `adj_factor` | stock复权；独立研究采集另走 `query_partitioned` | 支持单股全历史或单日全市场；页面未写数值上限 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=28) |
| `stock_basic` | stock维表，`list_status='L'` | 6,000，官方建议单次获取、保存本地 | 输入表未列，可按exchange/market拆分；[官方](https://tushare.pro/document/2?doc_id=25) |
| `fund_basic` | ETF维表，`market='E', status='L'` 后本地名称筛选 | 15,000 | 输入表未列，可按market/status/代码取；[官方](https://tushare.pro/document/2?doc_id=19) |
| `index_daily` | index日线，逐代码时间窗 | 支持代码、日期循环；页面未写数值上限 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=95) |
| `index_basic` | APIS允许，provider.py不调用 | 页面未写数值上限；按代码/市场/发布商筛选 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=94) |
| `rt_k` | 全市场通配符或显式证券实时请求，直接query；全市场权限已受阻 | 6,000，单独授权；不是历史分页链 | 输入表列ts_code，不能假定offset；[官方](https://tushare.pro/document/2?doc_id=372) |
| `trade_cal` | latest day、股票全市场日线/因子日期 | 日期范围；官方称沪深北交易日历一致；页面未写数值上限 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=26) |
| `income` / `income_vip` | income，≤100逐股票，>100逐报告期VIP | 普通版单股票；VIP按季度全市场；未单列上限 | 未列，**UNKNOWN**；[官方](https://tushare.pro/document/2?doc_id=33) |
| `balancesheet` / `balancesheet_vip` | balance_sheet，同上 | 同上 | 未列，**UNKNOWN**；[官方](https://tushare.pro/document/2?doc_id=36) |
| `cashflow` / `cashflow_vip` | cash_flow，同上 | 同上 | 未列，**UNKNOWN**；[官方](https://tushare.pro/document/2?doc_id=44) |
| `ths_index` | APIS允许，provider.py不调用；外部脚本须另审 | 5,000，官方明确一次取全、不要循环 | 不应机械分页；[官方](https://tushare.pro/document/2?doc_id=259) |
| `ths_daily` | APIS允许，provider.py不调用 | 3,000，按指数代码/日期循环 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=260) |
| `ths_member` | APIS允许，provider.py不调用 | 页面未写数值上限，仅最新成分，不是历史成员资格 | 输入表未列；[官方](https://tushare.pro/document/2?doc_id=261) |

`Client.pages()` 对所有API统一发 `limit=6000, offset=i*6000`，并以返回行数<6000判尾。**确定的代码风险**不止fund_adj：fund_daily满5000、fina_indicator满100、ths_daily满3000都会被当成尾页。是否真正丢数据还取决于具体请求有多少可用记录。fund_basic上限大于6000不代表安全：如果服务端忽略limit，可能返回超过请求的行数；当前固定步长与终止逻辑也没有覆盖这种契约偏差。

普通财务三表的start/end官方指**公告日**，fina_indicator页面写**报告期**；不得共用日期切分逻辑时默默改变筛选轴。VIP的period是报告期，不能用页面没有证明的全局6000封顶规则解释完整性。

### 通用 HTTP / SDK 能证明什么

官方 [`DataApi.query`](https://github.com/waditu/tushare/blob/master/tushare/pro/client.py) 把 `kwargs` 原样放到JSON `params`，返回 `fields/items`，没有自动分页、返回总数、服务端行数上限表或“短页永远代表末页”的保证。它能透传offset/limit，不能独立证明每个endpoint都执行它们。

官方成员在 [`waditu/tushare#1256`](https://github.com/waditu/tushare/issues/1256) 对`fina_mainbz_vip`明确解释offset和limit。这证明Tushare存在该分页机制；不是本仓库四类财务VIP当前页长的直接证明。缺少单endpoint证据时保留UNKNOWN，或采用endpoint已支持的代码/日期/报告期分区，不能断言不支持分页。

本库实际连接兼容HTTPS网关；官方文档不是该网关行为实测。已有真实缓存可只读审查请求参数、原始返回数、offset序列、范围及键覆盖。旧的limit=6000缓存不能删改冒充修复后证据；未获授权前不为补证发出新付费请求。

## TSP v0.3.37 契约

本项目引用的TSP是 [`shy3130/tick-stock-panel@v0.3.37`](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/docs/plugin-development.md)。其插件契约要求不复权日线，成交量手、成交额元，除权输出`symbol/trade_date/ex_factor`；插件自行承担数据转换。[Provider契约](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/backend/app/data_providers/base.py)要求取数失败明确上报，不能伪装成功空数据。

上游 [`kline_sync`](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/backend/app/services/kline_sync.py) 优先消费`iter_daily`；provider取数异常应使本轮staging放弃，不能先截断后正常结束。保留空批次进度与取消回调的异常传播；不能在捕获分页错误后返回空帧而使上游以为同步成功。

本地`events()`将累计因子相邻值之比转为单次事件因子，并且首条只有建基线的作用。由此可推导出另一个**历史预热风险**：`get_adj_factors`的≤100分支只回溯60自然日；>100分支只读start前最后一个全市场交易日。若某代码在该基线日缺记录、长停牌/新上市或网关缺行，首个区间内值会成为基线，start当天/首个有效日的变动可能被漏掉。60自然日不是官方或TSP保证。修复需按证券确认前驱累计因子，或确认证券确无更早历史；缺证据明确失败/缺口，不能把首值当1，也不能凭空生成事件。

## Qlib v0.9.7 的历史和索引

本库锁定`pyqlib==0.9.7`。官方 [`CalendarProvider`和`LocalExpressionProvider`](https://github.com/microsoft/qlib/blob/v0.9.7/qlib/data/data.py) 把查询时间映射到provider交易日历索引，并依表达式`get_extended_window_size()`向左/右扩展底层读取，算完再裁回请求区间。因此请求train开始时的`$close/Ref($close,20)-1`可以读取provider已有的训练前20个交易日。

官方 [`Ref`](https://github.com/microsoft/qlib/blob/v0.9.7/qlib/data/ops.py) 的正N是过去N期、负N是未来期，通过series.shift(N)计算并扩展读取窗口。应在完整provider交易日历上保留缺值做shift；不是每只证券dropna后数20条，也不是20自然日。缺行情时不能forward-fill成有效动量。

本地 `_verify_targets`从`all_dates[0]`读取close，而all_dates在run中由train起点构造；独立wide.shift(20)丢掉前驱历史，与Qlib的读取边界不同，足以误拒训练前有数据的合法快照。建议保留研究段日历负责切分/成熟度，在核对函数另取provider完整日历或train前20个交易日到末尾的审计日历，先计算后只裁取原请求索引比较。标签仍按T+1到T+11原定义；不能改变segment、原样本、输出值或容差来“修过”。

[`Alpha158DL`](https://github.com/microsoft/qlib/blob/v0.9.7/qlib/contrib/data/loader.py) 默认rolling窗口包含60，并有嵌套Ref。**动量20日修复不等于所有Alpha158特征已预热验收**。已有provider如果恰好从train日开始，Qlib不可能创造更早价格，早期特征会有缺失/部分窗口。应追加历史覆盖诊断，而非擅自补采数据或重训来改变历史阴性结论。未来正式比较若要定义warmup，应单独冻结方案；本次只修审计边界。

## 必要回归边界

1. fund_adj总2,500、单次强制2,000：默认策略取全；调用者传6,000也必须归一到官方安全上限或明确拒绝，不能只改默认值。
2. 满页、恰好整倍数、空尾页、重复/无推进页、超请求行数、错误响应和页数耗尽明确失败；键/日期越界不允许悄悄去重掩盖丢失。
3. fund_daily 5,001条、fina_indicator 101条使用对应安全分区；普通版/VIP策略分别验证，未知上限不伪装已验证。合成服务器行为只能证明算法，不能证明真实网关支持offset。
4. Qlib原生小型合成Binary：训练前存在≥20交易日价格，通过原标签/动量独立对账；没有前史时NaN掩码一致；停牌缺值保留；原segment、标签未来11期成熟度约束照旧。
5. 因子start当天变化且上个全市场交易日该证券缺行、较早前驱超过60自然日：找回前驱后输出正确比值；没有可证明基线时报告缺口，不把未知当无事件。

以上是执行方案与证据边界，业务修复和回归尚未执行。已有30股665配对日的负面结果不因潜在边界问题自动失效；实际影响要由冻结snapshot/provider起止日和已存响应逐项判定。全市场一年日线、股票因子、财务展示、ETF深历史是不同数据范围，不能相互替代验收。
