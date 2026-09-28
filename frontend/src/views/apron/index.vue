<template>
  <section class="page" data-module="apron">
    <header class="page-head">
      <div>
        <h2>机坪巡查管理</h2>
        <p class="page-desc">巡查单提交时按巡查项目逐项登记发现问题数并生成待整改事项；整改完成后逐条回填整改结论与整改人，全部回填后才能闭环。</p>
      </div>
      <div class="page-actions">
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
        <span>巡查区域</span>
        <input v-model="filters.area" placeholder="按巡查区域检索" />
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
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看明细</button>
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无机坪巡查数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条机坪巡查记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="summary-block">
      <h3>按巡查区域汇总（与列表同一筛选口径，刷新后仍成立）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in summaryColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in summaryRows" :key="item['巡查区域']">
            <td v-for="column in summaryColumns" :key="column">{{ item[column] }}</td>
          </tr>
          <tr v-if="!summaryRows.length">
            <td :colspan="summaryColumns.length" class="empty-state">当前筛选条件下没有可汇总的巡查单</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 巡查单明细：待整改事项与操作留痕（含失败尝试） -->
    <div v-if="detailOpen" class="modal-mask" @click.self="detailOpen = false">
      <div class="modal modal-wide">
        <h3>巡查单明细 · {{ detail.单号 }}</h3>
        <p class="modal-tip">
          当前状态：{{ detail.status }} ｜ 发现问题数：{{ detail.发现问题数 }} ｜ 待整改事项：{{ detail.items.length }} 条
        </p>
        <table v-if="detail.items.length" class="data-table modal-table">
          <thead>
            <tr>
              <th>事项编号</th>
              <th>巡查项目</th>
              <th>发现问题数</th>
              <th>整改结论</th>
              <th>整改人</th>
              <th>整改时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in detail.items" :key="item.事项编号">
              <td>{{ item.事项编号 }}</td>
              <td>{{ item.巡查项目 }}</td>
              <td>{{ item.发现问题数 }}</td>
              <td :class="{ 'cell-pending': !item.整改结论 }">{{ item.整改结论 || '待回填' }}</td>
              <td>{{ item.整改人 || '—' }}</td>
              <td>{{ item.整改时间 || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">该巡查单暂无待整改事项</p>

        <h4 class="trace-title">操作留痕</h4>
        <ul class="trace-list">
          <li v-for="(trace, index) in detail.traces" :key="index" :class="{ 'trace-fail': trace.结果 === '失败' }">
            <span class="trace-time">{{ trace.时间 }}</span>
            <span class="trace-action">{{ trace.动作 }}（{{ trace.结果 }}）</span>
            <span class="trace-detail">{{ trace.说明 }}</span>
          </li>
          <li v-if="!detail.traces.length" class="empty-state">暂无操作留痕</li>
        </ul>
        <footer class="modal-foot">
          <span class="modal-buttons">
            <button class="btn primary" type="button" @click="detailOpen = false">关闭</button>
          </span>
        </footer>
      </div>
    </div>

    <!-- 提交结果：逐项登记巡查项目与发现问题数 -->
    <div v-if="submitOpen" class="modal-mask" @click.self="submitOpen = false">
      <div class="modal">
        <h3>提交巡查结果 · {{ submitForm.单号 }}</h3>
        <p class="modal-tip">按巡查项目逐项登记发现问题数；发现问题数空缺或为负数时无法提交。问题数大于 0 的项目会自动生成待整改事项。</p>
        <div class="modal-grid">
          <label>
            <span>巡查日期</span>
            <input v-model="submitForm.巡查日期" placeholder="如 2026-09-28" />
          </label>
          <label>
            <span>巡查时长</span>
            <input v-model="submitForm.巡查时长" placeholder="如 60分钟" />
          </label>
        </div>
        <table class="data-table modal-table">
          <thead>
            <tr>
              <th>巡查项目</th>
              <th>发现问题数（非负整数）</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in submitForm.items" :key="index">
              <td><input v-model="item.巡查项目" placeholder="如 道面巡查" /></td>
              <td><input v-model="item.发现问题数" inputmode="numeric" placeholder="0" /></td>
              <td>
                <button class="link" type="button" @click="removeSubmitItem(index)" :disabled="submitForm.items.length <= 1">移除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <button class="btn" type="button" @click="addSubmitItem">+ 增加巡查项目</button>
        <footer class="modal-foot">
          <span v-if="modalError" class="error-text">{{ modalError }}</span>
          <span class="modal-buttons">
            <button class="btn ghost" type="button" @click="submitOpen = false">取消</button>
            <button class="btn primary" type="button" @click="confirmSubmit">提交结果</button>
          </span>
        </footer>
      </div>
    </div>

    <!-- 回填整改：逐条回填整改结论与整改人，重复提交只保留最后一次 -->
    <div v-if="rectifyOpen" class="modal-mask" @click.self="rectifyOpen = false">
      <div class="modal modal-wide">
        <h3>回填整改结论 · {{ rectifyForm.单号 }}</h3>
        <p class="modal-tip">逐事项回填整改结论与整改人，两者都不能为空；同一条巡查单重复提交整改结论时只保留最后一次。</p>
        <table class="data-table modal-table">
          <thead>
            <tr>
              <th>巡查项目</th>
              <th>发现问题数</th>
              <th>整改结论</th>
              <th>整改人</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in rectifyForm.items" :key="item.事项编号">
              <td>{{ item.巡查项目 }}</td>
              <td>{{ item.发现问题数 }}</td>
              <td>
                <textarea
                  v-model="item.整改结论"
                  rows="2"
                  :placeholder="item.发现问题数 === 0 ? '本项无问题，可留空' : '请填写整改结论'"
                ></textarea>
              </td>
              <td>
                <input
                  v-model="item.整改人"
                  :placeholder="item.发现问题数 === 0 ? '—' : '请填写整改人'"
                  :disabled="item.发现问题数 === 0"
                />
              </td>
            </tr>
          </tbody>
        </table>
        <footer class="modal-foot">
          <span v-if="modalError" class="error-text">{{ modalError }}</span>
          <span class="modal-buttons">
            <button class="btn ghost" type="button" @click="rectifyOpen = false">取消</button>
            <button class="btn primary" type="button" @click="confirmRectify">提交整改结论</button>
          </span>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null | RectifyItem[]>
type RectifyItem = {
  事项编号: string
  巡查项目: string
  发现问题数: number
  整改结论: string | null
  整改人: string | null
  整改时间: string | null
}
type SummaryRow = Record<string, string | number>
type SubmitItem = { 巡查项目: string; 发现问题数: string }
type RectifyDraft = RectifyItem & { 整改结论: string | null; 整改人: string | null }
type Trace = { 时间: string; 动作: string; 结果: string; 说明: string }

const ENDPOINT = '/api/apron'
const columns = ["巡查单号", "巡查区域", "巡查人员", "巡查日期", "巡查项目", "发现问题数", "待整改数", "巡查时长", "巡查状态"]
const summaryColumns = ["巡查区域", "巡查单数", "发现问题数", "待整改数", "已整改数"]
const statuses = ["待派发", "巡查中", "已提交", "已整改", "已作废"]

const rows = ref<Row[]>([])
const total = ref(0)
const summaryRows = ref<SummaryRow[]>([])
const errorMessage = ref('')
const filters = reactive<{ keyword: string; area: string; status: string }>({ keyword: '', area: '', status: '' })

const submitOpen = ref(false)
const rectifyOpen = ref(false)
const modalError = ref('')
const submitForm = reactive<{ id: number | null; 单号: string; 巡查日期: string; 巡查时长: string; items: SubmitItem[] }>({
  id: null,
  单号: '',
  巡查日期: '',
  巡查时长: '',
  items: [{ 巡查项目: '', 发现问题数: '' }],
})
const rectifyForm = reactive<{ id: number | null; 单号: string; items: RectifyDraft[] }>({
  id: null,
  单号: '',
  items: [],
})
const detailOpen = ref(false)
const detail = reactive<{
  单号: string
  status: string
  发现问题数: number
  items: RectifyItem[]
  traces: Trace[]
}>({
  单号: '',
  status: '',
  发现问题数: 0,
  items: [],
  traces: [],
})

const stats = computed(() => {
  const pendingOrders = rows.value.filter((row) => Number(row['待整改数']) > 0).length
  const foundProblems = rows.value.reduce((sum, row) => sum + Number(row['发现问题数'] || 0), 0)
  const pendingItems = rows.value.reduce((sum, row) => sum + Number(row['待整改数'] || 0), 0)
  return [
    { label: '筛选命中巡查单', value: total.value },
    { label: '本页发现问题', value: foundProblems },
    { label: '本页待整改事项', value: pendingItems },
    { label: '本页待整改巡查单', value: pendingOrders },
  ]
})

function queryString() {
  const params: Record<string, string> = {}
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
  if (filters.area.trim()) params.area = filters.area.trim()
  if (filters.status) params.status = filters.status
  return new URLSearchParams(params).toString()
}

function resetFilters() {
  filters.keyword = ''
  filters.area = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${queryString()}`, '_blank')
}

function displayValue(row: Row, column: string) {
  if (column === '巡查状态') return String(row.status ?? '')
  const value = row[column]
  if (value === null || value === undefined || value === '') return '—'
  return value
}

function pendingItems(row: Row): RectifyItem[] {
  const items = Array.isArray(row['待整改事项']) ? (row['待整改事项'] as RectifyItem[]) : []
  return items.filter((item) => Number(item.发现问题数) > 0)
}

function availableActions(row: Row): string[] {
  switch (row.status) {
    case '待派发':
      return ['派发巡查', '作废巡查']
    case '巡查中':
      return ['提交结果', '作废巡查']
    case '已提交':
      return pendingItems(row).length ? ['回填整改', '完成整改'] : []
    default:
      return []
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('巡查单明细读取失败')
    }
    const entry = (await response.json()) as Record<string, unknown>
    detail.单号 = String(entry['巡查单号'] ?? '')
    detail.status = String(entry.status ?? '')
    detail.发现问题数 = Number(entry['发现问题数'] || 0)
    detail.items = Array.isArray(entry['待整改事项']) ? (entry['待整改事项'] as RectifyItem[]) : []
    detail.traces = Array.isArray(entry['操作留痕']) ? (entry['操作留痕'] as Trace[]) : []
    detailOpen.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡查单明细读取失败'
  }
}

function addSubmitItem() {
  submitForm.items.push({ 巡查项目: '', 发现问题数: '' })
}

function removeSubmitItem(index: number) {
  submitForm.items.splice(index, 1)
}

function openSubmit(row: Row) {
  modalError.value = ''
  submitForm.id = Number(row.id)
  submitForm.单号 = String(row['巡查单号'])
  submitForm.巡查日期 = String(row['巡查日期'] ?? '')
  submitForm.巡查时长 = String(row['巡查时长'] ?? '')
  const projectText = String(row['巡查项目'] ?? '')
  const names = projectText ? projectText.split(/[、,，]/).map((name) => name.trim()).filter(Boolean) : []
  submitForm.items = names.length
    ? names.map((name) => ({ 巡查项目: name, 发现问题数: '' }))
    : [{ 巡查项目: '', 发现问题数: '' }]
  submitOpen.value = true
}

function openRectify(row: Row) {
  modalError.value = ''
  rectifyForm.id = Number(row.id)
  rectifyForm.单号 = String(row['巡查单号'])
  rectifyForm.items = pendingItems(row).map((item) => ({
    ...item,
    整改结论: item.整改结论 ?? '',
    整改人: item.整改人 ?? '',
  }))
  rectifyOpen.value = true
}

async function postAction(action: string, id: number, values: Record<string, unknown>): Promise<{ ok: boolean; message: string }> {
  const response = await request(`${ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action, ...values } }),
  })
  return (await response.json()) as { ok: boolean; message: string }
}

