# AIppocampus Browser Extension 设计文档

> 状态：概念验证阶段 | 创建：2026-05-27 | 触发：知乎文章「你愿意死后让亲友用 AI 复活自己吗」
>
> Source boundary: this is a product/design working note. Competitive stats,
> browser DOM/API details, and third-party project status are research leads
> until re-verified from primary sources before implementation or publication.

## 1. 缘起

知乎用户「一只狗kenny」描述了一个精确的痛：

> 他让 Claude 把一个窗口里打磨出的合作经验整理成 SKILL，放到新窗口用。新窗口能用架构，但不记得架构是怎么长出来的。他说这像阿尔茨海默病——能凭本能去爱，但忘了共同走过的路。

这个痛点不是个案，而是所有网页端 LLM 用户的日常。CLI 用户有 AIppocampus，但 99% 的用户在网页端聊天——他们没有跨会话记忆。

**核心洞察**：与其让扩展自己做「要不要召回」的决策（AIppocampus CLI 版的 900 行规则引擎），不如暴露 `memory_search` / `memory_save` 工具给 LLM，让 LLM 自己决定什么时候回忆、搜什么、怎么用结果。

## 2. 竞品地图（调研草稿，待源核验）

### 已有项目

| 项目 | 类型 | 做了什么 | 没做什么 |
|------|------|----------|----------|
| Supermemory (23K★) | 云端记忆 | 云端存储 + 多平台注入 | 依赖后端、不本地优先、不保留原文 |
| Mem0 / OpenMemory (54K★) | 云端 + 扩展 | 事实提取 + 注入 | Chrome 扩展已归档、摘要代替原文 |
| Kept (80★) | 扩展 + 桌面 | Markdown 归档 + SQLite FTS5 + 知识图谱 | 有搜索但无自动注入 |
| LokulMem | 浏览器库 | 纯浏览器端 IndexedDB 记忆层 | 功能极简，无脱敏、无召回决策 |
| Aether | Chrome 扩展 | 100% 本地（Chrome Summarizer API + transformers.js 向量） | 自动提取偏好但注入方式是气泡按钮 |
| Context-Sync | Chrome 扩展 | 跨平台上下文移植（自动注入+发送） | 无脱敏、无决策、全量注入 |
| HAEVN (15★) | 扩展 | 10+ 平台、TypeScript 严格模式、82 个 message handler | 纯存档，不注入 |
| hippo-memory | CLI + MCP | 生物启发记忆（衰减/强化） | 不是浏览器扩展 |

### 市场空白

**没有一个项目同时做到**：
1. 本地优先（所有数据在浏览器 IndexedDB）
2. 原文保留（不摘要替代）
3. 智能脱敏（凭据、路径、注入指令过滤）
4. LLM 自驱召回（不是扩展规则决定，而是 LLM 自己调 tool）
5. 跨会话注入（新对话自动可记忆）

## 3. 核心架构：LLM-as-Brain + Extension-as-Tool-Server

### 设计哲学

CLI 版 AIppocampus 的架构是「确定性优先，LLM 仅用于模糊地带」。浏览器版反过来：

- **LLM 是大脑**：召回决策由 Claude 自己做出（它天然知道什么时候该回忆）
- **扩展是工具服务器**：只提供 memory_search / memory_save 两个工具
- **确定性守门**：脱敏、截断、去重仍由扩展强制执行

### 数据流

```
用户输入 → Claude.ai 发送 completion 请求
         → 扩展拦截请求，注入 tools 参数（或 prompt 层虚拟工具定义）
         → Claude 判断需要回忆 → 输出 tool_use: memory_search(query="脚本架构")
         → 扩展拦截响应，检测 tool_use
         → 本地 IndexedDB 搜索 → 脱敏 → 截断
         → 扩展构造 tool_result 注入回对话流
         → Claude 拿到搜索结果，继续回复
```

### 组件清单

