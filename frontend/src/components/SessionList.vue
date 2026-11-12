<template>
  <aside class="sidebar">
    <div class="sidebar-head">
      <span class="brand">MiniAgent</span>
      <button class="primary small" :disabled="busy" @click="$emit('create')">+ 新建</button>
    </div>

    <ul class="session-list">
      <li v-if="draft" class="session-item active">
        <div class="session-main">
          <span class="title">新会话</span>
          <span class="meta">尚未发送消息</span>
        </div>
      </li>

      <li
        v-for="item in sessions"
        :key="item.id"
        class="session-item"
        :class="{ active: item.id === currentId }"
        @click="$emit('select', item.id)"
      >
        <div class="session-main">
          <span class="title">{{ item.title }}</span>
          <span class="meta">{{ item.message_count }} 条 · {{ formatTime(item.updated_at) }}</span>
        </div>
        <button class="icon" title="删除会话" :disabled="busy" @click.stop="$emit('remove', item.id)">
          ×
        </button>
      </li>
    </ul>

    <p v-if="!sessions.length && !draft" class="hint">还没有会话，点击「新建」开始。</p>
  </aside>
</template>

<script setup>
defineProps({
  sessions: { type: Array, default: () => [] },
  currentId: { type: String, default: null },
  draft: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})

defineEmits(['create', 'select', 'remove'])

function formatTime(iso) {
  if (!iso) return ''
  // 后端是 UTC ISO 串，转本地时间只显示月-日 时:分
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
</script>
