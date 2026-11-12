// 与后端通信的唯一出口：BASE 走相对路径，由 vite 代理到后端
const BASE = '/api'

async function toError(response) {
  let detail = `请求失败（HTTP ${response.status}）`
  try {
    const body = await response.json()
    if (body && body.detail) {
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    }
  } catch {
    /* 响应不是 JSON，沿用默认文案 */
  }
  return new Error(detail)
}

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options)
  if (!response.ok) throw await toError(response)
  return response.json()
}

export function listSessions() {
  return request('/sessions')
}

export function getSession(id) {
  return request(`/sessions/${id}`)
}

export function removeSession(id) {
  return request(`/sessions/${id}`, { method: 'DELETE' })
}

/**
 * 发起一轮对话并逐条消费 SSE 事件。
 * event.data 已解析为对象，交给调用方按 event 名分发。
 */
export async function streamChat({ sessionId, message, onEvent, signal }) {
  const response = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  })
  if (!response.ok) throw await toError(response)
  if (!response.body) throw new Error('当前浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = parseBlock(block)
      if (event) onEvent(event)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

function parseBlock(block) {
  let name = 'message'
  const dataLines = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) name = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  try {
    return { event: name, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}
