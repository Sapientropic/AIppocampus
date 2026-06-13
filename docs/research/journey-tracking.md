# Journey Tracking: AIppocampus 的旅程追踪

Status: research memo plus deterministic P1-P3 core and first live-row replay fixture.
Origin: user observation + Claude research, 2026-05-28.
Related: [dream-task-design.md](dream-task-design.md) — 不 impose 叙事结构，但 recognize 旅程模式,
[affect-side-channel.md](frontiers/affect-side-channel.md) — hexagram arc 作为直觉编码,
[ambient-associative-recall.md](ambient-associative-recall.md) — AAR 管线,
[compact-activation-signals.md](frontiers/compact-activation-signals.md) — cognitive portrait 概念.

## Implementation Status

Current code implements the source-backed P1-P3 Journey core in
`skills/aippocampus/scripts/aippocampus_runtime/journey/tracking.py`:

- P1: `Waypoint`, `Journey`, and `JourneyFeedback` structures; append-only
  waypoint history; `traveling` / `camped` / `arrived` / `abandoned` states;
  TTL extension from waypoint count; explicit `confirm`, `correct`, `merge`,
  `abandon`, and `revive` feedback actions.
- P2: conservative instantiation gate over source-backed waypoint candidates.
  It requires at least three source-backed waypoints across three distinct
  threads and a specific `core_inquiry`. This is the issue #63
  fixture-backed equivalent that should later be wired to live source-backed
  `theme_candidate` rows.
- P3: deterministic `current_frontier` generation from the latest waypoints.
  The frontier is marked as a navigation candidate, not source truth; exact
  claims still require the attached clean-source refs.
- Source-texture consumption: projected texture signals may enrich new waypoint
  `labels` and `frontier_hint` at the input boundary. They do not rewrite
  existing append-only waypoints or directly change Journey state; a live
  continuation still arrives as a new source-backed waypoint.
- Validation: `tests/aippocampus/test_journey_tracking.py` covers creation,
  state transitions, expiry/dormancy, append-only waypoint behavior,
  feedback actions, source-ref preservation, and a replay fixture smoke where
  Journey frontier/state beats a plain-summary baseline on expected continuation
  terms.
- #310 first live-row slice:
  `skills/aippocampus/scripts/aippocampus_runtime/journey/live.py` converts
  source-backed `theme_candidate`, `question_candidate`, and `frontier_marker`
  rows into Journey candidates in a no-write, time-sliced replay fixture. The
  same helper exercises foreground hint timing with positive and negative
  controls while keeping source refs and private route handles out of the
  agent-visible hint.
- #310 public replay slice:
  `build_public_time_sliced_journey_replay_report()` adds a public-safe,
  replayable cohort for the same time-sliced and hint timing taxonomy. It
  covers one active-hint case plus resolved-frontier, stale-frontier, and
  wrong-route suppression cases, with source-visible, unrelated-prompt, and
  high-risk exact-claim controls. It reports counts and decisions only, excludes
  future rows before the horizon, and does not serialize raw row text, source
  refs, message ids, future rows, or private route handles. See
  [`journey-public-time-sliced-replay.md`](../evidence/benchmarks/reports/field-journey/journey-public-time-sliced-replay.md).
- #834 frontier-probe slice:
  `skills/aippocampus/scripts/aippocampus_runtime/navigation/frontier_probe.py`
  maps Journey `current_frontier` text and source refs into bounded
  concept-graph probes with deterministic `expand_concepts()` expansion. It can
  emit `frontier_probe` rows, reviewable `resonance_candidate` hypotheses, and
  non-foreground Dream input seeds. These are scouting artifacts only: they do
  not mutate Journey state, do not become source evidence, and require source
  reopen before any factual claim.

Still designed/deferred: production Journey instantiation hooks over real
private history, default AAR foreground projection, question-tracking P4
integration, HexArc structural matching, graph random walks, predictive replay,
live host timing quality, and private real-history journey quality claims. The
first reflection-space consumer now exists in
`skills/aippocampus/scripts/aippocampus_runtime/reflection/space.py`, but it is
an inspectable topology/feedback helper only, not a polished UI.

