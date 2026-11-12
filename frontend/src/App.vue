<template>
  <div class="app">
    <SessionList
      :sessions="sessions"
      :current-id="currentId"
      :draft="isDraft"
      :busy="busy"
      @create="newSession"
      @select="selectSession"
      @remove="deleteSession"
    />

    <ChatWindow
      v-if="currentId || isDraft"
      :messages="messages"
      :live="live"
      :busy="busy"
      @send="send"
    />

    <section v-else class="empty-state">
      <h1>MiniAgent</h1>
      <p>从零实现的最小可用 Agent：自主决策、调用工具、多会话隔离。</p>
      <button class="primary" @click="newSession">新建会话</button>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { getSession, listSessions, removeSession, streamChat } from './api'
import SessionList from './components/SessionList.vue'
import ChatWindow from './components/ChatWindow.vue'

const sessions = ref([])
const currentId = ref(null)
const isDraft = ref(false) // 新会话：发第一条消息后才由后端分配 id
const messages = ref([])
const busy = ref(false)
const live = reactive({ active: false, steps: [], answer: '', error: '', notice: '' })

function resetLive() {
  live.active = false
  live.steps = []
  live.answer = ''
  live.error = ''
  live.notice = ''
}

async function refreshSessions() {
  const data = await listSessions()
  sessions.value = data.sessions
}

function newSession() {
  if (busy.value) return
  currentId.value = null
  isDraft.value = true
  messages.value = []
  resetLive()
}

async function selectSession(id) {
  if (busy.value || id === currentId.value) return
  isDraft.value = false
  currentId.value = id
  resetLive()
  try {
    const detail = await getSession(id)
    messages.value = detail.messages
  } catch (error) {
    live.error = error.message
    messages.value = []
  }
}

async function deleteSession(id) {
  if (busy.value) return
  try {
    await removeSession(id)
  } catch (error) {
    live.error = error.message
  }
  if (id === currentId.value) {
    currentId.value = null
    isDraft.value = false
    messages.value = []
    resetLive()
  }
  await refreshSessions().catch(() => {})
}

// 把 SSE 事件折叠成「当前这一轮的步骤列表」
function onEvent({ event, data }) {
  const currentStep = () => live.steps[live.steps.length - 1]

  switch (event) {
    case 'session':
      if (!currentId.value) {
        currentId.value = data.session_id
        isDraft.value = false
      }
      break
    case 'step':
      live.steps.push({ index: data.index, thought: '', tool: '', args: {}, final: false })
      break
    case 'thought':
      if (currentStep()) currentStep().thought = data.content
      break
    case 'tool_call':
      if (currentStep()) {
        currentStep().tool = data.tool
        currentStep().args = data.args
      }
      break
    case 'observation':
      if (currentStep()) {
        Object.assign(currentStep(), {
          ok: data.ok,
          result: data.result,
          elapsed_ms: data.elapsed_ms,
        })
      }
      break
    case 'context_compressed':
      live.notice = `已压缩 ${data.dropped} 条早期消息（摘要 ${data.summary_chars} 字）`
      break
    case 'parse_error':
      live.notice = data.message
      break
    case 'answer':
      live.answer = data.content
      break
    case 'error':
      live.error = data.message
      break
  }
}

async function send(text) {
  if (busy.value) return
  const sessionId = currentId.value

  messages.value.push({ role: 'user', text, content: text })
  resetLive()
  busy.value = true
  live.active = true

  try {
    await streamChat({ sessionId, message: text, onEvent })
  } catch (error) {
    live.error = error.message
  } finally {
    busy.value = false
    live.active = false
    // 以服务端持久化的历史为准（含完整 trace），避免前端重复维护状态
    if (currentId.value) {
      try {
        const detail = await getSession(currentId.value)
        messages.value = detail.messages
        // 历史里已经有这轮的答复，清掉流式状态避免重复渲染；出错时保留错误提示
        if (!live.error) resetLive()
      } catch {
        /* 拉取失败时保留流式内容 */
      }
      await refreshSessions().catch(() => {})
    }
  }
}

onMounted(() => {
  refreshSessions().catch((error) => {
    live.error = error.message
  })
})
</script>
