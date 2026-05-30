# Reflection Space: 认知地图与反思空间

Status: research memo plus first deterministic topology/feedback MVP; not a
complete visual product or foreground runtime contract.
Origin: user observation, 2026-05-28.
Related: [journey-tracking.md](journey-tracking.md) — Journey 数据结构,
[dream-task-design.md](dream-task-design.md) — 整合型任务（compensatory/prospective/amplification）,
[affect-side-channel.md](affect-side-channel.md) — hexagram 直觉层,
[ambient-associative-recall.md](ambient-associative-recall.md) — AAR 管线.

## Implementation Status

The first MVP lives in `skills/aippocampus/scripts/reflection_space.py`.

- It builds an inspectable `aippocampus_reflection_topology` from existing
  Journey dictionaries: journey nodes, waypoint nodes, current-frontier nodes,
  source-ref-carrying edges, and available actions (`expand`, `merge`,
  `revive`, `abandon`).
- It converts source-ref-carried feedback rows into advisory
  `aippocampus_reflection_adjustment` records over only three surfaces:
  `ranking`, `confidence`, and `visibility`.
- It handles recall effects, turning points, user corrections, and map actions
  as AAR/reflection strategy hints; every adjustment declares
  `clean_source_mutation=false` and `journey_mutation=false`.
- It does not select foreground tickets by itself. AAR or the host must still
  apply visible-context, matched-terms-only, source-thickness, anti-nag, and
  permission guards before surfacing anything.
- Current tests live in `tests/aippocampus/test_reflection_space.py` and cover
  small graph rendering, merge/revive/abandon actions, recall-effect feedback,
  unsourced feedback suppression, and a fixture smoke.

Still not claimed: polished visualization, real user behavior change,
scheduler/AAR enforcement, calibrated suggestion timing, or any clean-source /
Journey-history mutation.

## TL;DR

用户需要一个与日常对话不同的空间——不是工作台，是地图室。
进入这个空间时，交互模式从"解决问题"切换到"看看走到了哪"。

这不是炫技的可视化，是让"同行者"关系变得**可感知**的界面。
如果用户永远看不到 Journey，那旅程追踪对用户而言就不存在。

同时，反馈机制应该由潜意识层事后完成，而不是让 agent 实时打分。
人类不会边走路边给自己打分——反馈是事后整合的。

## 为什么需要这个

### 问题一：Journey 对用户不可见

journey-tracking.md 设计了 Waypoint、Journey、current_frontier 等结构，
但这些都存在于 AIppocampus 的内部数据中。用户能感知到的只有：
- AAR 的 active gentle nudge（"你之前也碰过这个"）
- 显式 recall（"你还记得……"）

如果 AIppocampus 认为用户同时在走 5 段路，用户完全不知道。
从"用户建模"到"旅程追踪"的本体论转变，在用户侧是不可见的。

### 问题二：用户反馈没有锚点

journey-tracking.md 设计了 confirm/correct/merge/abandon/revive 五种反馈，
但用户需要**看到东西**才能判断"这个对不对"。对着抽象标签做反馈不可行。

### 问题三：agent 只在"工作模式"下交互

当前所有交互都在交易模式（你问我答）。但人有时候需要的不是答案，
是退后一步看看全景。没有这个空间，agent 的"轻声提到"就显得越界。

## 设计原则

1. **可选、按需进入**。不是默认界面，不是每次对话结束都弹出来。
2. **初期极简**。不需要 3D 星空。一个清晰的拓扑图就够了。
3. **可交互，不是纯展示**。用户能在上面做动作。没有交互的可视化才是炫技。
4. **空间切换=心智状态切换**。进入反思空间时，对话模式从工作向变成反思向。

## 可视化形态

### 初期：拓扑图

```
  [记忆连续性]          [推荐系统研究]
   traveling              camped
   屯→革→渐              屯→屯
      │                     │
      │   current_frontier  │
      └──"路会不会走失"──┘
              ?
      ┌──────────────┐
      │  [AIppocampus │
      │   架构设计]   │
      │   traveling   │
      │   屯→革→渐→咸 │
      └──────────────┘
```

- 路 = 线段，waypoint = 节点，current_frontier = 闪烁/高亮端点
- traveling = 实线，camped = 虚线，abandoned = 灰色
- 两条路之间的 `?` = dream amplification 检测到的潜在汇合点

### 远期：星空 / 星座

用户提到"星空图谱"——这个隐喻值得保留但不急于实现：
- Journey = 星座（一组有关系的星）
- Waypoint = 星
- current_frontier = 最亮的星（正在这里）
- camped 的路 = 暗淡但可见的星座
- 潜在汇合 = 星座之间的星云