```
┌─────────────────────────────────────────────────┐
│           Chrome Extension (MV3)                 │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  Content Script (claude.ai)             │    │
│  │  ├── 对话捕获：轮询内部 REST API        │    │
│  │  │   GET /api/organizations/{id}/        │    │
│  │  │       chat_conversations/{id}         │    │
│  │  ├── UI 注入：记忆状态指示器             │    │
│  │  └── fetch monkeypatch（main world）     │    │
│  │      ├── 拦截请求 → 注入 tools          │    │
│  │      └── 拦截响应 → 检测 tool_use       │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  Background Service Worker              │    │
│  │  ├── 脱敏管线（移植自 AIppocampus）     │    │
│  │  ├── MiniSearch 全文索引               │    │
│  │  ├── IndexedDB 持久化                   │    │
│  │  └── tool 执行引擎                      │    │
│  │      ├── memory_search(query, max)      │    │
│  │      └── memory_save(key, content)      │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  Side Panel                             │    │
│  │  ├── 记忆浏览（搜索、时间线）           │    │
│  │  ├── 隐私设置（哪些对话纳入记忆）       │    │
│  │  └── 索引健康状态                       │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## 4. Tool Call 的三种实现路线

### 路线 A：API 层注入 tools 参数（最干净）

往 `/completion` 请求的 body 里注入 `tools` 字段，Claude 原生 tool use。

- **优势**：Claude 原生支持，格式可靠，thinking 中能看到推理过程
- **风险**：Claude.ai 前端可能不认识自定义 `tool_use` 响应，需要同时补丁 frontend handler
- **实现**：main world 脚本 monkeypatch `fetch`，拦截 `/completion` 请求和 SSE 响应

### 路线 B：Prompt 层虚拟工具（最稳）

在对话开头注入虚拟工具定义，Claude 通过输出特定 XML 标签"调用工具"。

```
[Memory System Active]
你可以使用以下工具：

<memory_search query="搜索词" />
→ 返回之前对话中的相关内容片段

<memory_save key="主题">要保存的内容</memory_save>
→ 保存信息供未来回忆
```

- **优势**：完全不动 API 结构，前端不会出错
- **风险**：依赖 prompt 遵循度，偶尔可能不严格按 XML 格式输出
- **实现**：只读流式响应，正则匹配 XML 标签

### 路线 C：混合（推荐先用 B 验证，再用 A 优化）

- 用路线 B 做 MVP 验证（开发快、风险低）
- 验证通过后，探索路线 A（体验更好）

## 5. 可复用资产（从 AIppocampus 仓）

### 第一梯队：直接移植（~200 行 JS）

| 来源 | 内容 | 用途 |
|------|------|------|
| `aippocampuslib.py` | `sanitize_external_model_text()` 7 种正则脱敏 | 搜索结果返回前脱敏 |
| `aippocampuslib.py` | `is_injected_instruction_text()` 9 种注入检测 | 过滤系统指令 |
| `retrieval.py` | `split_query_terms()` CJK 分词 + `STOP_TERMS` | 中文搜索分词 |
| `retrieval.py` | `phase_weight()` 阶段权重 | 搜索排序信号 |
| `retrieval.py` | `diversify_results()` 结果多样化 | 防止长对话后期内容淹没早期 |

### 第二梯队：算法复用，存储层替换

| 来源 | 内容 | 适配 |
|------|------|------|
| `build_clean_source.py` | `_clean_messages()` 清洗规则 | I/O 改 IndexedDB |
| `search_clean_source.py` | `score_message()` 评分 | JSONL → 内存数组 |
| `retrieval.py` | `extract_rag_terms()` 稀疏向量 | SQLite → MiniSearch |

### 不需要的（被 LLM 自判断替代）

- 12 个 cue 常量集（`EXPLICIT_RECALL_TERMS` 等）— Claude 自己判断
- 900 行召回决策 DAG (`prompt_recall_core.py`) — Claude 自己决定
- 4 级路由决策树 (`memory_candidate_router.py`) — 简化为 2 个 tool
- 语义门控 (`semantic_recall_gate.py`) — 不需要了

## 6. Claude.ai 技术细节备忘（待实测复核）

### DOM 选择器（草稿记录，需按当前前端复测）

| 元素 | 选择器 | 备注 |
|------|--------|------|
| 用户消息 | `[data-testid="user-message"]` | 最可靠 |
| 助手回复 | `.row-start-2` | Clio 项目 2026-04 修正 |
| 流式输出 | `[data-is-streaming]` | 响应进行中 |
| 输入框 | `.ProseMirror[contenteditable="true"]` | ProseMirror 编辑器 |
| 发送按钮 | `button[data-testid="send-button"]` | — |
| 复制按钮 | `button[data-testid="action-bar-copy"]` | 用户和助手消息都有 |

### 内部 REST API（非官方）

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/organizations/{org}/chat_conversations` | 创建对话 |
| GET | `/api/organizations/{org}/chat_conversations/{id}` | 获取完整对话 |
| POST | `/api/organizations/{org}/chat_conversations/{id}/completion` | 发消息（SSE 流） |
| GET | `/api/organizations/{org}/chat_conversations/{id}?tree=True` | 含分支的完整树 |

