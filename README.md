# MiniAgent —— 从零实现的最小可用 Agent

一个不依赖任何 Agent 框架（无 LangGraph / OpenHands / OpenClaw）的最小可用 Agent：
自己实现主循环、工具注册、LLM 输出解析、会话隔离、上下文压缩与工具调用追踪。

- 前端：Vue3 + Vite（无 UI 库、无状态库、无路由）
- 后端：FastAPI + httpx（无 Agent 框架，模型只当 HTTP 接口调用）
- 会话存储：进程内内存（刻意的取舍，见「已知取舍」）

---

## 一、对应题目要求

| 题目要求 | 实现位置 |
| --- | --- |
| 从零实现，不依赖 Agent 框架 | `backend/app/agent/runtime.py` 手写循环；模型只经 `httpx` 调用 |
| 基本循环四步 | `runtime.py`：接收输入 → 决策 → 调工具 → 判断继续/收敛 |
| ≥3 个工具且 todo 必须 | calculator / weather / todo / search，共 4 个 |
| 工具注册机制（名称+描述+参数 Schema） | `backend/app/tools/registry.py`，Schema 同时用于 Prompt 与参数校验 |
| 自行解析 LLM 输出 | `backend/app/agent/parser.py`，三级容错 + 修复重试 |
| session 管理（多窗口独立） | `backend/app/session/store.py`，前端左栏每个会话 = 一个窗口 |
| 最大轮次限制 | `MAX_STEPS`（默认 5），用尽给兜底答复且保留历史 |
| 记住状态 / 支持追问 | 消息数组 + 会话摘要；纯对话追问与带工具追问均覆盖 |
| context 过长有基础压缩 | `backend/app/agent/context.py`，机械摘要 + 保留最近 N 条 |
| 异常处理 | 见「异常处理」小节，覆盖模型、解析、工具、并发五类 |
| 工具调用 trace / 日志 | 每步 trace 持久化在会话中；后端输出结构化 JSON 日志 |
| 测试用例 | `backend/tests/`，57 条用例，不产生真实 API 调用 |

---

## 二、运行方式

### 1. 后端

```bash
cd backend
python -m venv .venv                      # Windows: .venv\Scripts\activate
.venv/Scripts/python.exe -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python

cp .env.example .env                      # 填入 LLM_API_KEY
.venv/Scripts/python.exe -m uvicorn run:app --reload --port 8000
```

**没有 API Key 也能跑**：把 `.env` 里的 `LLM_MOCK=1`（或启动时设环境变量 `LLM_MOCK=1`），
就会用内置的规则化 Mock 模型走完「决策 → 调工具 → 收敛」的完整链路。

环境变量（全部集中在 `backend/app/config.py` 读取并校验，缺失即启动失败）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_BASE_URL` | — | OpenAI 兼容接口地址，如 `https://api.deepseek.com/v1` |
| `LLM_API_KEY` | — | 仅存在于 `.env`，`.gitignore` 已排除，仓库内只有 `.env.example` 占位 |
| `LLM_MODEL` | — | 模型名 |
| `LLM_MOCK` | `0` | `1` 时使用内置 Mock 模型 |
| `MAX_STEPS` | `5` | 单轮最多「决策 + 工具」步数 |
| `CONTEXT_CHAR_BUDGET` | `6000` | 未压缩消息的字符预算 |
| `KEEP_RECENT_MESSAGES` | `8` | 压缩时永不触碰的最近消息条数 |
| `SUMMARY_MAX_CHARS` | `600` | 摘要长度上限（超出保留尾部） |
| `CORS_ORIGINS` | `http://localhost:5173` | 显式来源，不用通配符 |

### 2. 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Vite 已把 `/api` 代理到 `http://127.0.0.1:8000`，前端代码里没有任何硬编码地址。

> 若本机设置了 `HTTP_PROXY`，用 curl 调试 `localhost` 时需加 `--noproxy '*'`，浏览器不受影响。

### 3. 测试

```bash
cd backend
.venv/Scripts/python.exe -m pytest        # 57 passed
```

---

## 三、系统设计

