<template>
  <section class="page" data-module="register-detail">
    <header class="page-head">
      <div>
        <h2>设备登记详情</h2>
        <p class="page-desc">设备基础信息与状态流转留痕：每一步的动作、时间、经手人都可追溯。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <article v-if="entry" class="detail-card">
      <header class="detail-head">
        <div>
          <h3>{{ entry.设备编号 ?? '—' }} · {{ entry.设备名称 ?? '未命名设备' }}</h3>
          <span class="status-badge">{{ entry.status ?? '待登记' }}</span>
        </div>
      </header>

      <h4>登记信息</h4>
      <dl class="detail-grid">
        <div v-for="field in detailFields" :key="field">
          <dt>{{ field }}</dt>
          <dd>{{ entry[field] ?? '—' }}</dd>
        </div>
      </dl>

      <h4>重复登记留档</h4>
      <pre v-if="entry.备注" class="remark-box">{{ entry.备注 }}</pre>
      <p v-else class="muted-text">暂无重复提交记录。</p>

      <h4>操作流水</h4>
      <ol v-if="entry.history?.length" class="timeline">
        <li v-for="(item, index) in entry.history" :key="index" class="timeline-item">
          <div class="timeline-main">
            <strong>{{ item.action }}</strong>
            <span class="muted-text">
              <template v-if="item.from && item.to">{{ item.from }} → {{ item.to }}</template>
              <template v-else>{{ item.to }}</template>
            </span>
          </div>
          <div class="timeline-meta">
            <span>{{ item.time }}</span>
            <span>经手人：{{ item.operator }}</span>
          </div>
        </li>
      </ol>
      <p v-else class="muted-text">暂无操作流水。</p>
    </article>

    <p v-else-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <p v-else class="muted-text">正在读取设备登记明细…</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

interface HistoryItem {
  action: string
  from: string
  to: string
  time: string
  operator: string
}

type Entry = Record<string, string | HistoryItem[] | null> & { history?: HistoryItem[] }

const route = useRoute()
const router = useRouter()

const detailFields = ['设备编号', '设备名称', '设备种类', '使用单位', '安装地点', '投用日期', '登记证号', '登记状态']
const entry = ref<Entry | null>(null)
const errorMessage = ref('')

function goBack() {
  router.back()
}

onMounted(async () => {
  const id = String(route.params.id ?? '')
  try {
    const response = await request(`/api/register/${id}`)
    if (!response.ok) {
      throw new Error(`设备登记 ${id} 不存在或已归档`)
    }
    entry.value = (await response.json()) as Entry
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备登记明细读取失败'
  }
})
</script>

<style scoped>
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 22px;
}
.detail-head h3 {
  display: inline;
  margin-right: 10px;
}
.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  background: #eef2f7;
  font-size: 12px;
}
.detail-card h4 {
  margin: 18px 0 8px;
  font-size: 14px;
  border-left: 3px solid var(--brand);
  padding-left: 8px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px 18px;
  margin: 0;
}
.detail-grid dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-grid dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.remark-box {
  background: #f8fafc;
  border: 1px dashed var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  font-family: inherit;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 0 0 0 14px;
  border-left: 2px solid var(--border);
}
.timeline-item {
  position: relative;
  padding: 0 0 14px 16px;
}
.timeline-item::before {
  content: '';
  position: absolute;
  left: -19px;
  top: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
}
.timeline-main {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 13px;
}
.timeline-meta {
  display: flex;
  gap: 14px;
  color: var(--muted);
  font-size: 12px;
  margin-top: 2px;
}
.muted-text {
  color: var(--muted);
  font-size: 13px;
}
</style>