认证：浏览器 cookie 中的 `sessionKey`，扩展天然拥有。

### 关键工程经验

- MutationObserver 必须 300ms debounce（token-by-token 流式更新 DOM）
- CSP 阻止 content script 外部 fetch，必须走 background relay
- MV3 service worker 会休眠，跨事件状态用 `chrome.storage.session`
- DOM 没有 turn-level wrapper，需从 action bar 向上遍历祖先链定位 turn
- IME 输入需处理 compositionstart/compositionend 事件

## 7. 关键设计决策（待定）

### Q1：保存策略

| 选项 | 优势 | 劣势 |
|------|------|------|
| 自动保存所有对话 | 不丢东西 | 噪音大 |
| Claude 调 `memory_save` 保存 | 智能、精准 | 可能遗漏 |
| 用户手动标记 | 最可控 | 增加认知负担 |
| **自动保存 + Claude save 强化** | 不丢 + 有权重 | 复杂度中等 |

倾向：自动保存 + Claude save 强化。所有对话默认存入，Claude 在对话中觉得某段重要时调 save 加权重。

### Q2：注入方式

| 选项 | 优势 | 劣势 |
|------|------|------|
| 自动注入（用户无感） | 体验最顺滑 | 隐私风险、用户失控 |
| 用户确认后注入 | 可控 | 打断心流 |
| Claude 自己决定 | 最智能 | 需要信任 Claude 的判断 |

倾向：Claude 自己决定（通过 tool call），但扩展强制执行脱敏和截断作为安全网。

### Q3：平台优先级

MVP 只做 Claude.ai。理由：
- Claude 的 tool use 能力最强（原生训练）
- 用户群体与 AIppocampus 重合度最高
- 技术验证最快

后续扩展：ChatGPT → Gemini → 逐个适配。

## 8. MVP 范围

**目标**：用 Tampermonkey 脚本验证完整链路。

1. **对话自动捕获**：轮询 Claude.ai 内部 API，新消息存入 IndexedDB
2. **Prompt 层虚拟工具**：在对话开头注入 memory_search 工具定义
3. **Tool call 解析**：从 Claude 流式响应中提取 `<memory_search>` 标签
4. **本地搜索**：MiniSearch 索引 + CJK 分词（移植自 retrieval.py）
5. **脱敏管线**：返回结果前强制脱敏（移植自 aippocampuslib.py）
6. **结果注入**：构造 tool_result 通过 DOM 注入回对话

**不在 MVP 中**：
- memory_save 工具（先用自动保存）
- Side Panel UI
- 概念图谱
- 跨设备同步
- 多平台支持

## 9. 多 Agent 架构评审（Kimi + Gemini 讨论记录）

