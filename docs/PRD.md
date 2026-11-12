# 最小可用 Agent 系统 PRD

| 项 | 内容 |
| --- | --- |
| 项目名称 | MiniAgent —— 从零实现的最小可用 Agent |
| 版本 | v1.0（待评审） |
| 技术栈 | Vue3 (Vite) + FastAPI (Python 3.10+) |
| 交付形态 | 本地前后端可运行 + GitHub 仓库 + README |
| 文档状态 | **待审核**，审核通过后进入实现 |

---

## 1. 目标与非目标

### 1.1 目标

1. **不依赖任何 Agent 框架**，自行实现 Agent Runtime 主循环（接收输入 → 决策 → 调工具 → 判断继续/结束）。
2. **自行实现工具注册机制与 LLM 输出解析**：工具以「名称 + 描述 + 参数 JSON Schema」注册，LLM 读 Schema 自主决策，运行时解析其输出中的思考、工具调用、最终答案。
3. **多会话隔离**：同一用户可开多个窗口，各自独立上下文、互不污染，可随时切回继续聊。
4. **上下文有效管理**：有轮次上限、能记住历史状态、支持纯对话追问与带工具追问、超长时做基础压缩。
5. **可观测**：每一步的思考/工具调用/工具结果都有 trace，前后端均可查看。
6. 提供可自动运行的测试用例，覆盖上述能力。

### 1.2 非目标（明确不做，避免范围膨胀）

| 不做 | 原因 |
| --- | --- |
| 用户登录 / 多租户鉴权 | 题目只要求「用户 A 开两个窗口」，用单用户 + session 隔离即可表达 |
| 数据库 / 向量检索 / RAG | 会话用内存存储；search 为本地 mock |
| 多 Agent、任务规划器、子 Agent | 超出「最小可用」范围 |
| token 级流式输出 | 见 §7.1：文本 JSON 协议必须先拿到完整输出才能解析，流式粒度为**步骤级** |
| 工具并行调用 | 一次只调一个工具，语义清晰、日志易读 |
| 前端 UI 组件库 / 路由 / 状态管理库 | 三个页面级组件足够，避免无关依赖 |

---

## 2. 已确认的关键决策

| 决策项 | 选择 | 理由 |
| --- | --- | --- |
| LLM 决策协议 | **自研文本 JSON（ReAct 风格）** | 题目要求「自行实现解析逻辑」，把决策与解析都握在自己手里，且便于离线 mock 测试 |
| 会话存储 | **纯内存 dict** | 零依赖、代码最少；重启清空可接受 |
| 前端过程呈现 | **SSE 步骤级流式** | 思考与工具调用逐步浮现，体验接近真实 Agent；粒度是「事件」而非 token |
| 测试范围 | **后端 pytest 全覆盖 + 前端手测清单** | 前端为薄展示层，引入 Vitest 收益低 |
| 用户模型 | 单用户，session 即窗口 | 不做登录 |

---

## 3. 依赖清单（全部必要性说明）

### 后端 `backend/requirements.txt`

| 依赖 | 用途 |
| --- | --- |
| `fastapi` | HTTP 路由、SSE 响应、请求校验（自带 pydantic） |
| `uvicorn[standard]` | ASGI 服务器 |
| `httpx` | 调用 OpenAI 兼容 LLM 接口（异步 HTTP） |
| `pytest` + `pytest-asyncio`（dev） | 测试 |

> `.env` 用 12 行手写解析，**不引入 python-dotenv**。

### 前端 `frontend/package.json`

| 依赖 | 用途 |
| --- | --- |
| `vue` | 视图层 |
| `vite` + `@vitejs/plugin-vue` | 开发服务器与构建，并把 `/api` 代理到 8000 |

> SSE 用原生 `fetch` + `ReadableStream` 解析（约 40 行），**不引入 eventsource 库**；不用 UI 库、不用 pinia、不用 vue-router。

---

## 4. 系统架构