先做拓扑图，验证交互模式成立后再考虑视觉升级。

## 交互模式

### 用户的动作

| 动作 | 效果 |
|------|------|
| 点击路 | 展开完整 waypoints、observations、source_refs |
| 拖拽两条路的端点靠近 | 向系统表达"这两段路可能有关"→ 触发 merge 检查 |
| 右键 camped 的路 → "继续" | revive Journey，agent 在下次对话时可以提到 |
| 右键 camped 的路 → "放下" | abandon Journey |
| 点击 frontier 上的 `?` | 触发 Dream prospective analysis：往这个方向探索会到哪 |
| 缩放 | 从全景（所有路）→ 细节（单条路的 waypoints） |

### Agent 的角色

Agent 在反思空间中不只是复述地图。它的价值来自 dream-task-design.md 的整合型任务：

| Dream 功能 | 反思空间中的体现 |
|-----------|----------------|
| Compensatory | "你注意到推荐系统研究这条路已经 camped 三周了吗？它和记忆连续性可能有关。" |
| Prospective | "记忆连续性的 frontier（路会不会走失）和架构设计的 frontier（感而遂通）指向同一个核心问题。" |
| Amplification | "这是第三次一条路在部署讨论后停下来了——这可能是一个模式。" |
| Active imagination | "如果把这两条路合在一起看，你可能在追问的是：AI 能不能在变化中保持人格。" |

如果 agent 只是复述"你现在有三条路，第一条在走，第二条停了"——反思空间就失败了。

### 交互模式切换

```
工作模式                          反思模式
─────────                        ─────────
"帮我调这段代码"                  "我们走到了哪？"
"这个函数怎么写"                  "这两条路是不是在追同一个问题？"
agent 回答问题                    agent 和用户一起看地图
AAR 提供 recall cards             Dream 提供 compensatory/prospective/amplification
recall 是背景音乐                 地图是前景
```

切换不是 UI 状态，是**心智状态**。用户需要明确的空间边界来告诉自己：
"现在我不是在解决问题，我是在看我们走到了哪。"

## 潜意识反馈机制

### 为什么不让 agent 实时打分

| 问题 | 显式打分 | 潜意识反馈 |
|------|---------|-----------|
| 认知负担 | agent 边做边评，打断流 | 事后分析，不打断 |
| 近因偏差 | 被"刚用到的 recall"绑架 | 有完整上下文再判断 |
| 谄媚风险 | agent 默认说"有用" | 无此问题 |
| 与 append-only 冲突 | 实时修改元判断 = thrashing | 追加观察，不修改历史 |
| 本体论一致性 | "同行者给自己打分"= 表演 | "事后回顾一起走过的路"= 整合 |

### 潜意识反馈做什么

subconscious job 在对话结束后分析完整上下文：

1. **recall 效果追踪**：AAR 注入的 recall card 出现后，对话的 frontier 是否发生了实质性偏移？
   不是"有没有被引用"（表面指标），而是"recall 出现前后，对话方向变了没有"（轨迹耦合度）。

2. **转折点检测**：哪轮对话之后 frontier 发生了显著变化？这不一定是 waypoint——
   可能是 agent 错过的、或者用户没有明确表达但实际发生的。

3. **错失的召回**：有没有某轮对话，如果 AAR 当时触发了 recall，可能会改变方向？
   这是 AAR 策略调整的输入。

4. **Dream 任务触发**：当潜意识层检测到"多条 Journey 的 frontier 指向同一盲区"时，
   触发 Dream 的 prospective analysis。

### 反馈闭环

Kimi 指出的关键遗漏：潜意识反馈不能只是审计日志，必须有调整 AAR 策略的通道。

```
subconscious job 分析对话
  → 检测到某类 recall 持续被忽略
    → 调整 AAR visibility：降低该类 recall 的 suggested_visibility
  → 检测到某类 frontier 频繁被触发但 recall 没跟上
    → 调整 AAR 触发敏感度：提升该类 frontier 的召回权重
  → 检测到转折点发生在 AAR 未触发时
    → 标记该 thread 需要 theme_emergence 重新扫描
  → 检测到多条 Journey 指向同一盲区
    → 触发 Dream prospective analysis
```

## 触发机制

反思空间不能变成无人进入的废墟。需要智能触发。

### 用户主动进入

最简单的方式。但大部分用户不会主动——他们不知道有这个东西。

### Agent 建议

compensatory analysis 可以检测到一个信号：
**用户长期处于 traveling 状态，没有 camped 的停顿。**

