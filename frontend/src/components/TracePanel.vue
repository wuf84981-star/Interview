<template>
  <details v-if="steps.length" class="trace">
    <summary>
      思考与工具调用 · {{ steps.length }} 步
      <span v-if="notice" class="notice">{{ notice }}</span>
    </summary>
    <ol>
      <li v-for="(step, index) in steps" :key="index">
        <div class="line">
          <span class="idx">#{{ step.index ?? index + 1 }}</span>
          <span class="thought">{{ step.thought || '（无思考内容）' }}</span>
        </div>

        <div v-if="step.tool" class="tool">
          <code>{{ step.tool }}({{ shortArgs(step.args) }})</code>
          <span v-if="step.ok !== undefined" class="status" :class="step.ok ? 'is-ok' : 'is-fail'">
            {{ step.ok ? '成功' : '失败' }} · {{ step.elapsed_ms }}ms
          </span>
          <pre v-if="step.result !== undefined">{{ shortResult(step.result) }}</pre>
        </div>

        <div v-if="step.final" class="final">→ 收敛为最终答复</div>
        <div v-else-if="step.parse_error" class="final fail">格式错误：{{ step.parse_error }}</div>
      </li>
    </ol>
  </details>
  <p v-else-if="notice" class="muted small">{{ notice }}</p>
</template>

<script setup>
const props = defineProps({
  steps: { type: Array, default: () => [] },
  notice: { type: String, default: '' },
})

function shortArgs(args) {
  if (!args || !Object.keys(args).length) return ''
  return JSON.stringify(args)
}

function shortResult(result) {
  const text = JSON.stringify(result)
  return text.length > 200 ? `${text.slice(0, 200)}…` : text
}
</script>
