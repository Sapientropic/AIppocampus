# Browser Extension Research Notes

Role: research seed.
Status: current background notes; implementation routing stays in
[`browser-extension-design.md`](browser-extension-design.md).

## 0. 平台复核快照（2026-05-30）

本节是 #60 的 source-linked verification note。它只确认官方平台边界和
MVP 方向，不证明任何当前 Claude.ai / ChatGPT DOM selector 或内部端点
仍然可用。

### 可作为 MVP 的路线

当前最稳的本地 MVP 仍是 Claude.ai 上的 prompt 层虚拟
`memory_search`：扩展或用户脚本只做本地捕获、搜索、脱敏、截断和显式
结果交接，不注入官方 tool schema，不依赖内部 REST 端点作为稳定合同。
内部 API、DOM selector、cookie 名称、SSE 格式只能作为 dated local
observations；每次进入实现前都要重新实测。

### 官方路线边界

- Claude 自定义 connectors 已支持 remote MCP，但 Claude 从 Anthropic 云
  基础设施连接到公开可达的 MCP server；本地 `claude_desktop_config.json`
  里的 local MCP 不适用于 claude.ai。见 Anthropic Help Center:
  <https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp>。
- Anthropic API 也有 MCP connector，但它面向 Messages API、remote MCP
  server 和 beta header，不等于 claude.ai 页面扩展能稳定注入本地工具。
  见 Anthropic API docs:
  <https://platform.claude.com/docs/en/agents-and-tools/mcp-connector>。
- OpenAI Apps SDK / ChatGPT apps 是官方 ChatGPT 平台路线，基于 MCP，
  仍处 preview / beta 流程，需要 developer mode、MCP endpoint、测试和
  发布审核；它不是内部 `/backend-api/*` 端点的稳定开发合同。见
  <https://help.openai.com/en/articles/12515353-build-with-the-apps-sdk> 和
  <https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt>。
- OpenAI API 的 remote MCP / connectors 默认会在向 MCP server 分享数据前
  请求审批，并把 remote MCP / connector 视为会带来敏感数据和第三方服务
  风险的 powerful feature。见
  <https://developers.openai.com/api/docs/guides/tools-connectors-mcp>。
- Chrome MV3 应按最小权限设计：优先 `activeTab`、用户触发和
  optional host permissions，而不是默认全站 host access。见 Chrome
  extension permissions docs:
  <https://developer.chrome.com/docs/extensions/reference/api/permissions>。

### Consent / privacy boundary

- Capture 默认关闭；用户必须对具体站点或会话显式开启。
- Injection 默认关闭或逐次确认；返回结果必须可见、可撤回、可停止。
- 本地 IndexedDB / storage 只保存用户明确允许的对话片段；不要默认抓取
  所有 Claude.ai / ChatGPT 页面。
- 搜索结果交给模型前必须经过脱敏、prompt-injection 检测、长度截断和
  source-boundary 标注。
- `memory_save`、自动加权、跨设备同步、remote MCP、ChatGPT Apps SDK、
  API 层 tool injection 都不属于第一版 Claude.ai local MVP。


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


## 10. ChatGPT 拦截可行性修正（调研假设，待源核验）

> §9 中 Kimi 判断「ChatGPT 网页端 API 拦截极难」——本节记录一个待验证的反向假设：该判断可能不适用于浏览器扩展场景。
>
> 2026-05-30 复核更新：本节保留为历史调研线索。ChatGPT 的官方路线应
> 优先看 Apps SDK / developer mode / MCP apps；内部 `backend-api` 端点不
> 作为 AIppocampus 实现或发布声明的稳定依据。

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
