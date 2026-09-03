# RELATIVE BUY 下一交易日价格跟随确认候选

## 候选身份

- 候选 build：`20260903.1`
- 保留基线：build `20260902.3`
- 基线策略行为提交：`350e3dd`
- 基线 main 提交：`55b47ee`
- 训练期：2019-01-01 至 2021-12-31
- 2018 数据：只读 warm-up 和交易日历
- 第一阶段：普通摩擦聚宽回测
- 处理阶段：`IMPLEMENTED_LOCAL_NOT_BACKTESTED`
- `rule_candidate_created=true`
- `rule_adopted=false`
- 双倍摩擦：`DEFERRED_NOT_RUN`

本候选于 2026-09-03 经用户确认后实现。它只获得一次训练期真实路径实验资格，
不代表规则已经有效或取代保留基线。JoinQuant 回测仍是收益表现的权威依据。

## 单一假设

当前 RELATIVE BUY 识别的是局部拐点。部分信号形成后没有出现短期价格延续，
可能直接进入下跌并形成长时间持仓。本候选只检验一个假设：

> RELATIVE BUY 形成后的下一交易日，若完整 T-1 收盘价严格高于原信号日
> 收盘价，则局部拐点具有更好的价格跟随质量。

不加入 MACD、均线、ADX、量比、ATR 或市场宽度的新阈值，也不搜索确认幅度和
确认天数。

## 唯一允许变化

只对通过现有全部资格的 RELATIVE 新买入候选增加一次确认：

1. 第一次发现候选时冻结其身份、支持者、原排序次序、信号日期和信号收盘价，
   当日不提交买单；
2. 下一次交易日运行时，只读取该时点已经完成的 T-1 快照；
3. `confirmation_close > signal_close` 时释放原冻结候选；
4. `confirmation_close <= signal_close` 时取消该次候选；
5. 确认日快照或现有入场 ATR 无效时 fail-closed 取消；
6. 确认成功后进入原 `run_signal_buys`，继续由 FORMAL 优先、RELATIVE
   空位补位和既有订单状态规则处理。

等于原信号价属于不通过。不存在 0.1%、0.5% 或其他缓冲阈值。

## 控制流与数据边界

- FORMAL BUY 不进入待确认状态，继续在原决策日进入既有流程；
- RELATIVE SELL 仍然只观察，不进入买卖执行；
- RELATIVE 的三指标资格、DMI 负向优先排序及原共振身份不变；
- 冻结后的排序不得被确认日 DMI 或其他指标重新排列；
- 确认只使用 T-1 收盘价，T 日 09:35 行情仍只用于可交易性和执行价格；
- 确认日继续执行原有 T-1 ATR 有效性保护，不修改 ATR 计算或退出策略；
- 损坏的确认状态只清空 RELATIVE 待确认队列并记录诊断，不得阻断 FORMAL
  买卖；未来数据错误仍原样抛出；
- 同一代码在确认处理当日不从同一批快照重新登记新的待确认候选，避免把失败
  候选无限滚动；
- 待确认状态不控制卖出、持仓清理、ATR、市场环境或研究工具。

## 审计身份

初始化日志必须同时输出：

- `build="20260903.1"`；
- `atr_exit_policy="OBSERVE_ONLY"`；
- `relative_buy_policy="EMPTY_SLOT_BACKFILL"`；
- `relative_buy_priority_policy="DMI_NEGATIVE_FIRST"`；
- `relative_buy_confirmation_policy="NEXT_SESSION_T1_CLOSE_ABOVE_SIGNAL_CLOSE"`；
- `new_buy_support_policy="REQUIRE_ALL_THREE_INDICATORS"`；
- `new_buy_required_support_count=3`。

确认过程使用以下固定原因码：

- `RELATIVE_BUY_AWAITING_FOLLOW_THROUGH`；
- `RELATIVE_BUY_FOLLOW_THROUGH_CONFIRMED`；
- `RELATIVE_BUY_FOLLOW_THROUGH_FAILED`；
- 无效快照、ATR、信号价和日期倒退使用独立 fail-closed 原因码。

## 必须保持不变

- `ATR_EXIT_POLICY="OBSERVE_ONLY"`；
- FORMAL 和 RELATIVE 都必须三指标支持才能成为新买入候选；
- FORMAL 排序、RELATIVE 原 DMI 排序以及 FORMAL 优先级；
- 最大持仓、目标敞口、现金保留、停牌递补和订单状态；
- 正式 SELL、最短持有期、持仓状态和期末持仓处理；
- 市场宽度只读观察；
- T-1 日线边界、2019—2021 训练期和 2018 只读边界；
- manifest、日志身份、源文件哈希、普通/双倍摩擦状态和 fail-closed 审计。

## 普通摩擦预注册验收

保留基线 `20260902.3` 的普通摩擦日志基准为：总收益 77.1940%，已平仓
71 笔、53 胜 18 负，手续费后胜率 74.6479%，日胜率 51.2329%，最大回撤
15.88318%，中位交易收益 2.4811%，前 3 笔毛利润占比 21.3898%，期末
未平仓 3 只。

候选必须在真实聚宽路径中同时满足：

1. 手续费后已平仓胜率至少提高 2 个百分点；
2. 总收益不低于 77.1940%；
3. 最大回撤不高于 15.88318%；低于 10% 是后续总体目标，不以牺牲本表
   其他质量指标换取；
4. 日胜率严格高于 51.2329%；
5. 已平仓交易不少于 61 笔，即不低于基线的 85%；
6. 2019、2020、2021 各年净利润均为正，任一年度胜率不得比基线下降超过
   5 个百分点；
7. 中位交易收益、盈亏比必须完整报告，且不得出现不可接受恶化；
8. Top 1、Top 3、Top 7 毛利润集中度必须完整报告，不能用头部盈利掩盖
   大量亏损；
9. 期末未平仓不超过 3 只，并单独披露浮动盈亏；
10. 初始化身份、730 个训练交易日、T-1 日期、订单状态、组合账本、日志
    SHA-256 和源文件身份全部通过 fail-closed 校验。

普通摩擦任一硬门槛失败即拒绝候选并保留 `20260902.3`。只有普通摩擦全部
通过，才单独决定是否运行双倍摩擦；不得根据回测结果搜索确认天数、涨幅阈值
或追加其他指标。