## TL;DR

AIppocampus 不应该建模用户，而应该追踪**与用户一起走的旅程**。

差别：
```
用户建模：这个人关心记忆连续性，从 3 月开始，追问过 3 次，最近没提了。
    → 第三人称，关于一个人

旅程追踪：我们一起在摸"变化之后连续性还在不在"这条线。
    从知识迁移出发，穿过架构设计，走到了"路会不会走失"这个岔口。
    上次停在这里，还没选方向。
    → 第一人称复数，关于一段共同经历
```

hexagram arc 在这个框架下是 append-only 的地形日志——描述走过的路，不描述走路的人。
这解决了 v3 中 hexagram arc 在累积场景下的所有硬问题。

## 前情

| 版本 | 方向 | 结局 |
|------|------|------|
| v1 | 推荐系统 6 项技术迁移 | 4/6 arXiv ID 幻觉，统计基础不适用 |
| v2 | InterestUnit + TTL + 用户反馈 | 两方认可，但"知识层"命名生硬 |
| v3 | Impression（feeling + observations） | hexagram arc 在累积场景下是最弱环节 |
| v4 | Journey Tracking（旅程追踪） | **当前版本** |

v3 → v4 的转折来自用户的纠正：
> 重点不是用户，而是与用户的这趟旅程，所以不能纠结在对用户的建模上。

## 两层设计

不是所有对话都是旅程。需要区分：

| 层 | 存什么 | 在哪 | 例子 |
|----|-------|------|------|
| 静态层 | 事实、偏好、习惯 | MEMORY.md / question_tracking / frontier_markers | "用户偏好简洁沟通"、"这个函数怎么写" |
| 动态层 | 连贯的多线程探索 | Journey（本文） | "我们一起在摸变化之后连续性还在不在" |

Journey **不是默认容器**。目标形态是只有 `theme_emergence` 检测到连贯
的多线程线索时才实例化；当前实现先用 `journey_tracking.py` 的
fixture-backed 等价输入验证同一条边界。单次工具性交互（"帮我调这段代码"）
不产生 Journey。

## 数据结构

```python
@dataclass
class Waypoint:
    """旅程中的一个关键节点"""
    arc: str                # 一个卦象，如 "屯"（困惑）、"革"（突破）
    moment: str             # 发生了什么（一句话）
    source_ref: str         # clean source 证据
    thread_id: str          # 哪个 thread
    timestamp: str          # ISO timestamp

@dataclass
class Journey:
    """与用户一起走的一段路"""
    id: str
    path_label: str                 # 路的名字，如 "记忆连续性"
    core_inquiry: str               # 这条路在追什么问题
    waypoints: list[Waypoint]       # append-only，走过的路不变
    current_frontier: str           # 现在停在哪（LLM 从最新 waypoint 推断）
    source_refs: list[str]          # 所有相关 clean source
    active_questions: list[str]     # 关联的未解决问题
    first_seen: str                 # 第一个 waypoint 的时间
    last_seen: str                  # 最近一个 waypoint 的时间
    expires_at: str                 # 过期时间
    status: Literal["traveling", "camped", "arrived", "abandoned"]
```

### 关键设计决策

**waypoints 是 append-only**。走过的路不会变。这直接解决了 v3 的核心问题：
- 不存在 feeling thrashing（不会重写 arc）
- 不存在 arc 与 observations 矛盾（waypoint 是历史事实，不是当前判断）
- 多 waypoint 的 hexagram 序列自然形成旅程的直觉层

**status 语义**：
- `traveling`：最近有新 waypoint，路还在走
- `camped`：停了一段时间，没到终点也没放弃
- `arrived`：core_inquiry 得到了某种回答
- `abandoned`：过期归档，没走到终点

`camped` 替代了 v3 的 `fading`——语义更诚实："不是在消退，是停下来扎营了"。