这时 agent 可以在对话中轻声提到：
> "我们最近一直在赶路。要不要退后一步，看看地图？"

这个触发条件应该是可配置的，不是硬编码的。

### 周期性触发

每周一次，Dream 任务完成后，如果产生了值得注意的 compensatory/prospective output，
可以在下次对话开始时提示用户进入反思空间。

## 与现有组件的关系

```
Journey Tracking (journey-tracking.md)
  → 提供数据：Journey, Waypoint, current_frontier
  → 反思空间可视化这些数据

Dream (dream-task-design.md)
  → 提供洞察：compensatory, prospective, amplification, active imagination
  → agent 在反思空间中呈现这些洞察
  → 潜意识反馈触发 Dream 任务

AAR (ambient-associative-recall.md)
  → 潜意识反馈调整 AAR 策略（visibility、触发敏感度）
  → 工作模式与反思模式有不同的 AAR 行为

Thread Intuition (affect-side-channel.md)
  → waypoints 的 hexagram arc 在地图上呈现为直觉层
  → 反思空间中 hexagram arc 可以被"解读"（与工作模式不同——
     工作模式用 don't-decode，反思模式可以主动探索直觉含义）
```

## 产品先例与教训

| 产品 | 借鉴 | 教训 |
|------|------|------|
| Obsidian Graph View | 概念图谱可视化 | 避免毛球图——必须展示特定 Journey，不是所有概念边 |
| Miro/Muse | 空间画布 | 空间记忆很强——把 thread 放在地图角落，几周后回来 |
| Arc Browser Spaces | 上下文切换 | 从聊天到地图应该是"退后一步看全景"的感觉 |
| NotebookLM | 结构化总结 + 探索 | 交互式问答 + 自动摘要的组合值得参考 |

## 风险

1. **过度浪漫化**：星空图谱很美，但用户需要的可能只是一个列表。
   先做拓扑图验证交互模式，再做视觉升级。

2. **Agent 复述地图**：如果 agent 在反思空间中只是读出 Journey 数据，
   用户还不如自己看地图。agent 的价值必须来自 Dream 的整合型任务。

3. **反思空间变成废墟**：如果没有人进入，再好的设计也没用。
   必须有智能触发机制。但也不能太 aggressive——用户不想被频繁建议"看地图"。

4. **潜意识反馈的因果幻觉**：post-hoc 分析可能把巧合当因果。
   缓解：潜意识反馈只影响置信度排序，不直接删除或修改 clean source。

5. **工作/反思模式切换的认知负担**：用户需要理解两种模式的不同。
   如果切换不够自然，用户会困惑"为什么 agent 突然开始说地图的事"。

## 实施优先级

| 阶段 | 内容 | 依赖 |
|------|------|------|
| P1 | 潜意识反馈机制（subconscious job 分析 recall 效果、转折点） | implemented as deterministic source-ref-carried adjustments |
| P2 | 反馈→AAR 策略的闭环 | implemented as advisory ranking/confidence/visibility adjustment records |
| P3 | 反思空间 MVP：拓扑图 + 用户动作（点击展开、merge、revive/abandon） | implemented as inspectable topology data, not polished UI |
| P4 | Agent 在反思空间中的行为（Dream 洞察呈现） | P3 + Dream |
| P5 | 智能触发机制（compensatory 驱动的"看地图"建议） | P4 |
| P6 | 视觉升级（星空/星座隐喻） | P3，验证交互模式后 |

先做 P1-P2（潜意识反馈闭环），再做 P3（最小可视化），P4-P6 按需。

## Review Credits

**用户 (2026-05-28):**
"是不是得留一个接口给主 agent 做反馈。" → "这可以由潜意识层来做，像人类不会主动打分。"
→ "可以有一个认知地图可视化，用户来到这一层，默认交互就不是工作向了，可以一起 reflect 或回顾。"

**kimi-reviewer (2026-05-28):**
显式打分是反模式。可视化反思空间是真实需求——核心价值是让"同行者"关系有感知界面。
三个遗漏：agent 在反思空间中的角色契约、潜意识反馈→AAR 策略闭环、反思空间的智能触发时机。
"如果没有可视化，从'用户建模'到'旅程追踪'的转变对用户而言就是**不存在的**。"

**gemini-researcher (2026-05-28):**
潜意识反馈更 robust，但要注意因果幻觉和反馈延迟。
反思空间的核心价值是状态切换——从交易模式到反思模式。
Agent 在反思空间中的价值完全取决于 Dream 的整合型任务。
产品先例教训：避免 Obsidian 毛球图、利用 Miro 空间记忆、参考 Arc Browser 切换感。
