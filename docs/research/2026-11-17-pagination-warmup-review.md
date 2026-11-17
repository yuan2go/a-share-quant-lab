# PR #5 / #6 合并后分页与历史边界核查

核查日：2026-11-17，北京时间。**结论：两项 P2 成立；另有同类分页和复权前驱边界风险，但现有证据不支持撤销首轮阴性研究或整批 TSP 验收。业务修复尚未执行。**

## 1. 身份、权限与证据

- 本地 main、HEAD、`git ls-remote origin refs/heads/main` 一致：`b01f0c4486808595e1364e07c28ab6129c0cb380`；开始时工作区干净。
- [PR #5](https://github.com/yuan2go/a-share-quant-lab/pull/5)：review head `12ec4357af69dfebffb9be10ef95494ad8dc71c4`，merge `17670344da4a8fc5b73ab4021966ecab24c16185`；[具体发现](https://github.com/yuan2go/a-share-quant-lab/pull/5#discussion_r4587301510)。GitHub 合并时钟为北京时间 **11月16日22:54:56**，并非17日。
- [PR #6](https://github.com/yuan2go/a-share-quant-lab/pull/6)：review head `1fe16e4f4d819ab3ad9461c22fdc4eb922e2a35b`，merge 即本次 main；[具体发现](https://github.com/yuan2go/a-share-quant-lab/pull/6#discussion_r4588512445)。合并时钟为北京时间11月17日00:33:40。
- TSP 本地官方 checkout：`f9cb383c5918c6a88a412f3ce43d59fe81b94ccc`（v0.3.37）；Qlib 已有研究环境：0.9.7。
- 已读现行 README、ROADMAP、RESEARCH-PROTOCOL、STORE-CONTRACT、结果和 TSP 验收文档、受影响源码、保存的运行脚本及产物。STORE-CONTRACT 的30股研究采集范围与TSP一年全市场展示范围应分别理解。
- 本次仅新增研究文档；诊断脚本、合成 fixture 和脱敏聚合 JSON 存外置盘。未读取令牌文件，未请求真实行情、重训、重采、重启服务、改写数据库/冻结产物或提交推送。

官方契约和完整接口矩阵见 [official-contracts](2026-11-17-official-contracts.md)；执行提示见 [codex-prompt](2026-11-17-pagination-warmup-codex-prompt.md)。

## 2. 实际调用链与发现

### A. 统一6000分页：确定缺陷，影响不只ETF因子

`Provider.get_adj_factors(etf)` → `Client.all('fund_adj')` → `pages()` → `query(limit=6000, offset=i*6000)`。`pages()` 把任何小于6000的返回当作结束，而[官方 fund_adj](https://tushare.pro/document/2?doc_id=199)最多返回2000，且明确支持offset/limit。单只ETF未指定start时从1990开始，深历史可达到上限；大股票集/ETF集按日取数也可能达到上限，不能仅修单代码路径。

同一错误逻辑还覆盖：

| API / 路径 | 官方限制 | 判定 |
| --- | ---: | --- |
| `fund_daily`，`iter_daily(etf)`逐代码时间窗 | 5000 | 确定同类风险；[官方](https://tushare.pro/document/2?doc_id=127)要求按代码/日期循环 |
| 普通 `fina_indicator`，财务metrics的≤100股票分支 | 100 | 确定同类风险；约1100自然日通常不触顶，但不能假定修订记录总数<100；[官方](https://tushare.pro/document/2?doc_id=79) |
| `ths_daily` | 3000 | Client允许但当前provider未调用；条件性风险，不能说已影响本轮数据；[官方](https://tushare.pro/document/2?doc_id=260) |
| `ths_index` | 5000，官方要求不要循环 | 维表应一次有界获取，不套机械分页；BOOT私有脚本确有调用；[官方](https://tushare.pro/document/2?doc_id=259) |

`daily`/`daily_basic`/`stock_basic`官方明确6000，未发现“官方上限低于默认6000”的同类证据。`fund_basic`为15000。`adj_factor`、`index_daily`、`trade_cal`、财务普通三表及四类VIP、`ths_member`没有在所查页面明确各自数值上限，不能臆造统一上限。[SDK](https://github.com/waditu/tushare/blob/master/tushare/pro/client.py)透传kwargs不证明每个endpoint都实施offset/limit。`index_basic`在允许列表但provider不调用，`rt_k`为独立权限受阻路径，均不是本次新增分页实现范围。

还有两个工程边界：当前重复检测仅比上一页完整JSON，无法识别非相邻循环或部分重叠；没有拒绝返回数大于请求limit，固定offset步长可能造成重叠。日线/因子有唯一证券日期键，财务则必须保留公告/更新/报表类型等修订身份，不能按证券报告期提前去重来掩盖源问题。

### B. Qlib动量审计：错误拒绝合法快照，并非直接算错已发布RankIC

`run_first_qlib_study:99`从train首日起取日历 → `_verify_targets:255`仅加载该范围close → `wide.shift(20)`。但[Qlib LocalExpressionProvider](https://github.com/microsoft/qlib/blob/v0.9.7/qlib/data/data.py)按表达式扩展读取，[Ref](https://github.com/microsoft/qlib/blob/v0.9.7/qlib/data/ops.py)可使用provider已有的前20交易日。两边边界不同，审计会在model.fit之前报错。

官方0.9.7原生小型合成Binary诊断：provider有25个训练前交易日，内部另含一个NaN；当前train截断日历触发`native momentum differs...`，完整provider日历对同一dataset通过动量及三段原始标签对账。没有训练或调整容差。此结果证明故障机制和可行修复方向，不是业务代码已修复。

[Alpha158DL](https://github.com/microsoft/qlib/blob/v0.9.7/qlib/contrib/data/loader.py)含60期及嵌套Ref窗口；Rolling使用min_periods=1，所以历史不足也可能产生部分窗口数值，不能只数NaN判断已经充分预热。20期审计修好不代表158个特征全部充分预热。首轮从train日开始的有限历史是已披露研究限制，不能自动补采、删训练行或重训以追求完整窗口。

### C. 复权因子前驱：另一项确定可触发的边界缺陷

`get_adj_factors`小集合只回溯60自然日；大集合虽读取60日范围日历，却只抓start前最后一个市场交易日。`events()`把每证券首条累计因子作为基线，不输出事件。某证券前一市场日无记录、其实际前驱更早时，首个区间内变动会被漏掉；也可能将多次未知变动合并归到后续日期。

离线调用真实`Provider.get_adj_factors`，合成源已知1月2日因子1、4月1日因子2，从4月1日请求：小集合只查1月31日起、大集合只查3月31日基线，两分支都返回0事件，正确前驱可得时应为ratio=2。该诊断不声称真实Tushare必然在停牌日缺因子；它证明当前代码对缺前驱不做完整性判定。

## 3. 历史产物影响：逐范围判断

只读审查747个现存响应缓存，聚合身份为排序`[文件名, SHA256]`JSON的SHA256：`f253759e7fa28548014e407272b25d8ec25e29d275658036f9d3e0068a9b0d33`。这绑定本次读取到的历史响应集合，不是交易所对账或历史PIT证明。

| 范围 | 本次证据 | 影响判断 |
| --- | --- | --- |
| 首轮Qlib冻结研究 | run `8e5bf49b0f1ce6bce7be20fd`；Binary日历2019-01-02—2026-10-30共1897日，起点等于train起点 | 没有训练前历史，未触发动量审计误拒条件；保留665日/19919对及原阴性指标 |
| 首轮AQL真实取数 | 另用`src/tushare_source.py`，单证券3501自然日闭区间拆分，响应≥6000硬拒绝；不是TSP Client | ETF的2000/5000限额与普通财务100限额不进入首轮调用链；trade_cal另有逐自然日完整性检查 |
| TSP股票一年日线 | 原始各日最多5579行，因子最多5584行；484个日/API任务；原生验收1328772有效行 | 未发现本次已知低限额错误触发；不撤销现有有限验收，仍不等于外部完整性证明 |
| 10只ETF种子 | 每只fund_adj279行、fund_daily242行；10只合计日线2420行 | 均低于2000/5000，缓存没有更深ETF请求；深历史缺陷不能追溯为这批已截断 |
| 财务全市场 | >100分支使用4类VIP，各11个报告期；完整页6000后有offset6000，均有短尾页 | 不是普通fina_indicator的100条分支；已有网关分页推进证据，未发现已知误判；官方VIP限额/全覆盖证明仍UNKNOWN |
| 复权窗口前驱 | 5420只窗口前已上市股票全部在2025-11-14有因子；159只当代股票在窗口内上市；10只ETF各37条窗口前因子 | 已上市股票/种子ETF未发现缺基准条件；窗口内新股不能伪造上市前因子，不升级为独立公司行为核验 |
| 板块成分 | BOOT脚本通过pages('ths_member')保存73页：72×6000+4024=436024；ths_index返回1666 | 有本次网关推进记录；当前成分无历史PIT资格，未证明官方通用分页或独立全集 |

研究manifest SHA256仍为`06b067a408e7c713d34b5625afba615a01cb939a4bb0dd525e332a77abd142d3`；日历SHA256为`164762ead9ff63bf5356a361bbd6c6ebd872bdca14861467b5074ac2929a2a3a`；保存study-report SHA256为`ab165a25c4304aff00f38d9be10fc8fc92734c008d8c1f90fb7950f529d01c22`。本轮读取指标，没有重新计算真实RankIC或复验全部Binary文件。

TSP市场环境首段、上市不久证券及长窗口指标的预热限制已在原验收说明披露。它们与数据成功同步的242日分母不能互相替代；本次不修改上游指标引擎、不补拉前史。

## 4. 修复方案

1. **按契约选择请求策略，禁止只改一个全局默认数。** 在现有client/provider扩展点维护小型endpoint策略，区分有证据的offset分页、按证券/日期分区、一次取全。fund_adj有效limit≤2000，显式传6000也拒绝或钳制，实际offset与有效页长一致。正整数参数、响应超过limit、循环/无推进、唯一键重叠、越界键、页数/请求预算耗尽都明确报错。若不能证明短页语义，使用支持offset的有界空尾页确认并按已返回原始行数推进，或改用可证明有界的分区；不得继续以6000为统一完成证明。
2. **不依赖未证实的分页。** fund_daily按代码及互不重叠日期窗，单证券窗口的理论最大日数低于5000，饱和则拆分；普通fina_indicator按官方报告期日期分区，返回100需继续拆，最小分区仍饱和就报不完整，不把未知revision数当≤1。三张报表start/end是公告日，fina_indicator是报告期，不能混用轴。已运行VIP/ths_member保留特定网关证据身份；后继策略需显式说明依据及完整性条件，不能套普通版100、擅换API或增加付费请求。ths_daily仅登记其3000限制，不新增功能；ths_index按官方一次取全。未知契约确实阻断时精确限制该路径，不牵连已完成历史记录。
3. **Qlib审计读取完整provider日历和原始close，再裁回原审计键。** 最简单可取完整日历；若仅取train前20期，扩展区只服务独立shift，不把这20期本身也纳入需要额外20期历史的比较。始终先reindex交易日历、保留缺值后shift；证券键与具名索引不变。11期未来标签/隔离检查、segments、模型参数、股票池、评价分母逻辑不动，不能dropna压缩日历、填价、跳过首20审计行、放宽容差或删训练样本。
4. **复权前驱按证券确认。** 先消费已授权本地响应；没有前驱时，未来获得采集授权后才按有界历史窗回溯，区分已有上市历史、窗口内新上市、源缺失。不能仅凭60自然日或全市场前一日判足够。无法建立事件时点所需前驱则该范围明确失败/缺口，不能返回成功空帧，也不能把首个累计值直接当单次事件因子。对区间内部因子缺口同样避免把跨缺口比值冒充单日事件。
5. **保留TSP契约及缓存。** [TSP ProviderRequestError](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/backend/app/data_providers/base.py)必须传播到原生同步，使失败流不提交为成功；复用[现有staging](https://github.com/shy3130/tick-stock-panel/blob/v0.3.37/backend/app/services/kline_sync.py)，不Fork引擎。保留不复权OHLC、量手/额元、累计值→事件比例、进度/取消语义。旧6000请求缓存保存原字节/请求身份；修复后改变参数会产生新身份，不做全量删除或追改旧缓存。真实运行及未覆盖条目标NOT_RUN/UNKNOWN，不以合成测试替代。

## 5. 必要回归和交付边界

仅增加与修复风险直接相关的参数化边界测试，优先复用现有client、units和native smoke入口：

- fund_adj 1999/2000/2001/2500/4000；默认和显式超限page_size；空尾页、异常页长、重复/循环/无推进、键冲突/越界、后页失败及预算耗尽。验证完整原始键集，不只计数。
- fund_daily 5001、fina_indicator 101的安全分区，边界日期不重不漏；报告期/公告日轴及单分区饱和拒绝。VIP不误套普通限额；未知契约保持显式状态。
- 原生Qlib有≥20期前史/无前史/不足20期，含缺失证券日；独立标签/动量值和NaN掩码都一致，三段及11期成熟约束不变。不跑真实模型训练。
- 复权start日变化、前驱超过60自然日/前一市场日缺行、窗口内新上市/缺口无法证明；小集合及大集合两条真实Provider分支都覆盖。至少一次TSP原生staging后页失败验证正式数据未被部分覆盖。

可运行既有本地测试及必要官方Qlib/TSP合成联调；无依赖则明确NOT_RUN并交付诊断，不安装/启动真实采集绕过授权。每条测试是否必要由风险决定，不新增测试框架或庞大矩阵。

本轮已完成：远端main/PR核实、真实调用链静态审查、保存产物元数据审计、3种限额截断离线复现、官方Qlib原生审计边界复现、两个Provider复权分支离线复现。**未完成：业务修复、修复后回归、真实网关修复后验收、独立数据完整性/公司行为/PIT证明。**

私有可复现证据目录：`/Volumes/DevSSD/Development/Workspace/task-data/WP-AQL-PAGINATION-WARMUP-REVIEW-20261117/`，含`audit_saved_metadata.py`、`saved-artifact-audit.json`、`reproduce_boundaries.py`、`boundary-diagnostics.json`、`reproduce_provider_baseline.py`、`provider-baseline-diagnostics.json`。脚本只读旧产物或使用新建合成fixture，不访问付费网关。研究模型/原始付费行不进入公开Git。
