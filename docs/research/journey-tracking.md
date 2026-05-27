# Journey Tracking: AIppocampus 的旅程追踪

Status: research memo, v4 after 3 rounds of review.
Origin: user observation + Claude research, 2026-05-28.
Related: [dream-task-design.md](dream-task-design.md) — 不 impose 叙事结构，但 recognize 旅程模式,
[affect-side-channel.md](affect-side-channel.md) — hexagram arc 作为直觉编码,
[ambient-associative-recall.md](ambient-associative-recall.md) — AAR 管线,
[compact-activation-signals.md](compact-activation-signals.md) — cognitive portrait 概念.

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

Journey **不是默认容器**。只有 `theme_emergence` 检测到连贯的多线程线索时才实例化。
单次工具性交互（"帮我调这段代码"）不产生 Journey。

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

**current_frontier**：由 LLM 从最新的 1-3 个 waypoint 推断，描述"现在停在哪"。
不是整个旅程的总结，只是当前位置。

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

1. `theme_emergence` 检测到一个 theme 跨 ≥3 个 thread 出现
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

6. **camped 状态的边界**：
   什么时候算 camped（扎营，暂停后可能继续）vs abandoned（放弃了）？
   当前用过期时间硬切。但有些路可能暂停几个月后又捡起来。
   用户 revive 机制兜底。

## 实施计划

| 阶段 | 内容 | 依赖 | 工时 |
|------|------|------|------|
| P1 | Waypoint + Journey dataclass + 状态转移 + 过期 | theme_emergence | 2 天 |
| P2 | Journey 实例化逻辑（≥3 thread + LLM 连贯性检查） | P1 | 1 天 |
| P3 | current_frontier 生成（从最新 waypoint 推断） | P1 | 0.5 天 |
| P4 | 与 question_tracking 关联 | P1 | 0.5 天 |
| P5 | 用户反馈通道 | P1 | 1 天 |
| P6 | 图随机游走（prospective scouting + path resonance） | concept_edge_mining | 1 天 |

先做 P1-P3（Journey 核心），P4-P6 按需。

## 评估：时间切分回放

1. 取 Day T 的 Journey 快照
2. 取 Day T 到 T+14 的实际对话
3. Day T 的 current_frontier 描述的"岔口"，在 T+14 是否被用户实际探索？
4. Day T 标记为 traveling 的 Journey，两周后是否仍在走？
5. Day T 标记为 camped 的 Journey，两周后是否被 revive 或 abandon？

这是离线评估，不需要金标注。测试的是 Journey 对"路在往哪走"的追踪精度。

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
