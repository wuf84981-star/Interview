<template>
  <div class="message" :class="message.role">
    <div class="avatar">{{ message.role === 'user' ? '我' : 'AI' }}</div>
    <div class="bubble">
      <TracePanel v-if="hasTrace" :steps="message.trace" :notice="''" />
      <p class="text">{{ display }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import TracePanel from './TracePanel.vue'

const props = defineProps({
  message: { type: Object, required: true },
})

// 只渲染后端给的 text（用户原文 / 最终答复），不在前端解析 LLM 协议
const display = computed(() => props.message.text || props.message.content || '')
const hasTrace = computed(() => Array.isArray(props.message.trace) && props.message.trace.length > 0)
</script>