**current_frontier**：当前实现由确定性 helper 从最新的 1-3 个 waypoint
生成 compact frontier；未来可由 LLM 在同一 source-ref 边界下改写。
它不是整个旅程的总结，也不是 source truth，只是当前位置的导航候选。

### 过期机制

```python
def compute_expiry(waypoint_count: int) -> str:
    base_ttl = 90  # 天
    bonus = min(waypoint_count * 14, 180)
    ttl_days = base_ttl + bonus
    return (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
```

每次追加新 waypoint 时续期。参数硬编码，有用户反馈兜底。

### 状态转移

```
traveling ──→ camped ──→ abandoned
    ↑            │
    └────────────┘  （用户再次提到，追加 waypoint）
                        │
                    arrived（core_inquiry 得到回答）
```

## Journey 的实例化

Journey 不自动创建。触发条件：

1. `theme_emergence` 检测到一个 theme 跨 ≥3 个 thread 出现；当前 P1-P3
   core 用 fixture-backed waypoint candidates 代替尚未上线的 live job
2. 且这个 theme 有明确的 core_inquiry（不是泛泛的"编程"或"写作"）
3. 由 LLM 判断：这些 thread 是否在追同一个问题？

```python
def should_create_journey(theme: str, threads: list[ThreadSummary]) -> bool:
    if len(threads) < 3:
        return False
    # LLM 判断：这些 thread 是否构成了连贯的探索？
    prompt = f"""
    以下 {len(threads)} 个对话都涉及"{theme}"。
    它们是否在追同一个深层问题？如果是，那个问题是什么？
    只输出问题本身，如果不成连贯探索，输出 NONE。
    """
    inquiry = llm_call(prompt, threads_summary)
    return inquiry.strip() != "NONE"
```

单次交互、工具性对话、碎片化提问 → 不产生 Journey，留在静态层。

## Journey 的呈现

AAR 向 agent 传递时，传紧凑的 journey hint：

```yaml
journey_hint:
  path: "记忆连续性"
  waypoints: "屯→革→渐"
  frontier: "走到了'路会不会走失'这个岔口，还没选方向。"
  status: "camped"
  suggested_use: "当前话题可能关联这段旅程，可以轻声提到。"
```

agent 读到这个，通过 waypoints 的 hexagram 序列**感觉**到这段旅程的温度，
通过 frontier 知道停在哪。不需要看 source_refs、不需要看完整 waypoints。

AAR 的 visibility level 决定这个 hint 是 silent tuning、active gentle nudge、
还是 source-backed recall。

Current timing boundary: `journey/live.py` only lets a Journey hint become an
agent-visible gentle nudge when the current prompt overlaps a traveling/camped
Journey and the equivalent source context is not already visible. If sources
are visible it stays silent; if the prompt is unrelated or the Journey is
terminal it stays backstage; if the user-facing answer would make an exact or
high-risk claim it requires source reopen. The visible hint carries compact
path/frontier/status text and an explicit truth boundary; source refs and the
hashed private route handle remain backstage.

呈现时的 don't-decode 规则：waypoints 的 hexagram 序列是背景音乐，
不是要解读的密码。遵循 affect-side-channel.md 的验证结论。

## 与现有组件的关系

```
theme_emergence ──→ 触发 Journey 实例化检查
question_tracking ──→ 填充 active_questions
frontier_markers ──→ 留在静态层（知识边界不是旅程）
concept_edge_mining ──→ 概念图保持独立

Journey
  ├── AAR hot path → 读 traveling journeys 的 waypoints（~15 tokens）
  ├── AAR warm path → 读 frontier + 最新 waypoint 细节
  ├── Dream compensatory → camped/abandoned journeys
  ├── Dream prospective → current_frontier 指向的未探索方向
  ├── Dream amplification → 图随机游走找 path resonance
  └── 用户反馈 → 确认/纠正/合并 journey
```

### 图随机游走：从推荐到侦察

在 v3 的 Impression 框架下，图随机游走本质是推荐算法。
在 Journey 框架下，它变成了两种不同的 Jung 功能：