> 日期：2026-05-27 | 参与者：Kimi K2.6（架构评审）、Gemini 3.1 Pro（技术调研）、Claude（聚合）

### Kimi 核心观点

1. **MemorySurface Interface 抽象层**：不追求存储层统一（IndexedDB vs SQLite 差异太大），追求数据模型和接口统一。原子单位是 `Turn`（用户输入 + 助手回复 + 元数据），不是 `Message`。同步通过显式的 `AippocampusBundle` 导入/导出，不做实时同步。

2. **Tool Call 的平台差异**：ChatGPT 网页端「重度混淆 + 签名验证」导致拦截极难（**后被查证修正，见 §10**）。建议三级 fallback：Tool Call（Claude.ai）→ 被动提示 + 用户点击（其他平台）→ 纯存档（封闭平台）。

3. **@aippocampus/core（TypeScript 库）** 作为跨平台核心资产。脱敏、CJK 分词、评分算法统一写在 TS 里，浏览器扩展和未来 Electron/Obsidian 插件直接复用，Python CLI 通过子进程或 WASM 调用。

4. **不要做 ActivityPub 式联邦**。那是给公开社交内容设计的，记忆场景的痛点是隐私+冲突+延迟。

5. **演进建议**：双轨并行——MCP Adapter（包装现有 Python 资产，2-3 天）+ Tampermonkey MVP（验证 LLM 自驱召回，1-2 周）。

### Gemini 核心观点

1. **MCP Server 应先于浏览器扩展**。先把记忆逻辑剥离为本地 MCP Server，Cursor/Windsurf/Claude Code 立刻获得记忆能力。浏览器扩展只做轻量 bridge（抓 DOM + 连本地 MCP）。

2. **跨设备同步**：千万不要同步向量（embeddings）。只同步文本形式的「原子事实」，每个客户端本地生成向量。用 Loro/Yjs CRDT 同步增量，端到端加密。

3. **语义层冲突解决**：底层 CRDT 用 LWW（Last-Write-Wins），语义层由 LLM 在写入时先检索旧记忆，发现矛盾则发 `UPDATE` 而非 `ADD`。

4. **读取用 RAG 自动注入，写入用 Tool Call**。读取不需要 LLM 主动发起（系统静默检索 + 注入相关记忆到 prompt），写入和深度探索暴露为 Tool Call。比纯 Tool Call 方案延迟更低。

5. **隐私边界**：向量索引和原始对话必须本地，只有 LLM 提纯后的原子事实 JSON 可以同步（端到端加密）。

### Claude 聚合结论

| 议题 | 决策 |
|------|------|
| 演进顺序 | 双轨并行（Kimi），非串行（Gemini）。两条轨道回答不同问题 |
| 召回机制 | RAG 自动注入 + Tool Call 混合（Gemini）。纯 Tool Call 延迟高 |
| 跨平台统一 | @aippocampus/core TS 库（Kimi）。接口统一 > 存储统一 |
| 跨设备同步 | CRDT 同步原子事实 + 端到端加密（Gemini）。不同步向量 |
| 平台 fallback | ~~ChatGPT 降级为被动提示~~ → 修正为 Tool Call 同样可行（§10） |
| 不要做 | ActivityPub 联邦（两边一致） |

### 修正后的演进路径

```
Phase 1（并行，2 周）
├── 轨道 A：MCP Server（包装现有 Python 资产）
│   └── Claude Desktop / Claude Code 立刻获得记忆能力
└── 轨道 B：Tampermonkey MVP（Claude.ai + ChatGPT）
    └── 验证 RAG 自动注入 + Tool Call 混合方案
    └── 脱敏管线 TS 移植

Phase 2（收敛）
├── 定义 AippocampusBundle v1 格式（跨平台同步契约）
├── 提取 @aippocampus/core（TS 库）
└── 浏览器扩展 ↔ MCP Server 的 Bundle 桥接

Phase 3（扩展）
├── ChatGPT / Gemini 适配（Tool Call / MCP 注入）
├── 可选：CRDT 同步（Loro）
└── 可选：桌面端 Electron wrapper
```

