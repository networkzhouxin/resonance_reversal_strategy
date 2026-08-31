# resonance_reversal_strategy 交接文档

更新时间：2026-08-31

适用仓库：`git@github.com:networkzhouxin/resonance_reversal_strategy.git`

## 1. 接手后先做什么

1. 完整阅读仓库根目录 `AGENTS.md`，并严格遵守。
2. 只能处理独立的 `resonance_reversal_strategy`；禁止读取、复制、运行或验证
   `cross_signal` 及任何其他策略。
3. 核对分支、提交、远程和工作区：

   ```powershell
   git status --short --branch
   git log -3 --oneline --decorate
   git remote -v
   git branch -vv
   ```

4. 确认当前研究分支是 `codex/volume-ratio-soft-priority`。本交接文档写入前的研究
   HEAD 是 `a84ab9a`；包含本交接文档的最终提交号以交接消息和 `git log -1` 为准。
5. 在任何代码或交易行为变更前，先做只读分析，给出中文实施计划、影响边界、保护项和
   验收指标，取得用户明确确认后再实施。

## 2. 当前版本定位

### 2.1 官方保留基线

官方保留基线仍是 build `20260828.5`，没有被后续研究候选替代。必须保留：

- `ATR_EXIT_POLICY="OBSERVE_ONLY"`；
- `relative_buy_policy="EMPTY_SLOT_BACKFILL"`；
- FORMAL 始终整体优先于 RELATIVE；
- 当前信号、原始排序、仓位、正式卖出和训练边界；
- T-1 日线决策边界；
- 2019--2021 唯一训练期；
- 2018 只作为只读 warm-up 和交易日历证据；
- manifest、日志身份、源文件不可变和 fail-closed 校验；
- 普通/双倍摩擦比较流程。候选普通摩擦未通过时，不进入双倍摩擦。

### 2.2 当前分支中的策略代码

核心策略文件：

```text
resonance_reversal_strategy/smart_trade_joinquant_resonance_reversal_etf.py
```

当前文件是研究候选 build `20260831.2`，不是已晋升基线。文件身份：

```text
DEPLOYMENT_BUILD_ID = "20260831.2"
FORMAL_EVENT_LOGIC_BUILD_ID = "20260827.3"
ATR_EXIT_POLICY = "OBSERVE_ONLY"
RELATIVE_BUY_POLICY = "EMPTY_SLOT_BACKFILL"
NEW_BUY_VOLUME_POLICY = "T1_VOLUME_RATIO_SOFT_PRIORITY_WITH_FALLBACK"
NEW_BUY_VOLUME_THRESHOLD = 1.0
```

策略文件 SHA256：

```text
2e80182c371f058a35004eb563c00cacc27293c324b91e4a5f9449c8bb9f4d54
```

`20260831.2` 相对 `.5` 唯一允许的行为变化是：FORMAL 和 RELATIVE 各自在原稳定
顺序内，把 T-1 `volume_ratio <= 1.0` 的新买入候选稳定移到本组前部；`> 1.0`
和无效值仍保留为后备。它不是买入资格、仓位或卖出条件，RELATIVE 低量比不得跨组
挤占 FORMAL 高量比。

## 3. Git 状态与提交链

交接文档写入前：

```text
branch: codex/volume-ratio-soft-priority
a84ab9a docs: archive volume priority paired attribution
2f32f3a feat: add volume ratio soft priority candidate
adcb020 fix: preserve frozen manifest bytes
```

远程：

```text
origin git@github.com:networkzhouxin/resonance_reversal_strategy.git
```

当前研究分支尚未配置 upstream。只执行本地 `git commit` 不足以在另一台电脑取得该
分支；交接提交完成后，需要在原电脑显式推送：

```powershell
git push -u origin codex/volume-ratio-soft-priority
```

推送不包含被 `.gitignore` 排除的原始聚宽日志，日志必须按第 6 节单独迁移。

## 4. `.5` 与 `.2` 普通摩擦权威结果

JoinQuant 2019--2021 训练期普通摩擦结果：

