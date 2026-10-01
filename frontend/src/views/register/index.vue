<template>
  <section class="page" data-module="register">
    <header class="page-head">
      <div>
        <h2>使用登记管理</h2>
        <p class="page-desc">设备按「待登记 → 已登记 → 停用中 / 已注销」逐级把关；每一步记录时间与经手人，跳步申请当场退回。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记设备</button>
        <button class="btn" type="button" @click="exportRows">导出使用登记清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card" :class="item.emphasis">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>设备编号</span>
        <input v-model="keyword" placeholder="按设备编号检索" />
      </label>
      <label class="filter-item">
        <span>登记状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <a v-if="column === '设备编号'" class="link" href="javascript:void(0)" @click="openDetail(row.id)">
              {{ row[column] ?? '—' }}
            </a>
            <span v-else :class="{ 'status-badge': column === '登记状态' }">{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <template v-if="actionsByStatus[row.status ?? '']?.length">
              <button
                v-for="action in actionsByStatus[row.status ?? '']"
                :key="action"
                class="link"
                :class="{ danger: action === '申请注销' }"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">已注销，无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无使用登记数据，可先登记设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条使用登记记录</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
        第 {{ page }} 页
        <button class="btn" type="button" :disabled="page * pageSize >= total" @click="changePage(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="showForm" class="modal-mask" @click.self="closeCreate">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记设备</h3>
        <p class="modal-tip">登记证号、使用单位为办证硬指标，缺一项都会当场退回。</p>
        <label v-for="field in formFields" :key="field.key" class="form-item">
          <span>{{ field.label }}<i v-if="field.required" class="required-mark">*</i></span>
          <input
            v-model="form[field.key]"
            :type="field.type ?? 'text'"
            :class="{ invalid: missingFields.includes(field.key) }"
            :placeholder="`请填写${field.label}`"
          />
        </label>
        <p v-if="formError" class="error-text form-error">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit">提交登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script lang="ts">
export default { name: 'RegisterList' }
</script>

<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

interface Stats {
  待登记: number
  已登记: number
  停用中: number
  已注销: number
  在用台数: number
}

interface ActionResult {
  ok: boolean
  message: string
  entry: Row | null
}

const ENDPOINT = '/api/register'
const columns = ['设备编号', '设备名称', '设备种类', '使用单位', '安装地点', '投用日期', '登记证号', '登记状态']
const statuses = ['待登记', '已登记', '停用中', '已注销']
// 与后端状态关口保持一致的按钮收敛规则，服务端仍会二次把关。
const actionsByStatus: Record<string, string[]> = {
  待登记: ['办理登记'],
  已登记: ['申请停用', '申请注销'],
  停用中: ['解停恢复', '申请注销'],
  已注销: [],
}
const formFields = [
  { key: '设备编号', label: '设备编号', required: true },
  { key: '设备名称', label: '设备名称', required: true },
  { key: '设备种类', label: '设备种类', required: true },
  { key: '使用单位', label: '使用单位', required: true },
  { key: '登记证号', label: '登记证号', required: true },
  { key: '安装地点', label: '安装地点', required: false },
  { key: '投用日期', label: '投用日期', required: false, type: 'date' },
]

const router = useRouter()
const session = useSessionStore()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')
const stats = ref<Stats>({ 待登记: 0, 已登记: 0, 停用中: 0, 已注销: 0, 在用台数: 0 })

const statCards = computed(() => [
  { label: '在用台数（已登记）', value: stats.value.在用台数, emphasis: 'card-primary' },
  { label: '待登记设备', value: stats.value.待登记, emphasis: '' },
  { label: '已登记设备', value: stats.value.已登记, emphasis: '' },
  { label: '停用设备', value: stats.value.停用中, emphasis: '' },
  { label: '已注销设备', value: stats.value.已注销, emphasis: '' },
])

const showForm = ref(false)
const form = ref<Record<string, string>>({})
const formError = ref('')
const missingFields = ref<string[]>([])

// 从详情返回时停在原处：组件被 KeepAlive 缓存，记录并恢复滚动位置。
let savedScrollY = 0
onDeactivated(() => {
  savedScrollY = window.scrollY
})
onActivated(() => {
  void nextTick(() => window.scrollTo(0, savedScrollY))
})

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  page.value = 1
  void reload()
}

function changePage(target: number) {
  page.value = target
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openDetail(id: string | number | null) {
  void router.push(`/register/${String(id)}`)
}

function openCreate() {
  form.value = {}
  formError.value = ''
  missingFields.value = []
  showForm.value = true
}

function closeCreate() {
  showForm.value = false
}

async function submitCreate() {
  formError.value = ''
  missingFields.value = formFields
    .filter((field) => field.required && !form.value[field.key]?.trim())
    .map((field) => field.key)
  if (missingFields.value.length) {
    formError.value = `缺少必填字段：${missingFields.value.join('、')}，补齐后才能提交登记。`
    return
  }
  const values: Record<string, string> = { operator: session.operator }
  for (const field of formFields) {
    if (form.value[field.key]?.trim()) {
      values[field.key] = form.value[field.key].trim()
    }
  }
  try {
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = (await response.json()) as ActionResult
    if (!payload.ok) {
      // 重复登记：后端已把内容另存备注，提示用户即可，表单关闭、列表刷新。
      noticeMessage.value = payload.message
      errorMessage.value = ''
      showForm.value = false
      await Promise.all([reload(), loadStats()])
      return
    }
    showForm.value = false
    noticeMessage.value = payload.message
    errorMessage.value = ''
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '设备登记提交失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '申请注销' && !window.confirm(`确认对设备 ${String(row.设备编号 ?? row.id)} 申请注销？注销后不可再改回在用。`)) {
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${String(row.id)}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: session.operator } }),
    })
    const payload = (await response.json()) as ActionResult
    if (!payload.ok) {
      // 跳步/终态操作：后端已说明卡在哪一步，原样点给经手人看。
      errorMessage.value = payload.message
      return
    }
    noticeMessage.value = payload.message
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '使用登记动作未生效，请稍后重试'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      stats.value = (await response.json()) as Stats
    }
  } catch {
    // 统计读不出来不阻断列表操作，卡片保持上一次的值。
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams({
    page: String(page.value),
    size: String(pageSize),
  })
  if (keyword.value.trim()) {
    query.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('设备登记列表读取失败')
    }
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
    if ((page.value - 1) * pageSize >= total.value && page.value > 1) {
      page.value -= 1
      await reload()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '使用登记列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.card-primary {
  border-color: var(--brand);
  background: #f0f6ff;
}
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  background: #eef2f7;
  font-size: 12px;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.link.danger {
  color: #b42318;
}
.pager {
  display: flex;
  gap: 8px;
  align-items: center;
}
.pager .btn {
  padding: 2px 10px;
}
.pager .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.notice-text {
  color: #b54708;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 520px;
  max-height: 86vh;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  padding: 20px 22px;
}
.modal h3 {
  margin: 0 0 4px;
}
.modal-tip {
  color: var(--muted);
  font-size: 12px;
  margin: 0 0 12px;
}
.form-item {
  display: block;
  margin-bottom: 10px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.form-item input.invalid {
  border-color: #b42318;
}
.required-mark {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.form-error {
  margin: 4px 0 8px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