### 3.1 分层

```
Vue3（会话列表 / 对话流 / trace 面板）
        │  POST /api/chat  (SSE)
        ▼
FastAPI  api.py ── 路由、SSE 封装、会话查改删
        │
        ▼
AgentRuntime（主循环，唯一有"决策权"的地方）
   ├─ ContextBuilder   组装上下文 + 触发压缩
   ├─ OutputParser     解析 LLM 输出 → final / action / invalid
   ├─ ToolRegistry     工具注册、Schema 校验、异常兜底、计时
   └─ LLMClient        OpenAI 兼容 /chat/completions
        │
        ▼
SessionStore（内存字典，按 session_id 隔离）
```

控制器（`api.py`）不写业务逻辑；主循环（`runtime.py`）不关心 HTTP；
工具（`tools/*`）不关心是谁调用它。三层各自可单测。

### 3.2 目录

```
backend/
├── run.py                      # uvicorn 入口
├── requirements.txt  .env.example  pytest.ini
├── app/
│   ├── main.py                 # 应用装配、CORS、启动校验、健康检查
│   ├── config.py               # 环境变量集中读取 + 启动即校验
│   ├── schemas.py  api.py      # 请求模型 / 5 个接口
│   ├── common/{errors,logging}.py
│   ├── agent/{runtime,parser,prompt,context}.py
│   ├── llm/{client,mock}.py    # 真实客户端 / 脚本化与规则化假模型
│   ├── session/store.py        # Session / Message / SessionStore
│   └── tools/{registry,calculator,weather,todo,search}.py
└── tests/                      # 8 个文件 57 条用例
frontend/
└── src/{App.vue, api.js, style.css, components/*.vue}
```

### 3.3 一次请求的时序

```
POST /api/chat
  └─ 取出/新建 session（并发占用则 409）
     └─ 可选：上下文压缩（emit context_compressed）
        └─ for step in 1..MAX_STEPS:
             组装上下文(messages) → 调模型 → 解析
             ├─ final  → 落库 → emit thought/answer → 结束
             ├─ action → emit thought/tool_call → 调工具 → emit observation → 继续
             └─ invalid→ emit parse_error → 追加修复提示 → 重试（最多 1 次）
        └─ 步数用尽 → 兜底答复（stopped_reason=max_steps）
```

### 3.4 LLM 交互协议（自研）

System Prompt 规定模型每次只输出一个 JSON 对象：

```json
{"thought": "...", "action": "weather", "action_input": {"city": "深圳"}}
{"thought": "...", "final_answer": "深圳今天多云，26~31℃。"}
```

工具结果以 `Observation(weather): {"ok": true, ...}` 回灌，模型据此决定继续还是收敛。

### 3.5 输出解析（`parser.py`）

三级容错，任何情况下都不会因格式问题崩溃：