| 指标 | `.5` 官方基线 | `.2` 研究候选 |
|---|---:|---:|
| 期末资产 | 33,213.3元 | 33,792.7元 |
| 总收益 | 66.0665% | 68.9635% |
| 最大回撤 | 15.9334% | 15.8867% |
| 已平仓交易 | 66 | 68 |
| 期末未平仓 | 3 | 3 |
| 胜/负 | 50/16 | 51/17 |
| 交易胜率 | 75.7576% | 75.0000% |
| Wilson 95% 下界 | 64.1909% | 63.5614% |

`.2` 提高了总收益，最大回撤略降，并通过年度收益和利润集中度相关门槛；但它没有满足
预注册的关键条件：胜率没有严格提高、Wilson 下界下降、最大回撤没有降到 15% 以下。
因此：

- `.2` 保留为研究候选；
- `.5` 继续作为官方保留基线；
- `.2` 不晋升，不进入双倍摩擦；
- 不搜索 0.8、0.9、1.1 等相邻量比阈值；
- 不得把 `.5` 固定路径中 `volume_ratio <= 1.0` 的事后 85.29% 胜率当成新策略胜率。

## 5. 已完成研究及结论

### 5.1 量比软优先

已提交研究报告：

```text
resonance_reversal_strategy/docs/research/2026-08-31-volume-priority-paired-attribution.md
```

关键结论：

- 669 条排序决策中，`<=1.0` 为 367 条，`>1.0` 回退为 302 条；
- 58 个同日同来源可行动配对；
- T+1 低量比跑赢 28/58，T+3 为 30/48，T+5 为 32/54；
- 年度、来源和周期方向不完全一致；
- 实际成交的高量比回退一侧仍为 3 胜 1 负、固定路径净利润为正；
- 软优先方向可保留，但不支持把 `>1.0` 变成不合格候选。

### 5.2 已否决的入场和退出方向

以下均为回测后只读、原路径固定的诊断，不是正式策略回测结果，也没有生成规则候选。

#### RELATIVE 买入统一推迟一个交易日

使用下一交易日 09:35 已记录的 ATR 观察价，固定原标的、数量和实际退出，重新估算
买入成本：

| 指标 | `.5` | `.2` |
|---|---:|---:|
| 已平仓 RELATIVE 样本 | 53 | 55 |
| 胜单变化 | 40 → 38 | 41 → 39 |
| 净利润变化 | -1,481.1元 | -1,385.5元 |
| 排除最大绝对影响后 | -1,145.1元 | -1,041.1元 |

2020 和 2021 均恶化。次日 RELATIVE 信号仍存在的样本只有 1 笔，任意 BUY 信号仍存在
也只有 2 笔，不支持“统一等待一天确认”。

#### RELATIVE 支持事件新鲜度

支持事件不全发生在同一 signal date 的样本只有 11 笔：

- `.5`：8 胜 3 负，净利润约 +2,050.9 元，中位交易收益约 1.61%；
- `.2`：8 胜 3 负，净利润约 +2,361.0 元，中位交易收益约 1.61%；
- 持仓中位 MAE 约 -4.22%，明显差于同日支持组约 -0.74% 至 -0.80%；
- 胜率差双侧 Fisher 检验 p=1.0，年度方向不稳定；
- 排除最大盈利后仍为正利润；
- 新鲜度软排序只会改变 `.5` 的 2 个交易日、`.2` 的 3 个交易日。

因此不支持硬过滤，也不值得优先实施软排序。

#### 所有正式卖出统一延迟

H1/H3/H5 是现有观察日志相对 signal date 的收盘周期：H1 为执行日收盘，H3 为执行后
第 2 个交易日收盘，H5 为执行后第 4 个交易日收盘，不是新的真实撮合路径。

- H3 固定路径：`.5` 净利润约 -958.8 元、胜单 50→46；`.2` 约 -1,446.1 元、
  胜单 51→47。
- H5：`.5` 约 +630.5 元，但 `.2` 约 -537.9 元，版本与年度方向不一致。
- 亏损交易中此前出现过正 MFE 的为 `.5` 8/16、`.2` 9/17，但亏损组中位 MFE
  只有约 0.04%--0.09%，不足以支持保本或利润保护规则。