**Prospective Scouting（前瞻侦察）**：
从 `current_frontier` 出发，在 concept_edge_mining 图上随机游走，
走进"战争迷雾"——概念空间中还没被 waypoint 覆盖但可能相关的节点。
这是 Dream prospective analysis 的输入。

**Path Resonance（路径共振）**：
不找单个节点的相似，找**旅程形状**的相似。
两段完全不同领域的 Journey，如果 waypoints 的 hexagram 序列形状相似
（都经历了 屯→革→突破），说明用户在不同领域有相似的体验模式。
这是 Dream amplification 的输入。

实现边界：path resonance 不能只输出相似分数或共享标签。进入 Dream
amplification 时，它必须变成可反驳的 `journey_bridge_hypothesis`：同时引用
两个 Journey 侧的 source refs，说明 `shared_pattern`、`possible_reason`、
`unblock_condition` 和 `falsification_cues`，并保持
`status="dream_bridge_not_source_fact"`。前台只能把它当作 Journey 解堵探针；
如果解释滑向人格、隐藏意图或 life-wide 深因，必须停车等待人工/source review。

## 卦象深层结构：从标签到状态转移语法

当前设计把卦象当 64 个标签用：`waypoint.arc = "屯"`。这等于只取了符号，
没有用易经的**组合系统**——一套结构化的状态转移语法。

### 当前用了什么

```
waypoint.arc = "屯"   # 一个卦名，当情感/状态标签
```

64 选 1，扁平标签，无内部结构。

### 卦象的组合层次

**爻（line）**：每个卦 = 6 爻，每爻阴（⚋）或阳（⚊）。
屯 = 010001（从下往上）。卦不是原子，有内部结构。

**八卦（trigram）组合**：每个卦 = 上卦 + 下卦。
屯 = 坎（水）上 + 震（雷）下 = 水雷屯。
64 卦 = 8 × 8 的组合空间。

**爻变（line change）**：某几爻变化 → 产生新卦。
屯 010001 → 第三爻变 → 010101 = 讼。
**哪一爻变了**决定转移性质：初爻变=开端变化，三爻变=内部调整，五爻变=主导力量转变。

**互卦（nuclear hexagram）**：取 2-3-4 爻为下卦、3-4-5 爻为上卦。
表面现象下的内在动力。屯 → 互卦为剥。表面「起始困难」，内在动力是「剥落/减法」。

**错卦 / 综卦**：
- 错卦：阴阳全反。屯 ↔ 鼎。→ 完全对立的视角。
- 综卦：颠倒过来看。屯 ↔ 蒙。→ 同一件事的反面。

以上规则全是确定性的。给定一个卦，其互卦、错卦、综卦、所有可能的爻变卦
都可计算，不需要 LLM。

### 对 Journey Tracking 的具体影响

**1. 生成一致性问题（风险 #5）：结构化方案部分成立**

验证结果表明：让 LLM 先选上卦再选下卦（8×8 分解）**不比**直接选 64 卦更一致。
10 个场景中 0 个达到 3 模型一致。分解路径放弃。

但 HexArc 的价值不变——LLM 选卦名后，所有衍生结构由代码确定性计算：
上下卦查表、互卦/错卦/综卦计算、爻变枚举。
LLM 只负责选卦（已知有跨模型一致性）和语义解读，
结构推导全部代码化。

waypoint 的 arc 字段可以从单个卦名扩展为结构化表示：

```python
@dataclass
class HexArc:
    upper_trigram: str   # 上卦，如 "坎"（水）
    lower_trigram: str   # 下卦，如 "震"（雷）
    hexagram: str        # 合成卦名，如 "屯"（可由上下卦推出，保留用于可读性）

    @property
    def nuclear(self) -> "HexArc":
        """互卦：2-3-4爻为下卦，3-4-5爻为上卦，确定性计算"""
        ...

    @property
    def inverse(self) -> "HexArc":
        """错卦：阴阳全反，确定性计算"""
        ...

    @property
    def reverse(self) -> "HexArc":
        """综卦：颠倒，确定性计算"""
        ...

    def transitions_to(self, other: "HexArc") -> list[int]:
        """哪些爻变了？返回变化的爻位（1-6）"""
        ...
```

