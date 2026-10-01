<template>
  <section class="page" data-module="register">
    <header class="page-head">
      <div>
        <h2>使用登记管理</h2>
        <p class="page-desc">办完登记才能申请停用，停用中先解停再恢复使用，注销后不可再改回在用；每一步都记录时间与经手人。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记设备</button>
        <button class="btn" type="button" @click="exportRows">导出使用登记清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload()">
      <label class="filter-item">
        <span>设备编号</span>
        <input v-model="keyword" placeholder="按设备编号检索" />
      </label>
      <label class="filter-item">
        <span>登记状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
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
        <tr v-for="row in rows" :key="String(row.id)" class="data-row">
          <td v-for="column in columns" :key="column" class="data-cell" @click="openDetail(row)">
            {{ row[column] || '—' }}
          </td>
          <td class="row-actions">
            <template v-for="action in actionsFor(row)" :key="action.name">
              <button
                class="link"
                :class="{ danger: action.danger }"
                type="button"
                :title="action.tip"
                @click="runAction(action.name, row)"
              >
                {{ action.name }}
              </button>
            </template>
            <span v-if="!actionsFor(row).length" class="muted-text">已注销，终态不可操作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的使用登记数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条使用登记记录（点击任意单元格可查看登记明细）</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>

    <div v-if="creating" class="modal-mask" @click.self="closeCreate">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记设备</h3>
        <p class="modal-tip">标 <em>*</em> 为必填，缺一项都会点名退回；同一设备编号重复提交只另存备注，不覆盖原记录。</p>
        <label v-for="field in formFields" :key="field" class="form-item">
          <span>{{ field }}<em v-if="isRequired(field)">*</em></span>
          <input v-model="form[field]" :placeholder="`请输入${field}`" />
        </label>
        <label class="form-item">
          <span>经手人</span>
          <input v-model="formOperator" placeholder="默认取当前值班人" />
        </label>
        <label class="form-item wide">
          <span>备注（可选）</span>
          <textarea v-model="formRemark" rows="2" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit">提交登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onActivated, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

defineOptions({ name: 'RegisterList' })

type AuditRecord = { 时间: string; 经手人: string; 动作: string; 变更前: string; 变更后: string }
type Row = Record<string, string | number | null> & {
  status: string
  流转记录?: AuditRecord[]
  重复登记备注?: string
}
type Stat = { label: string; value: number }

const ENDPOINT = '/api/register'
const router = useRouter()
const session = useSessionStore()

const columns = ['设备编号', '设备名称', '设备种类', '使用单位', '安装地点', '投用日期', '登记证号', '登记状态']
const formFields = ['设备编号', '设备名称', '设备种类', '使用单位', '安装地点', '投用日期', '登记证号']
const requiredFields = ['设备编号', '使用单位', '登记证号']
const statuses = ['待登记', '已登记', '停用中', '已注销']

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Stat[]>([
  { label: '总台数', value: 0 },
  { label: '待登记', value: 0 },
  { label: '在用台数', value: 0 },
  { label: '停用台数', value: 0 },
  { label: '已注销', value: 0 },
])
const message = ref('')
const messageOk = ref(true)

const keyword = ref('')
const statusFilter = ref('')

const creating = ref(false)
const form = reactive<Record<string, string>>({})
const formOperator = ref(session.operator)
const formRemark = ref('')
const createError = ref('')

// 各状态允许的动作严格对齐后端状态链，前端先拦一道；漏网的跳步仍由后端退回
const ACTION_MATRIX: Record<string, { name: string; danger?: boolean; tip: string }[]> = {
  待登记: [{ name: '办理登记', tip: '先办完登记，设备才能进入在用' }],
  已登记: [{ name: '申请停用', tip: '在用设备申请停用' }],
  停用中: [
    { name: '解停恢复', tip: '先解停，设备才能恢复在用' },
    { name: '申请注销', danger: true, tip: '确认报废后注销，注销不可恢复' },
  ],
  已注销: [],
}

let firstActivation = true

function actionsFor(row: Row) {
  return ACTION_MATRIX[row.status] ?? []
}

function isRequired(field: string) {
  return requiredFields.includes(field)
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function openCreate() {
  for (const field of formFields) form[field] = ''
  formOperator.value = session.operator
  formRemark.value = ''
  createError.value = ''
  creating.value = true
}

function closeCreate() {
  creating.value = false
}

function openDetail(row: Row) {
  void router.push({ name: 'register-detail', params: { id: row.id } })
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function submitCreate() {
  createError.value = ''
  // 提交前先本地点名，缺哪一项直接标出来，不白跑一次请求
  const missing = requiredFields.filter((field) => !form[field]?.trim())
  if (missing.length) {
    createError.value = `登记未提交：缺少必填项${missing.join('、')}，请补全后再提交`
    return
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: { ...form, operator: formOperator.value.trim() || session.operator },
        remark: formRemark.value.trim() || null,
      }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      createError.value = payload?.message ? String(payload.message) : '登记提交失败，请稍后重试'
      return
    }
    creating.value = false
    flash(String(payload.message), true)
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '登记提交失败'
  }
}

async function runAction(action: string, row: Row) {
  if (action === '申请注销' && !window.confirm(`确认注销设备「${row.设备编号}」？注销后不可再改回在用。`)) {
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: session.operator } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      // 跳步申请当场退回，并说明卡在哪一步
      flash(payload?.message ? String(payload.message) : `${action}未生效，请稍后重试`, false)
      return
    }
    flash(String(payload.message), true)
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : `${action}请求失败`, false)
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      const data = await response.json()
      stats.value = [
        { label: '总台数', value: data.总台数 ?? 0 },
        { label: '待登记', value: data.待登记 ?? 0 },
        { label: '在用台数', value: data.在用台数 ?? 0 },
        { label: '停用台数', value: data.停用中 ?? 0 },
        { label: '已注销', value: data.已注销 ?? 0 },
      ]
    }
  } catch {
    // 统计拉取失败不阻断列表操作，下次刷新自动重试
  }
}

async function reload(showMessage = false) {
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('设备登记列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (showMessage) flash('列表已按最新登记明细重算', true)
  } catch (error) {
    flash(error instanceof Error ? error.message : '使用登记列表读取失败', false)
  }
  await loadStats()
}

function flash(text: string, ok: boolean) {
  message.value = text
  messageOk.value = ok
}

onMounted(() => {
  void reload()
})

// 从详情返回时组件被缓存：首次激活已由 onMounted 加载，之后返回才刷新；
// 筛选条件与滚动位置随缓存保留，停在原处。
onActivated(() => {
  if (firstActivation) {
    firstActivation = false
    return
  }
  void reload()
})
</script>

<style scoped>
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
  width: 560px;
  max-height: 86vh;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal h3 { margin: 0 0 4px; }
.modal-tip { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
.modal-tip em, .form-item em { color: #d92d20; font-style: normal; }
.form-item { display: block; margin-bottom: 10px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.form-item input, .form-item textarea {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font: inherit;
}
.modal { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.modal h3, .modal-tip, .form-item.wide, .modal .error-text, .modal-actions { grid-column: 1 / -1; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
.data-row { cursor: pointer; }
.data-cell:hover { background: #f1f6ff; }
.row-actions { cursor: default; white-space: nowrap; }
.link.danger { color: #b42318; }
.muted-text { color: var(--muted); font-size: 12px; }
.ok-text { color: #027a48; }
</style>