因此不支持统一延迟卖出、统一改收盘卖出或基于这项事后 MFE 建立退出条件。

### 5.3 当前唯一保留的研究线索

仅由 `BOLL+KDJ` 两个指标支持的正式卖出可能有部分偏早：

| H5 固定路径变化 | `.5` | `.2` |
|---|---:|---:|
| 样本 | 52 | 52 |
| 净利润变化 | +1,606.3元 | +1,049.4元 |
| 胜单变化 | 38→38 | 37→37 |
| 排除最大绝对影响后 | +1,122.3元 | +541.2元 |
| 2019 | +1,113.8元 | +973.4元 |
| 2020 | +1,226.5元 | +1,257.6元 |
| 2021 | -734.0元 | -1,181.6元 |

这只是研究线索，不是候选：2021 明显反向，H5 又是多个既有观察周期之一，存在选择
偏差和真实现金/持仓路径变化。相反，`BOLL+KDJ+RSI` 三指标卖出延迟 H5 在两个版本中
都恶化，强卖出信号目前不应推迟。

## 6. 证据文件与跨电脑迁移

### 6.1 Git 已跟踪

以下文件会随分支推送和克隆：

```text
artifacts/joinquant/training-2019-2021/archive_manifest.json
artifacts/joinquant/training-2019-2021/joinquant_sessions_2018_2021.json
```

注意：`archive_manifest.json` 自身是归档清单 schema version 1；它引用的交易日历
`joinquant_sessions_2018_2021.json` 才是 Schema V2 manifest，二者不得混淆。

Schema V2 日历：

```text
bytes: 12877
sessions: 973
coverage: 2018-01-02 至 2021-12-31
evaluation: 2019-01-01 至 2021-12-31
sha256: 24cfbdb7cfcac61c1e8a6f58bbdf54f851031ad63a7feb2ac331590ab7ede87f
```

### 6.2 Git 不跟踪，必须单独复制

`.gitignore` 排除了整个 `artifacts/` 目录；下面的原始日志和 JSON 当前只存在于本机，
不能通过 Git 迁移：

| 文件 | bytes | SHA256 |
|---|---:|---|
| `resonance-20260828.5-standard.log` | 50,487,161 | `07507c5ff24117f9467577bf4f76787637264017be2d1246bcbe7550869128c5` |
| `resonance-20260828.5-double-friction.log` | 50,488,834 | `b237ef5c5d10b05e85bea247a31ad4834869c4b09cca781bd104845d2b983e63` |
| `resonance-20260831.2-standard.log` | 50,929,023 | `39632039fbb9b995360dbfd30d6d8d888d71efd42f4431c7aa98fb7cc03f7b32` |
| `resonance-20260831.2-paired-volume-priority-report.json` | 7,482 | `91a85775ea6fca446d72a9ba99bf327e2adabed524671b916abb519cfff8fb88` |

完整历史审计还包括 `.3/.4` 和 `20260828.1`--`.4` 日志，其文件名、bytes 和 SHA256
均记录在 `archive_manifest.json`。最稳妥的方式是把整个目录单独复制：

```text
artifacts/joinquant/training-2019-2021
```

可使用移动硬盘或受控共享目录。复制后在新电脑核对：

```powershell
Get-FileHash -Algorithm SHA256 `
  .\artifacts\joinquant\training-2019-2021\resonance-20260828.5-standard.log, `
  .\artifacts\joinquant\training-2019-2021\resonance-20260828.5-double-friction.log, `
  .\artifacts\joinquant\training-2019-2021\resonance-20260831.2-standard.log, `
  .\artifacts\joinquant\training-2019-2021\resonance-20260831.2-paired-volume-priority-report.json, `
  .\artifacts\joinquant\training-2019-2021\joinquant_sessions_2018_2021.json