1. 原样 `json.loads`
2. 剥掉 ```json 代码围栏再解析
3. **括号平衡扫描**：从每个 `{` 起做深度计数（跳过字符串内部与转义），截出平衡子串再解析，最多试 3 个起点

仍失败 → `invalid`；主循环追加修复提示重试 1 次，二次失败把原始文本作为答复降级返回。

### 3.6 工具注册机制

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema
    handler: Callable[[Session, dict], dict]
```

- `registry.schemas()` 生成 System Prompt 里的工具清单——模型看到的就是这份 Schema；
- `registry.validate()` 用同一份 Schema 校验必填、类型、枚举，**Schema 不是装饰**；
- `registry.invoke()` 统一捕获异常并计时，把失败转成 Observation 回灌。

**新增一个工具**：在 `app/tools/` 下写一个函数 + `registry.register(Tool(...))`，再在
`app/tools/__init__.py` 里 import 一次即可，主循环与 Prompt 无需改动。

现有四个工具：

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `calculator` | `expression: string` | 用 `ast` 白名单求值，**不使用 eval**，拒绝函数调用/变量名/超大指数 |
| `weather` | `city: string` | 6 个城市的内置模拟数据，未知城市返回可查询列表 |
| `todo` | `action: enum[add,list,complete,delete]`、`content`、`todo_id` | 待办存于 `session.state["todos"]`，**随会话隔离** |
| `search` | `query: string`、`top_k: integer` | 本地 10 篇 mock 文档的 2-gram 词频检索 |

### 3.7 前端

- 左侧会话列表 = 题目里的「窗口」，每个窗口对应一个独立 session；
- 发送消息后用原生 `fetch` + `ReadableStream` 解析 SSE（约 40 行，无第三方库）；
- 进行中的一轮以「思考 → 工具调用 → 工具结果 → 回答」逐段浮现，完成后以服务端持久化历史为准（含完整 trace）；
- 前端**不解析 LLM 协议**：只渲染 `text`（人类可读）与 `trace`（步骤），中间 JSON 不会漏到界面上。

---

## 四、Memory 的召回时机与放置方式

这是本题的核心，单独说明。

### 4.1 放进 context 的内容（按顺序）

| 位置 | 内容 | 为什么放 |
| --- | --- | --- |
| 1 | System Prompt（工具 Schema + 输出协议 + 规则） | 协议必须每轮稳定复现，否则解析会崩 |
| 2 | 会话摘要（若有压缩） | 用极低成本保住远距离事实（早期结论、用户偏好） |
| 3 | 最近窗口的消息原文 | 短期记忆主体：用户问题、模型决策、工具结果 |
| 4 | 当前用户输入 | 已在消息尾部 |

消息按角色渲染：

- `user` → `{"role": "user", "content": 原文}`
- `assistant` → 原样回灌模型上一次的 JSON（保证协议连贯）
- `tool` → `{"role": "user", "content": "Observation(工具名): {...}"}`

### 4.2 刻意不放进 context 的内容

| 不放 | 原因 |
| --- | --- |
| trace 的元数据（耗时、时间戳、step 序号） | 对决策无价值，只占预算 |
| 异常堆栈 | 内部细节，模型看了也只会复述 |
| 被压缩掉的旧消息原文 | 已经进摘要，重复塞等于没压缩 |
| 其他 session 的任何信息 | 窗口隔离的前提 |
| 工具内部实现与代码 | 与任务无关 |
| 格式重试用的中间 JSON 原文 | 只在修复那一步有用，压不进摘要（`visible=False` 时跳过） |

### 4.3 召回时机

- **每轮循环的每一步都重建一次**（`build_context`），所以工具结果在同一轮内立刻对下一步可见——这是「工具调用后的再决策」成立的前提；
- **追问时不需要额外检索**：同一 session 的历史天然参与组装，"那北京呢" 这类追问直接就能接上；
- **压缩在每轮对话开始前判断**，不在循环中间触发，避免把本轮刚产生的 Observation 压掉。

### 4.4 压缩策略（基础版）

触发条件（满足其一）：

- 未压缩消息总字符数 > `CONTEXT_CHAR_BUDGET`（默认 6000）
- 未压缩消息条数 > 24

执行：

1. 最近 `KEEP_RECENT_MESSAGES`（默认 8）条**永不压缩**；
2. 更早的消息逐条压成一行摘要追加到 `session.summary`：
   - `用户: {前 60 字}`
   - `助手调用 weather({"city": "深圳"})`
   - `工具 weather 成功: {结果前 60 字}`
3. 摘要超过 `SUMMARY_MAX_CHARS`（默认 600）时**保留尾部**（最近的事实价值更高），并尽量从整行开始截断；
4. `compressed_upto` 游标记录进度，原始消息仍保留在会话里供前端查看历史；
5. 触发时通过 SSE 推 `context_compressed` 事件，UI 显示「已压缩 N 条早期消息」。

不做 LLM 二次摘要、不做向量召回——题目明确「复杂的压缩不用在这里实现」。

---

## 五、异常处理

| 场景 | 行为 |
| --- | --- |
| 环境变量缺失 | 启动即抛 `ConfigError` 并提示缺失项，不带病运行 |
| 模型超时 / 5xx | 自动重试 1 次；仍失败推 `error` 事件，历史完整保留可重发 |
| 模型返回 4xx | 直接失败并提示检查 Key/模型名，不做无意义重试 |
| 输出不是合法 JSON | 追加修复提示重试 1 次 → 仍失败降级返回原文（`stopped_reason=parse_fallback`） |
| 工具不存在 / 参数不合法 | 转成失败 Observation 回灌，模型自行纠正，循环不中断 |
| 工具内部抛异常 | 同上，统一兜成 `{"error": "..."}`，附耗时 |
| 步数用尽 | 兜底答复（`max_steps`），历史保留，用户可直接说「继续」 |
| 同一会话并发请求 | 409「该会话正在处理中」 |
| 会话不存在 | 404 |
| SSE 内未预期异常 | 兜底推 `error` 事件，不让连接悬挂 |

日志：单行 JSON，固定字段 `ts / level / request_id / event / payload`，
事件类型包括 `turn_start / llm_call / tool_result / parse_failed / compress / turn_end / stream_error`。
**不记录** API Key 与完整 Prompt 原文。

---

## 六、测试

```bash
cd backend && .venv/Scripts/python.exe -m pytest -v
```

全部使用 `ScriptedLLM`（预置返回序列）驱动，**不产生真实 API 调用**，离线可跑。

| 文件 | 覆盖点 | 数量 |
| --- | --- | --- |
| `test_parser.py` | 纯 JSON / 代码围栏 / 前后噪声 / 字符串内括号 / 非法输出 / 参数为字符串 | 8 |
| `test_registry.py` | Schema 暴露 / 正常调用 / 缺必填 / 类型错 / 枚举越界 / 未知工具 / handler 异常 | 7 |
| `test_tools.py` | calculator 注入与除零、weather 命中与未命中、todo 增删改查与会话隔离、search 命中与空 | 15 |
| `test_runtime.py` | 直接回答 / 单工具 / 双工具 / 工具报错自愈 / 未知工具 / 轮次上限 / 解析重试 / 解析二次失败降级 / 模型失败 | 9 |
| `test_session.py` | 两会话隔离 / 追问看到上文 / 带工具追问保住状态 / 标题生成 / 多轮历史 | 5 |
| `test_context.py` | 上下文顺序与 Observation 渲染 / 摘要注入 / 未超预算不压缩 / 压缩保留最近 N 条 / 跳过不可见中间步骤 / 摘要截断 | 6 |
| `test_api.py` | 健康检查 / SSE 事件顺序 / 续聊 / 404 / 空消息 422 / 列表与删除 / 模型失败事件 | 7 |

**前端手测清单**（三条命令启动后逐项确认）：

1. 新建会话 A，发送「帮我查一下深圳的天气，然后记一个待办」，应看到 3 步：思考 → weather → todo → 回答；
2. 新建会话 B，发送「帮我写一段周报，然后记一个待办」，两个会话的消息与待办互不影响；
3. 切回会话 A 问「我刚才记了什么待办？」，答案只包含 A 的待办；
4. 刷新页面，会话列表与完整历史（含 trace 折叠面板）都能恢复；
5. 停掉后端再发消息，界面显示可读错误提示且不丢失历史。

---

## 七、已知取舍

| 取舍 | 说明 |
| --- | --- |
| 会话存内存 | 重启即清空。零依赖、代码最少；要持久化换一个 `SessionStore` 实现即可，接口不变 |
| 单用户 | 不做登录，`session_id` 即窗口。题目只要求「同一用户多窗口」 |
| 步骤级流式 | 文本 JSON 协议必须先拿到完整输出才能解析，token 级流式会切碎 JSON |
| todo 按会话隔离 | 与「窗口互不影响」一致；跨窗口共享需引入用户概念，超出题目范围 |
| 摘要为机械规则 | 确定性、可断言、零额外模型调用，符合「基础压缩」 |
| 不做工具并行 | 一次一个工具，语义清晰、trace 易读 |

---

## 八、文档

- `docs/PRD.md` —— 需求与设计说明（决策、接口契约、测试计划）
- `docs/AI_PROMPTS.md` —— AI 辅助开发的 Prompt 记录与 6 个真实问题的排查过程
