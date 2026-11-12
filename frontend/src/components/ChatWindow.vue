<template>
  <section class="chat">
    <header class="chat-head">
      <h2>对话</h2>
      <span class="badge" :class="{ live: busy }">{{ busy ? '思考中…' : '就绪' }}</span>
    </header>

    <div ref="scroller" class="messages">
      <MessageItem v-for="(message, index) in messages" :key="index" :message="message" />

      <div v-if="live.active || live.answer || live.error || live.steps.length" class="message assistant">
        <div class="avatar">AI</div>
        <div class="bubble">
          <TracePanel :steps="live.steps" :notice="live.notice" />
          <p v-if="live.answer" class="text">{{ live.answer }}</p>
          <p v-else-if="live.error" class="text error">{{ live.error }}</p>
          <p v-else class="text muted">正在处理…</p>
        </div>
      </div>

      <p v-if="!messages.length && !live.active" class="hint center">
        试试：帮我查一下深圳的天气，然后记一个待办
      </p>
    </div>

    <form class="composer" @submit.prevent="submit">
      <textarea
        v-model="draft"
        rows="2"
        placeholder="输入消息，Enter 发送，Shift + Enter 换行"
        :disabled="busy"
        @keydown.enter.exact.prevent="submit"
      />
      <button class="primary" type="submit" :disabled="busy || !draft.trim()">发送</button>
    </form>
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import MessageItem from './MessageItem.vue'
import TracePanel from './TracePanel.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  live: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])
const draft = ref('')
const scroller = ref(null)

function submit() {
  const text = draft.value.trim()
  if (!text || props.busy) return
  draft.value = ''
  emit('send', text)
}

watch(
  () => [props.messages.length, props.live.steps.length, props.live.answer, props.live.error],
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  },
)
</script>