## 10. ChatGPT 拦截可行性修正（调研假设，待源核验）

> §9 中 Kimi 判断「ChatGPT 网页端 API 拦截极难」——本节记录一个待验证的反向假设：该判断可能不适用于浏览器扩展场景。

### 待核验事实

ChatGPT 确实有五阶段安全管线：
1. VM Token（前端配置生成）
2. Requirements Token（`POST /sentinel/chat-requirements`）
3. Proof-of-Work Token（FNV-1a hash 暴力搜索）
4. Turnstile Token（Cloudflare Turnstile VM bytecode，~28K 字符，XOR 多层加密，89 条 VM 指令，检查 55 个 React 应用状态属性——所谓「proof-of-render」）
5. Conduit Token（`POST /conversation/prepare`）

**但这些防御只针对 headless/服务端调用。浏览器扩展运行在同一个 JavaScript 上下文中，继承已完成的安全 token，不需要自己解任何谜题。**

### 待核验线索

| 项目 | 方法 | 日期 |
|------|------|------|
| **GPT Performance Optimizer** | Chrome MV3 扩展，5 层 fetch/Stream 拦截 | 2026-03 |
| **chat-plus** | 浏览器扩展，**往 ChatGPT 注入 MCP 工具** | 2026-04 |
| **rosetta** | CDP Fetch 拦截 + WS 第二通道，完整 Pro 对话含 CoT | 2026-05 |
| **ChatGPT Usage Monitor** | Tampermonkey fetch 拦截 | 2025-12 |
| **ChatGPT Exporter** (pionxzh) | 2371★，95 releases，持续更新到 2026-03 | 活跃 |
| **chatgpt-revised-prompt-extractor** | Tampermonkey `@grant none`，直接调 backend-api | 2026-04 |
| **OmniRoute PR #1593** | Node.js 直连 backend-api（tls-client-node + Sentinel 两阶段握手） | 2026-04 |

### OpenAI 官方 MCP 支持（需按当前官方文档复核）

OpenAI 已发布 **ChatGPT Apps SDK**，基于 MCP 协议：
- 工具执行：`POST /backend-api/ecosystem/call_mcp`（接受 `tool_name`、`app_uri`、`tool_input`）
- Widget 渲染：`GET /backend-api/ecosystem/widget`（HTML-as-data）
- 认证：OAuth 2.1 + CIMD
- 社区实现 chat-plus：浏览器扩展直接往 ChatGPT 注入任意 MCP 工具，模型在沙箱写 JS 编排多工具调用

### ChatGPT 内部 API 端点备忘

```
身份/会话:
  GET  /api/auth/session                    → accessToken (JWT)
  GET  /api/auth/csrf                       → csrfToken
  GET  /backend-api/me

对话:
  POST /backend-api/conversation             → 发消息 (SSE 流)
  GET  /backend-api/conversation/{id}        → 完整对话树 (mapping)
  GET  /backend-api/conversations            → 对话列表 (分页)

安全门控 (Sentinel):
  POST /backend-api/sentinel/chat-requirements/prepare
  POST /backend-api/sentinel/chat-requirements
  POST /backend-api/sentinel/chat-requirements/finalize

工具生态 (MCP):
  GET  /backend-api/ecosystem/widget
  POST /backend-api/ecosystem/call_mcp

文件:
  GET  /backend-api/files/download/{id}
  POST /backend-api/files
```

对话数据格式：树形结构（`mapping` 字典），每个节点含 message + parent + children 引用。与 Claude.ai 的线性消息数组不同。

### 工作结论

**暂不把 ChatGPT 默认降级为「被动提示」。** 先把 Tool Call / MCP 路线作为待验证假设保留；进入实现前必须重新核验官方文档、社区项目现状和当前网页端行为。

**一句话：ChatGPT 的防御目标是阻止无成本批量调用（bot farms），不是阻止浏览器内的用户增强工具。**