```
┌──────────── Vue3 前端 ────────────┐        ┌─────────── FastAPI 后端 ───────────┐
│ SessionList │ ChatWindow │ SSE 解析 │──HTTP──▶│ /api/chat (SSE)                    │
└───────────────────────────────────┘        │        │                            │
                                              │        ▼                            │
                                              │  AgentRuntime（自研主循环）          │
                                              │   ├─ ContextBuilder（组装+压缩）     │
                                              │   ├─ OutputParser（解析 LLM 输出）   │
                                              │   ├─ ToolRegistry（注册+调度+校验）  │
                                              │   └─ LLMClient（OpenAI 兼容 HTTP）   │
                                              │        │                            │
                                              │  SessionStore（内存，按 id 隔离）     │
                                              └─────────────────────────────────────┘
```

一次请求的时序：

```
前端 POST /api/chat ──▶ AgentRuntime.run_turn()
  for step in 1..MAX_STEPS:
      ContextBuilder.build(session) ──▶ LLMClient.complete() ──▶ OutputParser.parse()
      ├─ final_answer → 落库、emit(answer)、结束
      └─ tool_call    → ToolRegistry.invoke() → 结果写入 session → emit(observation) → 继续
  超出 MAX_STEPS → 兜底答复 + 结束
```

### 4.1 目录结构

```
Ai_Interview/
├── README.md
├── .gitignore                 # 忽略 .env / node_modules / __pycache__
├── docs/
│   ├── PRD.md
│   └── AI_PROMPTS.md          # AI Prompt 与问题解决记录
├── backend/
│   ├── requirements.txt
│   ├── .env.example           # 仅占位值
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py            # 应用装配：CORS、路由、启动配置校验
│   │   ├── config.py          # 环境变量集中读取与校验（缺失即启动失败）
│   │   ├── schemas.py         # 请求/响应模型
│   │   ├── api.py             # 4 个 REST 端点 + 1 个 SSE 端点
│   │   ├── common/
│   │   │   ├── errors.py      # 类型化异常：LLMError/ToolError/ParseError/NotFound
│   │   │   └── logging.py     # 结构化 JSON 日志（含 request_id）
│   │   ├── llm/
│   │   │   ├── client.py      # OpenAI 兼容 /chat/completions
│   │   │   └── mock.py        # ScriptedLLM：按脚本返回，供测试与无 Key 演示
│   │   ├── agent/
│   │   │   ├── runtime.py     # ★ 主循环（核心，约 150 行）
│   │   │   ├── prompt.py      # System Prompt 与 Observation 渲染
│   │   │   ├── parser.py      # ★ LLM 输出解析
│   │   │   └── context.py     # ★ 上下文组装 + 压缩
│   │   ├── tools/
│   │   │   ├── registry.py    # ★ Tool 定义、注册表、Schema 校验
│   │   │   ├── calculator.py  ├── weather.py  ├── todo.py  └── search.py
│   │   └── session/
│   │       └── store.py       # Session / Message / SessionStore
│   └── tests/                 # 8 个测试文件，约 40 条用例
└── frontend/
    ├── package.json  ├── vite.config.js  ├── index.html
    └── src/
        ├── main.js  ├── App.vue  ├── api.js  ├── style.css
        └── components/{SessionList,ChatWindow,MessageItem,TracePanel}.vue
```

---

## 5. 核心设计

### 5.1 LLM 交互协议（自研）

System Prompt 规定：**每次只输出一个 JSON 对象，不带 markdown 代码块、不带多余文字**。

```json
// 需要调用工具
{"thought": "用户问深圳天气，需要调用 weather", "action": "weather", "action_input": {"city": "深圳"}}

// 直接回答 / 基于已有观察收敛
{"thought": "已拿到天气结果，可以直接回答", "final_answer": "深圳今天多云，26~31℃。"}
```

`thought` 必填（用于展示推理过程与 trace）；`action` 与 `final_answer` 二选一。

工具结果回灌格式（以 user 角色承载，兼容所有 OpenAI 兼容接口）：

```
Observation(weather): {"ok": true, "data": {"city": "深圳", "temp": "26~31℃", ...}}
```

### 5.2 输出解析器（`parser.py`）

严格按顺序容错，绝不因格式问题崩溃：

1. 去除首尾空白 → 剥离 ```json ... ``` 代码围栏。
2. `json.loads`。
3. 失败则从文本中扫描**括号平衡**的子串（最多尝试 3 个起点）再解析。
4. 成功且为 dict：
   - 含非空 `final_answer` → `final`
   - 含 `action`（字符串） → `action`，`action_input` 非 dict 时置 `{}` 并记警告
   - 都不含 → `invalid`