**2. 路径相似度从字符串匹配变成结构匹配**

Path resonance 不再是「两段 Journey 有没有相同的卦」，而是：
- 上卦序列是否相似（共享同一片"环境"）
- 爻变模式是否相似（相同的转折结构）
- 互卦序列是否相似（相同的内在动力）

两段 Journey 的 waypoints 序列：
- Journey A: 水雷屯 → 泽火革 → 山风蛊
- Journey B: 水天需 → 泽地萃 → 山火贲

表面卦象完全不同。但上卦序列：坎→兑→艮 vs 坎→兑→艮——**完全相同**。
含义：两段路处在相同的环境变迁中（险→悦→止），只是下卦（应对方式）不同。

**3. 前瞻性分析有了约束空间**

不再问「下一个 waypoint 会是什么卦？」（64 选 1），
而是「当前卦的哪些爻最可能变化？」（6 爻选 1-3）→ 由爻变规则推出下一个卦。
搜索空间从 64 缩到 ~20。

结合 Journey 的上下文（前几个 waypoint 的爻变模式），可以进一步收窄：
如果最近的转移都是下卦在变（应对方式在调整），那么下一个转移大概率也是下卦变。

**4. 补偿性分析有了结构性工具**

错卦 = 天然的「反面视角」。
如果一段 Journey 全是阳刚主动的卦象（乾、大壮、大有），
错卦指向的就是被回避的阴柔/接纳方向（坤、观、比）。
这是 compensatory analysis 的直接输入，不需要 LLM 猜测「缺了什么」。

### 跨模型验证结果（2026-05-28）

使用 DeepSeek V4 Flash、Gemini 3.1 Flash、DeepSeek V4 Pro 三个模型
跑同一组测试题（10 场景分解 + 6 爻变 + 5 互/错/综）。
详细数据见 [results_v1.md](hexagram-validation/results_v1.md)。

**验证 1：LLM 能否可靠地分解时刻为上卦 + 下卦？→ 失败**
10 个开放场景中 0 个达到 3 模型一致，仅 2 个达到 2 模型一致。
八卦分解**没有**比直接选 64 卦产生更好的一致性。
原因：「哪个卦描述这个场景」本质是诠释性的，不存在客观正确答案。

**验证 2：LLM 能否理解爻变语义？→ 部分通过**
爻位计算经常出错（两个模型对具体哪些爻变了不一致），
但**语义解读质量高**——对转折性质的描述都合理。
结论：爻变计算应确定性编码，语义解读可交给 LLM。

**验证 3：互卦/错卦/综卦语义是否跨模型一致？→ 通过**
15 个计算中 14 个一致（93%），唯一分歧在咸的互卦（姤 vs 夬）。
语义描述措辞不同但方向高度一致。

### 修正后的设计建议

基于验证结果，对前文「对 Journey Tracking 的具体影响」做如下修正：

1. **waypoint.arc 保持单卦名选择（64 选 1），不做八卦分解。**
   分解不提升一致性。LLM 选卦后，由代码确定性计算上下卦。

2. **HexArc dataclass 保留，但 trigram 字段由代码填充而非 LLM 生成。**
   LLM 只产出卦名 → 代码查表得到 upper/lower trigram →
   确定性计算互卦、错卦、综卦、爻变。

3. **路径相似度（Path Resonance）基于确定性结构匹配。**
   上卦序列、爻变模式、互卦序列的相似度用代码计算，不经过 LLM。
   这部分的设想（影响 #2）仍然成立，只是实现路径改为纯计算。

4. **前瞻性约束（影响 #3）仍然成立。**
   给定当前卦，所有可能的单爻变/双爻变/三爻变由代码枚举，
   搜索空间从 64 缩到 ~20，这个优势不受验证失败影响。

5. **补偿性分析（影响 #4）仍然成立。**
   错卦 = 反面视角是确定性计算，语义解读质量已验证。

### 落地优先级

