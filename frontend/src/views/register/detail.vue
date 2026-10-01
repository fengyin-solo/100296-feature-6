<template>
  <section class="page" data-module="register-detail">
    <header class="page-head">
      <div>
        <h2>设备登记明细</h2>
        <p class="page-desc">登记信息、流转留痕与重复提交备注都在此可查。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="entry">
      <div class="detail-grid">
        <article v-for="field in fields" :key="field" class="detail-item">
          <span class="detail-label">{{ field }}</span>
          <strong>{{ entry[field] || '—' }}</strong>
        </article>
        <article class="detail-item">
          <span class="detail-label">当前状态</span>
          <strong class="status-badge">{{ entry.status }}</strong>
        </article>
      </div>

      <h3 class="section-title">流转记录（每步时间与经手人）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>经手人</th>
            <th>动作</th>
            <th>变更前</th>
            <th>变更后</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(record, index) in entry.流转记录" :key="index">
            <td>{{ record.时间 }}</td>
            <td>{{ record.经手人 }}</td>
            <td>{{ record.动作 }}</td>
            <td>{{ record.变更前 || '—' }}</td>
            <td>{{ record.变更后 }}</td>
          </tr>
          <tr v-if="!entry.流转记录?.length">
            <td colspan="5" class="empty-state">暂无流转记录</td>
          </tr>
        </tbody>
      </table>

      <h3 class="section-title">重复登记备注</h3>
      <pre v-if="entry.重复登记备注" class="remark-box">{{ entry.重复登记备注 }}</pre>
      <p v-else class="muted-text">暂无重复提交记录。同一设备重复提交登记时，补充内容会追加在这里，不覆盖最早一条登记。</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchJson } from '@/api/client'

type AuditRecord = { 时间: string; 经手人: string; 动作: string; 变更前: string; 变更后: string }
type Entry = Record<string, string | number | null> & {
  status: string
  流转记录?: AuditRecord[]
  重复登记备注?: string
}

const route = useRoute()
const router = useRouter()

const fields = ['设备编号', '设备名称', '设备种类', '使用单位', '安装地点', '投用日期', '登记证号']
const entry = ref<Entry | null>(null)
const errorMessage = ref('')

function goBack() {
  void router.push({ name: 'register' })
}

onMounted(async () => {
  const id = route.params.id
  try {
    entry.value = await fetchJson<Entry>(`/api/register/${id}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记明细读取失败'
  }
})
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.detail-item {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.detail-label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.section-title { font-size: 15px; margin: 18px 0 8px; }
.remark-box {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
  margin: 0;
}
.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  background: #eef4ff;
  color: #1f6feb;
}
.muted-text { color: var(--muted); font-size: 13px; }
</style>