5. 全部失败 → `invalid`，保留 `raw` 供重试提示使用。

输出统一为 `ParsedOutput(kind, thought, action, action_input, final_answer, raw)`。

### 5.3 Agent 主循环（`runtime.py`）

| 环节 | 行为 |
| --- | --- |
| Step 1 接收输入 | 追加 user 消息；首轮用前 20 字生成会话标题 |
| Step 2 判断 | 组装 context → 调 LLM → 解析：`final` 直接回复，`action` 进入 Step 3 |
| Step 3 调工具 | `ToolRegistry.invoke(name, args, session)`，未知工具/参数不合法/内部异常一律包成**失败 Observation** 回灌，不中断循环 |
| Step 4 判断 | 工具结果已入上下文 → 进入下一轮循环，由 LLM 决定继续调工具还是收敛 |
| 轮次上限 | `MAX_STEPS`（默认 5）用尽 → 输出兜底文案（`stopped_reason="max_steps"`），历史保留，用户可直接追问「继续」 |
| 解析失败 | 追加一条修复提示消息重试，**最多 1 次**（计入 step）；仍失败则把原始文本作为 `final_answer` 兜底（trace 标记 `parse_failed`） |
| LLM 失败 | 抛 `LLMError` → 前端收到 `error` 事件；会话历史完整保留，可直接重发 |

### 5.4 工具注册机制（`registry.py`）

```python
@dataclass
class Tool:
    name: str
    description: str
    parameters: dict        # JSON Schema
    handler: Callable[[Session, dict], dict]
```

- `@register_tool` 装饰器把工具登记进全局 `ToolRegistry`；`app/tools/__init__.py` 导入即完成注册。
- `registry.schemas()` 生成 System Prompt 里的工具清单，**LLM 看到的就是这份 Schema**。
- `registry.validate(args, schema)` 做最小校验：`required` 缺失、类型不符（string/integer/number/boolean）、`enum` 越界 → 抛出可读错误。不引入 jsonschema 库。

**四个工具**（题目要求 ≥3 且 todo 必须）：

| 工具 | 参数 Schema | 返回 | 说明 |
| --- | --- | --- | --- |
| `calculator` | `expression: string` | `{expression, result}` | 用 `ast` 白名单求值（仅数字、`+ - * / // % **`、括号、一元负号），**不使用 eval**；非法字符/零除/超长表达式返回错误 |
| `weather` | `city: string` | `{city, condition, temp, humidity, wind}` | 内置 6 个城市的 mock 数据，未知城市返回错误并附可用城市列表 |
| `todo` | `action: enum[add,list,complete,delete]`、`content: string`、`todo_id: integer` | `{todos:[{id,content,done}]}` | 待办存于 `session.state["todos"]`，**随会话隔离** |
| `search` | `query: string`、`top_k: integer(default 3)` | `{results:[{title,snippet,score}]}` | 本地 10 篇 mock 文档的词频打分检索，无命中明确返回空 |

### 5.5 会话管理（`store.py`）

```
Session: id | title | created_at | updated_at | messages[] | summary | compressed_upto | state{} | lock
Message: id | role(user/assistant/tool) | content | thought | tool_name | tool_args | tool_ok | created_at
```

- 前端左栏每个会话 = 一个窗口；多开浏览器标签页天然共享同一后端状态。
- `GET /api/sessions/{id}` 返回完整历史（含每步 thought 与工具结果），刷新页面可无缝续聊。
- 同一会话并发请求：per-session `asyncio.Lock`，占用时返回 409「会话正在处理中」，防止上下文串写。
- 删除会话即整条记录移除，不影响其他会话。

### 5.6 上下文组装与压缩（`context.py`）

**放入 context 的内容（按顺序）**

| 位置 | 内容 | 理由 |
| --- | --- | --- |
| 1 | System Prompt（含工具 Schema + 输出协议 + 规则） | 每次都必须携带，保证协议稳定 |
| 2 | 会话摘要（若有压缩） | 用低成本方式保留远距离事实 |
| 3 | 最近窗口内的消息原文 | 短期记忆主体 |
| 4 | 当前用户输入 | 已在消息尾部 |