## 11. 参考项目（深入研究用）

### 通用 / 跨平台

| 项目 | 为什么要看 | 链接 |
|------|-----------|------|
| Kept | 最完整的系统设计（扩展+桌面+MCP+图谱） | github.com/egroup-labs/kept |
| LokulMem | 纯浏览器端记忆库的最佳实现 | github.com/Pouryaak/LokulMem |
| HAEVN | 工程质量最高（TS 严格+82 个 handler） | github.com/aiamblichus/haevn |
| Context-Sync | 跨平台上下文注入的最直接实现 | github.com/Vineetpandey0/Claude-Context-Preserver |
| hippo-memory | 生物启发记忆（衰减/强化），CLI + MCP | github.com/kitfunso/hippo-memory |
| Supermemory | 23K★，云端记忆 + 浏览器扩展 + MCP | github.com/supermemoryai/supermemory |
| Mem0 | 54K★，通用记忆层，MCP 集成 | github.com/mem0ai/mem0 |

### Claude.ai 专用

| 项目 | 为什么要看 | 链接 |
|------|-----------|------|
| Clio | Claude DOM 提取器，选择器维护经验 | github.com/martymcenroe/Clio |
| chat-archive | 三层提取策略（clipboard→启发式→ML） | github.com/fxops-ai/chat-archive |
| PinIt | CSP 绕过经验、ancestor chain 遍历 | dev.to/mizaelpv |
| claude-ai-re-client | Python 完整逆向 Claude.ai API | github.com/Adithyan-Defender/claude-ai-re-client |

### ChatGPT 专用

| 项目 | 为什么要看 | 链接 |
|------|-----------|------|
| chat-plus | **往 ChatGPT 注入 MCP 工具**，4-hook adapter 合约 | github.com/hgkhgkgjf/chat-plus |
| GPT Performance Optimizer | 5 层 fetch/Stream 拦截，MV3 生产级 | github.com/willy-liu/gpt_performance_optimizer |
| ChatGPT Exporter (pionxzh) | 2371★，95 releases，最成熟的导出方案 | github.com/pionxzh/chatgpt-exporter |
| rosetta | CDP + WS 双通道，完整 Pro 对话含 CoT | github.com/SyntaxSmith/rosetta |
| OmniRoute | Node.js 直连 backend-api，Sentinel 完整握手 | PR #1593 |

### MCP 记忆 Server

| 项目 | 为什么要看 | 链接 |
|------|-----------|------|
| modelcontextprotocol/server-memory | 官方 reference，知识图谱方式 | github.com/modelcontextprotocol/server-memory |
| mem0-mcp / local-mem0-mcp | Mem0 的 MCP 封装 | github.com/mem0ai |

## 12. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Claude.ai 改版导致 API/DOM 失效 | 高 | 高 | 多选择器回退 + 版本检测 |
| ChatGPT Sentinel 升级阻断扩展 | 中 | 中 | 浏览器扩展寄生在前端已完成的安全挑战之上，风险可控；关注 chat-plus 等社区的适配速度 |
| 内部 API 被视为违规 | 中 | 高 | 只读不改；不程序化发消息 |
| 大量对话 IndexedDB 性能 | 中 | 中 | MiniSearch 内存索引 + 懒加载 + 序列化缓存应对 Service Worker 休眠 |
| LLM 不稳定遵循虚拟工具格式 | 中 | 低 | 多轮 prompt 调优 + fallback 正则；优先走 API 层 tools 参数注入（路线 A） |
| 脱敏遗漏导致凭据泄露 | 低 | 高 | 7 种正则模式全移植 + hard_block；ChatGPT 场景需额外测试 |
| IndexedDB ~60MB 容量警告 | 中 | 中 | 分片存储 + 归档线程压缩 + Bundle 导出降级 |
| MV3 Service Worker 休眠杀死索引 | 高 | 中 | MiniSearch 序列化索引存 IndexedDB，启动时 chrome.storage.session 检查缓存 |
