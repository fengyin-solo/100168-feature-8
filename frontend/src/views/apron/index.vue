<template>
  <section class="page" data-module="apron">
    <header class="page-head">
      <div>
        <h2>机坪巡查管理</h2>
        <p class="page-desc">巡查单按巡查项目逐项登记发现问题数，整改完成回填结论与整改人后闭环；发现问题数可按巡查区域汇总。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记巡查单</button>
        <button class="btn" type="button" @click="exportRows">导出机坪巡查清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>巡查单号</span>
        <input v-model="filters.keyword" placeholder="按巡查单号检索" />
      </label>
      <label class="filter-item">
        <span>巡查状态</span>
        <select v-model="filters.status">
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
          <td v-for="column in columns" :key="column">{{ cellText(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">明细</button>
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="openAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!actionsFor(row).length" class="muted-text">无</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无机坪巡查数据，可先登记巡查单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条机坪巡查记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="summary-block">
      <h3>巡查区域问题汇总</h3>
      <p class="page-desc">与巡查单列表共用同一套筛选口径，发现问题数合计与列表逐条相加一致。</p>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in summaryColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in summaryRows" :key="item['巡查区域']">
            <td v-for="column in summaryColumns" :key="column">{{ item[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!summaryRows.length">
            <td :colspan="summaryColumns.length" class="empty-state">当前筛选条件下暂无汇总数据</td>
          </tr>
          <tr v-if="summaryRows.length" class="summary-total">
            <td v-for="column in summaryColumns" :key="column">{{ summaryTotal[column] ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 登记巡查单 -->
    <div v-if="createModal.open" class="modal-mask" @click.self="closeModals">
      <div class="modal">
        <h3>登记巡查单</h3>
        <div class="form-grid">
          <label v-for="field in createFields" :key="field" class="form-item">
            <span>{{ field }}</span>
            <input v-model="createModal.form[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <p v-if="createModal.error" class="error-text">{{ createModal.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeModals">取消</button>
          <button class="btn primary" type="button" @click="submitCreate">登记</button>
        </div>
      </div>
    </div>

    <!-- 提交结果：逐项登记发现问题数 -->
    <div v-if="findingsModal.open" class="modal-mask" @click.self="closeModals">
      <div class="modal modal-wide">
        <h3>提交巡查结果 · {{ findingsModal.code }}</h3>
        <table class="data-table inner-table">
          <thead>
            <tr>
              <th>巡查项目</th>
              <th style="width: 150px">发现问题数</th>
              <th style="width: 60px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in findingsModal.items" :key="index">
              <td><input v-model="item.巡查项目" placeholder="如：道面标志" /></td>
              <td>
                <input v-model.number="item.发现问题数" type="number" min="0" step="1" placeholder="非负整数" />
              </td>
              <td><button class="link" type="button" @click="findingsModal.items.splice(index, 1)">移除</button></td>
            </tr>
          </tbody>
        </table>
        <button class="btn" type="button" @click="addFindingRow">增加巡查项目</button>
        <label class="form-item duration-item">
          <span>巡查时长</span>
          <input v-model="findingsModal.duration" placeholder="如：60 分钟" />
        </label>
        <p v-if="findingsModal.error" class="error-text">{{ findingsModal.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeModals">取消</button>
          <button class="btn primary" type="button" @click="submitFindings">提交结果</button>
        </div>
      </div>
    </div>

    <!-- 提交整改：回填整改结论与整改人 -->
    <div v-if="repairModal.open" class="modal-mask" @click.self="closeModals">
      <div class="modal modal-wide">
        <h3>提交整改结论 · {{ repairModal.code }}</h3>
        <table class="data-table inner-table">
          <thead>
            <tr>
              <th>巡查项目</th>
              <th style="width: 90px">发现问题数</th>
              <th>整改结论</th>
              <th style="width: 130px">整改人</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in repairModal.items" :key="index">
              <td>{{ item.巡查项目 }}</td>
              <td>{{ item.发现问题数 }}</td>
              <td><input v-model="item.整改结论" placeholder="回填整改结论" /></td>
              <td><input v-model="item.整改人" placeholder="回填整改人" /></td>
            </tr>
          </tbody>
        </table>
        <p class="page-desc">同一条巡查单重复提交整改结论只保留最后一次；全部事项回填后巡查单才会闭环。</p>
        <p v-if="repairModal.error" class="error-text">{{ repairModal.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeModals">取消</button>
          <button class="btn primary" type="button" @click="submitRepair">提交整改</button>
        </div>
      </div>
    </div>

    <!-- 明细：逐项问题、整改回填与操作留痕 -->
    <div v-if="detailModal.open" class="modal-mask" @click.self="closeModals">
      <div class="modal modal-wide">
        <h3>巡查单明细 · {{ detailModal.row?.['巡查单号'] }}</h3>
        <table class="data-table inner-table">
          <thead>
            <tr>
              <th>巡查项目</th>
              <th>发现问题数</th>
              <th>整改结论</th>
              <th>整改人</th>
              <th>整改时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in detailItems" :key="index">
              <td>{{ item['巡查项目'] }}</td>
              <td>{{ item['发现问题数'] }}</td>
              <td>{{ item['整改结论'] || '—' }}</td>
              <td>{{ item['整改人'] || '—' }}</td>
              <td>{{ item['整改时间'] || '—' }}</td>
            </tr>
            <tr v-if="!detailItems.length">
              <td colspan="5" class="empty-state">尚未提交巡查结果</td>
            </tr>
          </tbody>
        </table>
        <h4>操作留痕</h4>
        <ul class="audit-list">
          <li v-for="(log, index) in detailLogs" :key="index">
            <span>{{ log['时间'] }}</span>
            <span>{{ log['动作'] }}</span>
            <span :class="log['结果'] === '成功' ? 'ok-text' : 'error-text'">{{ log['结果'] }}</span>
            <span>{{ log['说明'] }}</span>
          </li>
          <li v-if="!detailLogs.length" class="muted-text">暂无留痕</li>
        </ul>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="closeModals">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type ItemRow = {
  巡查项目: string
  发现问题数: number | string
  整改结论?: string
  整改人?: string
  整改时间?: string
}

type AuditLog = {
  时间: string
  动作: string
  结果: string
  说明: string
}

type Row = Record<string, string | number | boolean | null | ItemRow[] | AuditLog[]> & {
  id: number
  status: string
  items?: ItemRow[]
  操作留痕?: AuditLog[]
}

type SummaryBucket = Record<string, string | number>

const ENDPOINT = '/api/apron'
const columns = ['巡查单号', '巡查区域', '巡查人员', '巡查日期', '巡查项目', '发现问题数', '整改情况', '整改人', '巡查时长', '巡查状态']
const summaryColumns = ['巡查区域', '巡查单数', '发现问题数', '待整改数', '已整改数', '本月发现问题']
const statuses = ['待派发', '巡查中', '已提交', '已整改', '已作废']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })
const stats = ref([
  { label: '待派发巡查', value: 0 },
  { label: '巡查中任务', value: 0 },
  { label: '本月发现问题', value: 0 },
])
const summaryRows = ref<SummaryBucket[]>([])
const summaryTotal = ref<SummaryBucket>({})

const createFields = ['巡查单号', '巡查区域', '巡查人员', '巡查日期']
const createModal = reactive<{ open: boolean; form: Record<string, string>; error: string }>({
  open: false,
  form: {},
  error: '',
})
const findingsModal = reactive<{
  open: boolean
  id: number | null
  code: string
  duration: string
  items: ItemRow[]
  error: string
}>({ open: false, id: null, code: '', duration: '', items: [], error: '' })
const repairModal = reactive<{
  open: boolean
  id: number | null
  code: string
  items: ItemRow[]
  error: string
}>({ open: false, id: null, code: '', items: [], error: '' })
const detailModal = reactive<{ open: boolean; row: Row | null }>({ open: false, row: null })

const detailItems = computed<ItemRow[]>(() => (detailModal.row?.items as ItemRow[] | undefined) ?? [])
const detailLogs = computed<AuditLog[]>(() => (detailModal.row?.['操作留痕'] as AuditLog[] | undefined) ?? [])

function queryString() {
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.status) params.set('status', filters.status)
  return params.toString()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function closeModals() {
  createModal.open = false
  findingsModal.open = false
  repairModal.open = false
  detailModal.open = false
}

function repairProgress(row: Row) {
  const items = (row.items as ItemRow[] | undefined) ?? []
  const problemItems = items.filter((item) => Number(item.发现问题数) > 0)
  if (!problemItems.length) return null
  const done = problemItems.filter((item) => (item.整改结论 ?? '').trim() && (item.整改人 ?? '').trim()).length
  return { done, total: problemItems.length }
}

function repairerText(row: Row) {
  const items = (row.items as ItemRow[] | undefined) ?? []
  const names = Array.from(
    new Set(items.map((item) => (item.整改人 ?? '').trim()).filter(Boolean)),
  )
  return names.join('、')
}

function cellText(row: Row, column: string) {
  if (column === '巡查状态') return row.status ?? '—'
  if (column === '整改情况') {
    const progress = repairProgress(row)
    if (!progress) return '—'
    return progress.done === progress.total
      ? `已整改 ${progress.done}/${progress.total} 项`
      : `待整改 ${progress.total - progress.done} 项（已回填 ${progress.done}）`
  }
  if (column === '整改人') return repairerText(row) || '—'
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function actionsFor(row: Row): string[] {
  switch (row.status) {
    case '待派发':
      return ['派发巡查', '作废巡查']
    case '巡查中':
      return ['提交结果', '作废巡查']
    case '已提交':
      return ['提交整改', '作废巡查']
    default:
      return []
  }
}

function openCreate() {
  createModal.form = Object.fromEntries(createFields.map((field) => [field, '']))
  createModal.error = ''
  createModal.open = true
}

async function submitCreate() {
  createModal.error = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createModal.form }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createModal.error = payload.message || '巡查单登记失败'
      return
    }
    closeModals()
    await reload()
  } catch (error) {
    createModal.error = error instanceof Error ? error.message : '巡查单登记失败'
  }
}

function openDetail(row: Row) {
  detailModal.row = row
  detailModal.open = true
}

function addFindingRow() {
  findingsModal.items.push({ 巡查项目: '', 发现问题数: '' })
}

function openAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '提交结果') {
    findingsModal.id = row.id
    findingsModal.code = String(row['巡查单号'] ?? '')
    findingsModal.duration = typeof row['巡查时长'] === 'string' ? row['巡查时长'] : ''
    findingsModal.items = [{ 巡查项目: '', 发现问题数: '' }]
    findingsModal.error = ''
    findingsModal.open = true
    return
  }
  if (action === '提交整改') {
    repairModal.id = row.id
    repairModal.code = String(row['巡查单号'] ?? '')
    repairModal.items = ((row.items as ItemRow[] | undefined) ?? [])
      .filter((item) => Number(item.发现问题数) > 0)
      .map((item) => ({ ...item }))
    repairModal.error = ''
    repairModal.open = true
    return
  }
  void runSimpleAction(action, row)
}

async function runSimpleAction(action: string, row: Row) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '机坪巡查动作未生效'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '机坪巡查操作失败'
  }
}

async function submitFindings() {
  findingsModal.error = ''
  const names = new Set<string>()
  for (const item of findingsModal.items) {
    const name = item.巡查项目.trim()
    const raw = item.发现问题数
    if (!name) {
      findingsModal.error = '每个巡查项目都要填写项目名称'
      return
    }
    if (names.has(name)) {
      findingsModal.error = `巡查项目「${name}」重复登记`
      return
    }
    names.add(name)
    if (raw === '' || raw === null || Number(raw) < 0 || !Number.isInteger(Number(raw))) {
      findingsModal.error = `巡查项目「${name}」的发现问题数空缺或为负数，请填写非负整数`
      return
    }
  }
  if (!findingsModal.items.length) {
    findingsModal.error = '至少登记一个巡查项目'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${findingsModal.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action: '提交结果',
          巡查时长: findingsModal.duration,
          items: findingsModal.items.map((item) => ({
            巡查项目: item.巡查项目.trim(),
            发现问题数: Number(item.发现问题数),
          })),
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      findingsModal.error = payload.message || '巡查结果提交失败'
      return
    }
    closeModals()
    await reload()
  } catch (error) {
    findingsModal.error = error instanceof Error ? error.message : '巡查结果提交失败'
  }
}

async function submitRepair() {
  repairModal.error = ''
  for (const item of repairModal.items) {
    if (!(item.整改结论 ?? '').trim() || !(item.整改人 ?? '').trim()) {
      repairModal.error = `巡查项目「${item.巡查项目}」的整改结论与整改人都必须回填`
      return
    }
  }
  try {
    const response = await request(`${ENDPOINT}/${repairModal.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action: '提交整改',
          items: repairModal.items.map((item) => ({
            巡查项目: item.巡查项目,
            整改结论: (item.整改结论 ?? '').trim(),
            整改人: (item.整改人 ?? '').trim(),
          })),
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      repairModal.error = payload.message || '整改结论提交失败'
      return
    }
    closeModals()
    await reload()
  } catch (error) {
    repairModal.error = error instanceof Error ? error.message : '整改结论提交失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = queryString()
  try {
    const [listPayload, summaryPayload, pendingPayload, inspectingPayload] = await Promise.all([
      fetchList(query),
      fetchSummary(query),
      fetchStatusCount('待派发'),
      fetchStatusCount('巡查中'),
    ])
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    summaryRows.value = summaryPayload.items ?? []
    summaryTotal.value = summaryPayload.total ?? {}
    stats.value[0].value = pendingPayload
    stats.value[1].value = inspectingPayload
    stats.value[2].value = Number(summaryTotal.value['本月发现问题'] ?? 0)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '机坪巡查列表读取失败'
  }
}

async function fetchList(query: string) {
  const response = await request(`${ENDPOINT}?${query}`)
  if (!response.ok) throw new Error('巡查单列表读取失败')
  return response.json()
}

async function fetchSummary(query: string) {
  const response = await request(`${ENDPOINT}/areas/summary?${query}`)
  if (!response.ok) throw new Error('巡查区域汇总读取失败')
  return response.json()
}

async function fetchStatusCount(status: string) {
  const params = new URLSearchParams({ status, page: '1', size: '1' })
  const response = await request(`${ENDPOINT}?${params.toString()}`)
  if (!response.ok) return 0
  const payload = await response.json()
  return Number(payload.total ?? 0)
}

onMounted(reload)
</script>

<style scoped>
.muted-text { color: var(--muted); font-size: 12px; }
.ok-text { color: #067647; }
.summary-block { margin-top: 20px; }
.summary-block h3 { margin: 8px 0; font-size: 15px; }
.summary-total td { font-weight: 600; background: #f1f5fb; }
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
  width: 480px;
  max-height: 86vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-wide { width: 720px; }
.modal h3 { margin: 0 0 12px; font-size: 16px; }
.modal h4 { margin: 14px 0 6px; font-size: 14px; }
.form-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-item input, .form-grid .form-item { flex: 1 1 200px; }
.form-item input { width: 100%; }
.duration-item { margin: 10px 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.inner-table { margin-bottom: 10px; }
.inner-table input { width: 100%; border: 1px solid var(--border); border-radius: 4px; padding: 4px 6px; }
.audit-list { list-style: none; margin: 0; padding: 0; font-size: 12px; max-height: 180px; overflow-y: auto; }
.audit-list li { display: flex; gap: 10px; padding: 4px 0; border-bottom: 1px dashed var(--border); }
.audit-list li span:nth-child(2) { min-width: 64px; }
.audit-list li span:nth-child(3) { min-width: 36px; }
.filter-item select { border: 1px solid var(--border); border-radius: 4px; padding: 5px 6px; }
</style>