**刻意不放入的内容**：完整 trace 元数据（耗时/时间戳）、异常堆栈、被压缩掉的旧消息原文、其他会话的任何信息、工具内部实现细节。

**召回时机**：*每一轮循环的每一步*都重新调用 `build_context(session)`，因此工具结果可立即被下一步决策看到；追问时同一 session 的历史自动参与组装，无需额外检索。

**压缩策略（基础版，机械式、确定性、可测试）**

- 触发条件：未压缩消息总字符数 > `CONTEXT_CHAR_BUDGET`(6000) 或条数 > 24。
- 保留：最近 `KEEP_RECENT_MESSAGES`(8) 条**永不压缩**。
- 压缩：更早的消息逐条压成一行摘要，追加到 `session.summary`：
  - `用户: {前 60 字}`
  - `助手调用 {tool}({参数前 40 字})` / `助手: {前 60 字}`
  - `工具 {tool} 返回: {结果前 60 字}`
- 摘要上限 `SUMMARY_MAX_CHARS`(600)，超出时保留尾部（最近的事实优先）。
- 触发时 emit `context_compressed` 事件并写日志，前端显示一条「已压缩 N 条早期消息」提示。

> 不做 LLM 二次摘要、不做向量召回——题目明确「复杂的压缩不用在这里实现」。

### 5.7 可观测性

- **trace**：每轮返回的每个 step 含 `thought / tool / args / result / ok / elapsed_ms`，随 assistant 消息持久化在会话中，前端可折叠查看。
- **日志**：`common/logging.py` 输出单行 JSON，字段固定 `ts, level, request_id, session_id, event, payload`；`event` 取值为 `turn_start / llm_call / parse / tool_call / tool_result / compress / turn_end / error`。不记录 API Key 与完整 Prompt 原文。

### 5.8 异常处理矩阵

| 场景 | 处理 |
| --- | --- |
| 配置缺失 | 启动即抛异常并打印缺失项，不允许带病启动 |
| LLM 超时 / 5xx | 自动重试 1 次 → 仍失败 emit `error`（文案「模型调用失败，请稍后重试」），不泄露堆栈 |
| LLM 返回非 JSON | 修复提示重试 1 次 → 原始文本兜底 |
| 工具不存在 | Observation：`未知工具 xxx，可用工具：...`，LLM 自我纠正 |
| 工具参数不合法 | Observation：`参数错误：缺少必填项 city`，LLM 重试 |
| 工具内部异常 | Observation：`工具执行失败：...`，循环继续 |
| 超过最大轮次 | 兜底答复 + `stopped_reason=max_steps` |
| 会话不存在 | REST 404；SSE 建新会话 |
| 并发写同一会话 | 409 |

---

## 6. 接口契约

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | **SSE**，请求 `{session_id?, message}`；`session_id` 为空则新建会话 |
| GET | `/api/sessions` | 会话列表 `[{id,title,updated_at,message_count}]`，按更新时间倒序 |
| GET | `/api/sessions/{id}` | 会话详情（含 messages 与 trace） |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| GET | `/api/health` | `{status:"ok", llm_mode:"real"|"mock", tools:[...]}` |

SSE 事件序列示例：

```
event: session      data: {"session_id":"9f3a...","title":"帮我查深圳天气"}
event: step         data: {"index":1}
event: thought      data: {"content":"用户问天气，应调用 weather"}
event: tool_call    data: {"tool":"weather","args":{"city":"深圳"}}
event: observation  data: {"tool":"weather","ok":true,"elapsed_ms":2,"result":{...}}
event: step         data: {"index":2}
event: thought      data: {"content":"已获得结果，直接回答"}
event: answer       data: {"content":"深圳今天多云…","stopped_reason":"final"}
```

异常时以 `event: error` 收尾；`context_compressed` 可在任意位置插入。

---

## 7. 前端设计

**布局**：左侧会话列表（新建 / 切换 / 删除，显示标题与更新时间）+ 右侧对话区。

**流式渲染**：发送后立即插入一条「进行中」的助手消息，随事件增长：

```
[思考] 用户问天气，应调用 weather
[工具] weather({"city":"深圳"})  ✓ 2ms
[结果] {"city":"深圳","temp":"26~31℃", ...}
[回答] 深圳今天多云，26~31℃…
```

