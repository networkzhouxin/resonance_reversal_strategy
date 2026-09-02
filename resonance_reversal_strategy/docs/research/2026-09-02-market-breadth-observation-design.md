# 市场宽度观察版本设计

## 研究身份

- 观察 build：`20260902.2`
- 交易行为控制版本：`20260901.4`
- 处理阶段：`OBSERVATION_ONLY_AWAITING_JOINQUANT_CONTROL_REPLAY`
- `strategy_behavior_changed=false`
- `rule_candidate_created=false`
- `rule_adopted=false`

本版本只补充 T-1 市场状态证据，用于研究市场环境是否能够区分两指标和
三指标新买入的质量。观察结果不得直接成为交易资格、排序或仓位规则。

## 唯一观察定义

每日信号快照全部构建完成后，对有效 ETF 快照计算：

```text
at_or_above_ratio =
    T-1 close >= T-1 boll_mid 的 ETF 数量 / 有效 ETF 数量
```

状态固定为：

- 有效快照为零：`UNKNOWN`；
- `at_or_above_ratio >= 0.5`：`RISK_ON`；
- `at_or_above_ratio < 0.5`：`RISK_OFF`。

`0.5` 是唯一预注册的自然多数边界，不搜索其他比例。无效、缺失、非有限或
非正的收盘价/BOLL 中轨只从宽度分母中排除，不改变对应 ETF 的交易处理。

## 日志与身份

初始化日志新增：

- `market_breadth_observation_policy=`
  `"T1_POOL_CLOSE_AT_OR_ABOVE_BOLL_MID_MAJORITY"`；
- `market_breadth_risk_on_minimum_ratio=0.5`。

每个决策日新增一条 `market_breadth_observation`，记录 build、参数和资产池
指纹、决策日、信号日、状态、总样本数、有效/无效数量、位于中轨之上和之下
的数量及比例。

## 影响边界

唯一允许变化是结构化观察日志和 build 身份。下列行为必须与
`20260901.4` 完全一致：

- FORMAL、RELATIVE 信号、候选集合和事件窗口；
- `DMI_NEGATIVE_FIRST` 排序和空位补位；
- 支撑数量、BOLL 新鲜度及代码稳定排序；
- 最大持仓、目标仓位、现金保留和订单状态；
- 完整 SELL 共振、最短持有期、挂起退出及异常路径；
- `ATR_EXIT_POLICY="OBSERVE_ONLY"`；
- T-1 决策边界以及 2019—2021 训练期；
- 2018 只作为只读 warm-up 和交易日历；
- manifest、日志身份、原始证据和 fail-closed 校验。

市场宽度状态不得被买入、卖出、排序、仓位或异常分支读取，不得充当功能
开关，也不得触发提前返回。

## 聚宽控制回放门禁

只运行一次 2019—2021 普通摩擦控制回放。除新增观察日志和 build 身份外，
必须与归档 `.4` 满足：

1. 买卖成交身份、时间、方向、数量和顺序完全一致；
2. 成交订单状态转换和每日持仓账本完全一致；
3. 每日总资产、可用现金、期末持仓、总收益和最大回撤完全一致；
4. 730 个训练交易日每天恰有一条市场宽度记录；
5. 每条记录的 `signal_date` 为对应 `decision_date` 的上一 manifest 交易日；
6. 初始化身份、参数/资产池/事件/相对观察指纹全部通过 fail-closed 校验。

任一交易路径差异都视为观察版本失败并停止研究。由于本版本不改变交易行为，
本阶段不运行双倍摩擦。

## 后续只读分析边界

控制回放一致后，才允许按 `RISK_ON`/`RISK_OFF` 比较两指标与三指标候选的
T+1、T+3、T+5 方向收益、同日可执行竞争、真实成交、年度稳定性和利润质量。
结果仍属于原路径固定的只读归因；只有交互方向跨年度稳定且在真实竞争场景中
存在足够样本，才另行形成一个预注册动态候选并再次取得用户确认。
