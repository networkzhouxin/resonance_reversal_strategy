# HARD BOLL 相对买入观察化候选

## 身份与证据

- 保留基线：build `20260902.3`，main `55b47ee`
- 候选：build `20260904.2`
- 状态：`CANDIDATE_IMPLEMENTED_AWAITING_JOINQUANT`
- `rule_adopted=false`
- 普通摩擦：`PENDING`
- 双倍摩擦：`DEFERRED_NOT_RUN`

基线日志 `resonance-20260902.3-standard.log` 的 SHA-256 为
`47af385cdf55a99431a3604ef5d5c9d2df1a0d614f82c157a84141b5731a17c6`；
Schema V2 SHA-256 为
`24cfbdb7cfcac61c1e8a6f58bbdf54f851031ad63a7feb2ac331590ab7ede87f`。

`.3` 原路径固定归因中，`SOFT_ALL_THREE` 为 54 笔、41 胜 13 负、胜率
75.93%、净利润 12,211.6 元、盈利因子 3.30；`HARD_BOLL_SOFT_OSC` 为
14 笔、9 胜 5 负、胜率 64.29%、净利润 1,073.2 元、盈利因子 1.45，且
2021 年净利润为 -172.6 元。Fisher 双侧检验约 `p=0.324`，因此该归因只用于
预注册，不能代替候选真实路径结果。

## 唯一规则

```text
HARD_BOLL_SOFT_OSC: 保留观察和结果记录，不获得 RELATIVE 新买入资格
SOFT_ALL_THREE: 保持现有新买入资格和后续流程
```

三指标门禁先执行。两指标候选仍记录 `NEW_BUY_REQUIRES_THREE_SUPPORTERS`；只有
满足三指标要求的 HARD 分支 BUY 记录 `RELATIVE_BUY_BRANCH_OBSERVE_ONLY`。

本门禁只位于 `collect_relative_buy_decisions`，不得传播到观察构造、FORMAL、
SELL、DMI 排序、空位补位、仓位、ATR、异常或清理路径。保持 T-1、2019—2021
训练期、2018 只读 warm-up、市场宽度只观察及全部 fail-closed 校验不变。

## 普通摩擦验收

只运行一次与 `.3` 同设置的 2019—2021 普通摩擦 JoinQuant 回测，并同时要求：

1. 已平仓胜率高于 74.6479%，日胜率高于 51.2329%；
2. 总收益不低于 77.1940%，最大回撤低于 15.88318%；
3. 已平仓不少于 50 笔，三个年度净利润均为正；
4. 中位收益不低于 2.4811%，盈利因子不低于 2.929；
5. 前 3 笔毛利润占比不高于 26%，期末未平仓不超过 3 笔；
6. build 为 `20260904.2`，初始化字段为
   `relative_new_buy_branch_policy="SOFT_ALL_THREE_ONLY"`；
7. HARD 观察仍存在、三指标 HARD BUY 均按新原因拒绝且没有该分支成交；
8. 身份、T-1、manifest、成交订单和持仓账本校验全部通过。

任一硬门槛失败即拒绝候选并保留 `.3`。普通摩擦通过后，再由用户决定是否补做
双倍摩擦；当前不得表述为已通过。