组件职责：`SessionList`（列表与操作）、`ChatWindow`（消息流 + 输入 + SSE 订阅）、`MessageItem`（用户/助手气泡）、`TracePanel`（折叠 trace）。状态用 `reactive` 局部持有，无状态库。

交互细节：生成中禁用发送与切换会话（或提示先停止）；错误事件在消息内红字提示且不破坏历史；空会话显示示例提问。

---

## 8. SSE 与 JSON 协议的一个取舍

题目要求流式呈现思考过程，但文本 JSON 协议必须拿到**完整**输出才能可靠解析（token 级会把 JSON 切碎，解析成本远大于收益）。故采用**步骤级流式**：LLM 单次调用内部仍是一次完整响应，但每个 step 的 thought / tool_call / observation 一旦产生就立刻推送。用户看到的是「思考 → 调工具 → 看结果 → 再思考」的实时推进，这正是 Agent 的可观测价值所在。

---

## 9. 测试计划

全部用 `ScriptedLLM`（预置返回序列）驱动，**不产生真实 API 调用**，可离线运行。

| 文件 | 覆盖点 | 用例数 |
| --- | --- | --- |
| `test_parser.py` | 纯 JSON / 代码围栏 / 前后噪声 / 括号平衡扫描 / 非法 JSON / action_input 非 dict | 6 |
| `test_registry.py` | 注册查询 / 缺必填 / 类型不符 / enum 越界 / 未知工具 | 5 |
| `test_tools.py` | calculator 正常·零除·注入字符串被拒·非表达式；weather 命中/未命中；todo 增查改删；search 命中/空 | 10 |
| `test_runtime.py` | 直接回答 1 步 / 单工具 2 步 / 双工具 3 步 / 工具异常后自愈 / 超 MAX_STEPS 兜底 / 解析失败修复 / 二次失败降级 | 7 |
| `test_session.py` | 两会话隔离 / 历史续聊 / 标题生成 / todo 跨会话隔离 | 4 |
| `test_context.py` | 消息渲染格式 / 摘要注入 / 超预算触发压缩 / 保留最近 N 条 / 摘要截断 | 5 |
| `test_api.py` | 新建会话 / SSE 事件顺序 / 历史查询 / 删除 / health | 5 |

前端手测清单（写入 README）：多窗口隔离、刷新恢复、追问、压缩提示、错误提示共 5 项。

---

## 10. 交付物

| 交付项 | 说明 |
| --- | --- |
| 代码 | 上述目录结构，无 LLM Key 硬编码（仅 `.env`，`.gitignore` 已排除，仓库只含 `.env.example` 占位） |
| README | 运行方式、系统设计、**memory 召回时机与放置方式**、接口说明、测试命令、演示脚本 |
| `docs/AI_PROMPTS.md` | AI 辅助开发的关键 Prompt、设计取舍，以及 3~5 个真实问题的排查过程 |
| 测试 | `pytest` 全绿 + 前端手测清单 |

---

## 11. 实施顺序

1. 骨架：`main.py` / `config.py` / 日志 / health
2. 工具层：`registry` + 4 个工具
3. LLM 层：`client` + `mock` + `parser`
4. 会话与上下文：`store` + `context`
5. 主循环与 SSE 接口
6. 前端三件套 + SSE 解析
7. 测试补齐 + README + AI 记录

---

## 12. 待确认事项（请重点看这几条）

1. **模型接入**：默认走 OpenAI 兼容接口，环境变量 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`（示例值填 DeepSeek）。是否认可？是否需要在无 Key 时用 `LLM_MOCK=1` 跑规则化假回复来演示（不加 Key 也能看完整链路）？
2. **todo 归属**：按题目「窗口 1 / 窗口 2 互不影响」，待办挂在**会话**上（每个窗口一份独立待办）。若希望同一用户跨窗口共享待办，需引入 user 概念——这会与「禁止额外扩展」冲突，故默认按会话隔离。
3. **单用户假设**：不做登录，`session_id` 即一切；README 中会注明。
4. **压缩阈值**：默认 6000 字符 / 24 条消息触发，保留最近 8 条，摘要上限 600 字。数值是否合适（演示时是否希望能更容易触发压缩）？
5. **确认后**我将按 §11 顺序实现，中途不再插入额外功能。