```

必须与上表及 `archive_manifest.json` 一致；不要在 hash 不符时重新登记新 hash 来绕过
校验。

## 7. 下一步建议：只读卖出确认研究

下一步不要先改代码。建议只研究实际 `BOLL+KDJ` 两指标正式卖出后的下一交易日信号
状态：

1. 原卖出后的下一交易日仍是 `BOLL+KDJ SELL`；
2. 下一交易日增强为 `BOLL+KDJ+RSI SELL`；
3. 下一交易日 SELL 信号消失或转向；
4. 因训练期结束而右截尾。

研究合同：

- 处理阶段：`POST_BACKTEST_READ_ONLY_EXIT_CONFIRMATION_ATTRIBUTION`；
- 路径假设：原候选、成交和持仓路径固定；
- 数据：只用 `.5/.2` 普通摩擦 2019--2021 日志和冻结 Schema V2 日历；
- 下一交易日判断仍只读取当日决策时的 T-1 完整日线；
- 分别报告样本数、后续 H1/H3/H5、年度、排除最大绝对影响和右截尾；
- `.5` 是主要研究基线，`.2` 只做方向复核，不把新规则默认叠加到 `.2`；
- 不搜索等待 2/3/4/5 天等参数，不使用验证期，不直接形成交易规则。

只有在某个下一日信号状态同时满足样本足够、`.5/.2` 同向、至少两个年度稳定、2021
没有不可接受反向、排除极端值后仍成立，并且能由 T-1 信息实现时，才编写独立的单变量
候选设计和真实 JoinQuant 验收指标，再等待用户确认。

## 8. 本地验证

只允许运行专用 resonance 测试：

```powershell
python -m pytest `
  tests/test_resonance_reversal_strategy.py `
  tests/test_resonance_relative_turn_analysis.py `
  tests/test_resonance_trade_risk_analysis.py `
  tests/test_resonance_volume_ratio_soft_priority_analysis.py
```

本次交接提交前使用 Python 3.12.10、pytest 8.4.2 完整验证，结果为
`512 passed, 3 skipped`。在新电脑上应重新运行并记录 Python、pytest 版本和实际结果；
本地测试不替代 JoinQuant 收益回测。

研究分析器：

```text
resonance_reversal_strategy/research/analyze_relative_turn_observations.py
resonance_reversal_strategy/research/analyze_resonance_trade_risk.py
resonance_reversal_strategy/research/analyze_volume_ratio_soft_priority_candidate.py
```

## 9. 在聚宽运行哪个文件

如果需要复现当前 `.2` 研究候选，把以下文件完整复制到聚宽策略编辑器：

```text
resonance_reversal_strategy/smart_trade_joinquant_resonance_reversal_etf.py
```

运行前必须核对初始化日志包含 build `20260831.2`、ATR `OBSERVE_ONLY`、RELATIVE
`EMPTY_SLOT_BACKFILL`、量比软优先策略和阈值 1.0。不要把这次运行称为 `.5` 基线复现。
若要复现官方 `.5`，可从提交 `adcb020` 的同一路径恢复到独立工作树后运行；该提交中的
策略文件已核验为 `DEPLOYMENT_BUILD_ID="20260828.5"`。不得直接修改当前 `.2` 文件并
声称是 `.5`。

## 10. 新电脑恢复建议

原电脑先完成交接提交并显式推送当前分支。新电脑执行：

```powershell
git clone git@github.com:networkzhouxin/resonance_reversal_strategy.git
Set-Location .\resonance_reversal_strategy
git fetch origin
git switch --track origin/codex/volume-ratio-soft-priority
git status --short --branch
git log -3 --oneline --decorate
```

然后把第 6 节的 `training-2019-2021` 证据目录复制到仓库对应相对路径，逐项校验
SHA256，运行第 8 节专用测试。开始研究前再次阅读 `AGENTS.md`。

## 11. 禁止事项

- 不读取、复制、运行或验证其他策略；
- 不使用验证期、全周期或 2022+ 结果调参；
- 不让 T 日成交量或未来价格修改冻结信号、排名、仓位或卖出决定；
- 不把事后分组、固定路径或相关性直接升级为交易规则；
- 不回退 `.5` 已确认保留的 ATR 纯观察和 RELATIVE 空位补位；
- 不把 `.2` 误标为已晋升基线；
- 不在普通摩擦候选未通过时运行双倍摩擦；
- 不静默修改 manifest bytes、日志或 SHA256；
- 不叠加多个候选后再判断效果；
- 不使用本地收益模拟替代 JoinQuant 权威结果。