async function confirmSubmit() {
  modalError.value = ''
  if (!submitForm.items.length || submitForm.items.some((item) => !item.巡查项目.trim())) {
    modalError.value = '每个巡查项目都需要填写项目名称'
    return
  }
  if (submitForm.items.some((item) => item.发现问题数.trim() === '')) {
    modalError.value = '发现问题数不能为空，请逐项填写非负整数（无问题填 0）'
    return
  }
  if (submitForm.items.some((item) => !/^\d+$/.test(item.发现问题数.trim()))) {
    modalError.value = '发现问题数必须是非负整数，不能为负数或小数'
    return
  }
  if (submitForm.id === null) return
  const result = await postAction('提交结果', submitForm.id, {
    巡查日期: submitForm.巡查日期,
    巡查时长: submitForm.巡查时长,
    问题明细: submitForm.items.map((item) => ({
      巡查项目: item.巡查项目.trim(),
      发现问题数: Number(item.发现问题数.trim()),
    })),
  })
  if (!result.ok) {
    modalError.value = result.message
    return
  }
  submitOpen.value = false
  await reload()
}

async function confirmRectify() {
  modalError.value = ''
  if (rectifyForm.items.some((item) => !String(item.整改结论 ?? '').trim() || !String(item.整改人 ?? '').trim())) {
    modalError.value = '每条待整改事项的整改结论与整改人都必须回填'
    return
  }
  if (rectifyForm.id === null) return
  const result = await postAction('回填整改', rectifyForm.id, {
    整改明细: rectifyForm.items.map((item) => ({
      事项编号: item.事项编号,
      整改结论: String(item.整改结论 ?? '').trim(),
      整改人: String(item.整改人 ?? '').trim(),
    })),
  })
  if (!result.ok) {
    modalError.value = result.message
    return
  }
  rectifyOpen.value = false
  await reload()
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '提交结果') {
    openSubmit(row)
    return
  }
  if (action === '回填整改') {
    openRectify(row)
    return
  }
  try {
    const result = await postAction(action, Number(row.id), {})
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '机坪巡查操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = queryString()
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/summary?${query}`),
    ])
    if (!listResponse.ok) {
      throw new Error('巡查单列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      const summaryPayload = await summaryResponse.json()
      summaryRows.value = summaryPayload.items ?? []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '机坪巡查列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.summary-block {
  margin-top: 20px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.summary-block h3 {
  margin: 0 0 10px;
  font-size: 14px;
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
  width: 560px;
  max-height: 86vh;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-wide {
  width: 820px;
}
.modal h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.modal-tip {
  color: var(--muted);
  font-size: 12px;
  margin: 0 0 12px;
}
.modal-grid {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.modal-grid label,
.modal-table input,
.modal-table textarea {
  width: 100%;
}
.modal-grid label span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.modal-table {
  margin-bottom: 10px;
}
.modal-table input,
.modal-table textarea {
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font: inherit;
}
.modal-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}
.modal-buttons {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.filter-item select {
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.cell-pending {
  color: #b42318;
}
.trace-title {
  margin: 14px 0 8px;
  font-size: 13px;
}
.trace-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.trace-list li {
  display: flex;
  gap: 10px;
  padding: 6px 10px;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}
.trace-list li:last-child {
  border-bottom: none;
}
.trace-list li.trace-fail {
  background: #fef3f2;
}
.trace-time {
  color: var(--muted);
  white-space: nowrap;
}
.trace-action {
  white-space: nowrap;
  min-width: 130px;
}
.trace-fail .trace-action {
  color: #b42318;
}
.trace-detail {
  color: #334155;
}
</style>