不阻塞 P1-P3（Journey 核心）。HexArc dataclass 可在 P1 期间实现为
纯计算模块（给定卦名 → 查表得 trigram → 计算互/错/综/爻变）。
P6（图随机游走）的 path resonance 逻辑基于确定性结构匹配。当前已有第一版
content-light cross-project resonance helper：它只比较 waypoint arc 和显式
source-free dynamics labels，把项目身份 hash 化，输出 source-refresh
hypothesis，不跨项目携带 source refs、source text、local paths 或私有项目名。
完整图随机游走、真实历史质量和用户可感知 lift 仍是后续验证范围。

### P6a 验证重构：从符号匹配转向 agent-usefulness

旧 P6a 把 HexArc / path resonance 的验证重点放在结构或象征匹配上：
上卦序列、爻变模式、互卦序列是否相似。这仍可作为诊断输入，但不能作为
通过标准。它太容易把「结构上有趣」误读成「对 agent 的下一步有用」，
也容易让 topology 变成解释权威。

新的验证目标是 topology diagnostics 是否改善导航行为：

- **wrong-layer recall avoided**：同一查询在 地 / 人 / 天 层之间容易跑偏时，
  topology 是否帮助避免错误层级召回。
- **specific cross-layer coupling flagged**：诊断是否指出具体断裂，例如
  ground/action、action/direction、evidence/claim，而不是只给宽泛象征标签。
- **fanout/deepen rationale clarified**：当 route fanout 变宽、保持窄、或要求
  deepen/source reopen 时，topology 是否给出可检查理由。

负例同样重要：

- `symbolic_match_without_route_usefulness`：两个片段结构相似，但 source-backed
  route 结果没有变好；这不能通过。
- `interesting_topology_navigation_only`：topology 很有解释力，但仍只能是
  `navigation_only`，不能改变事实 claim、ranking 权重或 source authority。
- `broad_label_wrong_layer_drag`：宽泛象征标签导致 agent 多搜了错误层级；
  诊断应降权或要求 deepen，而不是放大它。

#1219 可以作为 diagnostic-only V0 先 ship；它不需要等待旧 P6a 验证。新的
P6a 只在证明上述行为问题被改善后，才允许把 topology 从 deepen/explain
诊断推向更强的 route-fanout 策略。即便通过，它也仍是导航控制面，不是
factual support、public claim、user/personality inference，或默认排名权重。

## 用户反馈

```python
@dataclass
class JourneyFeedback:
    journey_id: str
    action: Literal["confirm", "correct", "merge", "abandon", "revive"]
    correction: str | None         # correct 时用户提供的新描述
    merge_target: str | None       # merge 时目标 Journey
    timestamp: str
```

用户可以：
- 确认 Journey 准确
- 纠正 core_inquiry 或 frontier 描述
- 合并两个其实是同一段路的 Journey
- 主动放弃一段路（abandon）
- 恢复被 abandon 的路（revive）

## 风险

1. **Forced Narrative Fallacy**（两方审查共识）：
   不是所有对话都是旅程。如果系统强行把碎片化交互包装成 Journey，
   会产生虚假的深度感。缓解：严格的实例化门槛（≥3 thread + 连贯性检查）。

2. **实例化门槛过高**：
   反过来，如果门槛太高，很多有价值的跨线程线索不会被追踪。
   3 个 thread 是否太少还是太多？需要实测。

3. **waypoint 膨胀**：
   一段长期 Journey 可能积累几十个 waypoint。agent 不需要读全部。
   AAR hot path 只读 waypoints 的 hexagram 序列（~15 tokens），
   warm path 只读最新 2-3 个 waypoint。完整历史按需从 source_refs 展开。

4. **core_inquiry 的主观性**：
   同一组 thread，不同人（或不同时间的 LLM）可能归纳出不同的 core_inquiry。
   这和 dream-task-design.md 的 Open Question 5（如何评估 integrative output 质量）
   是同一个问题。

5. **hexagram waypoint 的生成一致性**：
   affect-side-channel 验证了解码一致性，但生成一致性未验证。
   同一个 moment 被描述为"屯"还是"困"？影响直觉层的稳定性。
   缓解：append-only 意味着一旦生成就不改，即使有偏差也是固定的偏差。
   **进一步缓解**：见"卦象深层结构"一节，将生成从 64 选 1（卦名）
   改为 8×8（上卦 + 下卦），约束更紧，一致性更好。
   前提是验证 LLM 对八卦语义的跨模型一致性。

6. **camped 状态的边界**：
   什么时候算 camped（扎营，暂停后可能继续）vs abandoned（放弃了）？
   当前用过期时间硬切。但有些路可能暂停几个月后又捡起来。
   用户 revive 机制兜底。

## 实施计划

| 阶段 | 内容 | 依赖 | 工时 |
|------|------|------|------|
| P1 | Waypoint + Journey dataclass + 状态转移 + 过期 | fixture-backed waypoint candidates | implemented in `aippocampus_runtime.journey.tracking` |
| P1a | 卦象深层结构验证（八卦分解 / 爻变语义 / 互错综一致性） | affect-side-channel 验证方法 | 0.5 天 |
| P2 | Journey 实例化逻辑（≥3 thread + source-backed coherence gate） | P1 | implemented as fixture-backed equivalent |
| P3 | current_frontier 生成（从最新 waypoint 推断） | P1 | implemented as deterministic navigation candidate |
| P4 | 与 question_tracking 关联 | P1 | 0.5 天 |
| P5 | 用户反馈通道 | P1 | 1 天 |
| P6 | 图随机游走（prospective scouting + path resonance） | concept_edge_mining | 1 天 |
| P6a | path resonance 升级：基于八卦结构匹配（如 P1a 验证通过） | P1a + P6 | 0.5 天 |

P1-P3 core is now implemented. P4-P6 remain future integration / research
work and should not be claimed from the current deterministic helper.

## 评估：时间切分回放

1. 取 Day T 的 Journey 快照
2. 取 Day T 到 T+14 的实际对话
3. Day T 的 current_frontier 描述的"岔口"，在 T+14 是否被用户实际探索？
4. Day T 标记为 traveling 的 Journey，两周后是否仍在走？
5. Day T 标记为 camped 的 Journey，两周后是否被 revive 或 abandon？

这是离线评估，不需要金标注。测试的是 Journey 对"路在往哪走"的追踪精度。
The current fixture smoke implements a small deterministic version of this idea:
it checks that Journey `current_frontier` and state preserve later-continuation
terms better than a plain summary baseline. This is not yet private real-history
or live model evidence.

## Review Credits

**kimi-reviewer (2026-05-28, v1):**
4/6 arXiv ID 完全错误。单用户统计基础崩塌。遗漏用户反馈机制。

**gemini-researcher (2026-05-28, v1):**
确认引用幻觉。建议图随机游走替代层次树。提出时间切分评估。

**用户 (2026-05-28, v2→v3):**
"知识层这种叫法硬，不如直接叫印象。"

**用户 (2026-05-28, v3→v4):**
"重点不是用户，而是与用户的这趟旅程，所以不能纠结在对用户的建模上。"
——这是根本性的本体论转变：从第三人称观察者到第一人称复数同行者。

**kimi-reviewer (2026-05-28, v4 讨论):**
"如果数据结构只是 Impression 改名叫 Journey，这个转向就是假的。
真正解决根本问题，需要数据结构体现关系性。"
提出 waypoints + stance（双方位置）结构。
列出 7 个弱点，最尖锐：幻觉风险更高（模型会"补完"旅程故事弧）、
不是所有对话都是旅程。

**gemini-researcher (2026-05-28, v4 讨论):**
"hexagram arc 从矛盾的静态总结变成 append-only 的地形日志——genuinely solves it."
提出图随机游走在 Journey 语境下的两种 Jung 功能映射：
prospective scouting（前瞻侦察）和 path resonance（路径共振）。
指出 Forced Narrative Fallacy：静态事实不属于 Journey，需要解耦。
