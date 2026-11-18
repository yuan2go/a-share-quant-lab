// TSP Page Pack SDK v1: fully standalone read-only research view.
// The v0.3.37 ctx.api bridge has no generic route method. A single scoped,
// same-origin GET uses the host's existing session; no API key is sent.
// All untrusted model/output strings go through textContent, never innerHTML.
const eid = 'aql.research'
const style = {
  shell: 'font-family:inherit;max-width:1080px;margin:0 auto;padding:24px;color:var(--foreground,inherit)',
  dim: 'opacity:.72;font-size:13px',
  table: 'width:100%;border-collapse:collapse;font-size:14px',
  cell: 'padding:10px 12px;border-bottom:1px solid var(--border,#ddd);text-align:left',
  card: 'border:1px solid var(--border,#ddd);border-radius:12px;padding:20px;margin-top:16px'
}
function element(tag, parent, text, css) {
  const e = document.createElement(tag)
  if (text != null) e.textContent = String(text)
  if (css) e.style.cssText = css
  parent.appendChild(e)
  return e
}
function metric(value) {
  return Number.isFinite(value) ? value.toFixed(5) : '—'
}

function renderBatch(panel, latest, historical) {
  const interval = latest.prediction_interval
  element('h3', panel, '10 期上涨概率')
  element('p', panel, '数据截至 ' + latest.data_through + ' · 生成于 ' + latest.generated_at)
  element('p', panel, '预测区间 ' + (interval.start_date ?? '未知') + ' 收盘 至 ' + (interval.end_date ?? '未知') + ' 收盘')
  element('p', panel, latest.work_package + ' · 模型 ' + latest.model_id, style.dim + ';overflow-wrap:anywhere')
  element('p', panel, [latest.data_status, latest.model_status, latest.status, latest.calibration_status, latest.issuance_status, latest.qualification].join(' · '), style.dim)
  element('p', panel, '历史校准 log loss · 原方案 ' + metric(historical.original_loss) + ' · ' + historical.original +
    ' · 重拟合 ' + metric(historical.candidate_loss) + ' · ' + historical.candidate + ' · ' + historical.candidate_adoption)
  const labels = new Map(latest.labels.map(row => [row.symbol, row]))
  const count = latest.predictions.filter(row => Number.isFinite(row.calibrated_probability)).length
  element('p', panel, '校准概率覆盖 ' + count + '/30 · 到期复盘 ' + latest.maturity)
  const table = element('table', panel, null, style.table)
  const header = element('tr', element('thead', table))
  for (const label of ['证券','原始','校准','B0','B1','近期 B2','到期上涨']) element('th', header, label, style.cell)
  const body = element('tbody', table)
  for (const p of latest.predictions) {
    const row = element('tr', body)
    element('td', row, p.symbol, style.cell)
    for (const key of ['raw','calibrated','b0','b1','recent']) element('td', row, metric(p[key+'_probability']), style.cell)
    const label = labels.get(p.symbol)
    const cell = element('td', row, label?.y == null ? '—' : label.y ? '上涨' : '未上涨', style.cell)
    if (label?.probability_review) {
      const details = element('details', cell)
      element('summary', details, '各方法损失')
      for (const [method, score] of Object.entries(label.probability_review)) {
        element('p', details, method + ' · log loss ' + metric(score.log_loss) + ' · Brier ' + metric(score.brier))
      }
    }
  }
}

async function showDirection(panel, active) {
  try {
    const response = await fetch('/api/extensions/aql.research/direction', {credentials:'same-origin'})
    if (!response.ok) throw new Error('HTTP ' + response.status)
    const data = await response.json()
    if (!active()) return
    if (data.kind === 'NO_DIRECTION_DATA') {
      element('p', panel, '尚未发布方向研究产物。')
      return
    }
    const {latest, historical, paired} = data
    const selectorLabel = element('label', panel, '预测批次 ')
    const selector = element('select', selectorLabel)
    for (const batch of [...data.archive].reverse()) {
      const option = element('option', selector, batch.date + ' · ' + batch.generated_at + ' · ' + batch.maturity)
      option.value = batch.key
      option.selected = batch.prediction_sha256 === latest.prediction_sha256
    }
    const details = element('div', panel)
    renderBatch(details, latest, historical)
    selector.onchange = async () => {
      const key = selector.value
      details.replaceChildren()
      try {
        const response = await fetch('/api/extensions/aql.research/direction/' + encodeURIComponent(key), {credentials:'same-origin'})
        if (!response.ok) throw new Error('HTTP ' + response.status)
        const view = await response.json()
        if (active() && key === selector.value) renderBatch(details, view, historical)
      } catch (error) {
        if (active() && key === selector.value) element('p', details, '无法读取该批次 · ' + error.message)
      }
    }
    element('h3', panel, '合格前瞻配对结果')
    for (const [key, group] of Object.entries(paired)) {
      element('p', panel, (key === 'including_recent' ? '含近期 B2' : '原四种方法') + ' · ' + group.dates + ' 日 · ' + group.pairs + ' 对')
      if (!group.pairs) {
        element('p', panel, '暂无合格成熟样本。', style.dim)
        continue
      }
      for (const [name, scores] of Object.entries(group.metrics)) {
        element('p', panel, name + ' · log loss ' + metric(scores.log_loss) + ' · Brier ' + metric(scores.brier), style.dim)
      }
    }
  } catch (error) {
    if (active()) element('p', panel, '方向研究读取失败 · ' + error.message)
  }
}
const extension = {
  id: eid,
  apiVersion: 1,
  routes: [{
    id: 'aql-research',
    path: '/aql-research',
    mount: (el, ctx) => {
      const root = element('section', el, null, style.shell)
      element('h2', root, 'A 股 Qlib 选股实验室', 'font-size:24px;font-weight:650')
      let disposed = false
      const direction = element('section', root, null, style.card + ';overflow-x:auto')
      showDirection(direction, () => !disposed)
      const ranking = element('details', root, null, style.card)
      element('summary', ranking, '查看历史排名实验')
      const state = element('p', ranking, '读取研究产物中…', style.dim)
      const content = element('div', ranking)
      async function load() {
        try {
          const res = await fetch('/api/extensions/aql.research/latest', {method:'GET', credentials:'same-origin', headers:{Accept:'application/json'}})
          if (!res.ok) throw new Error('研究接口不可用 HTTP ' + res.status)
          const body = await res.json()
          if (disposed) return
          if (body.status !== 'RETROSPECTIVE_RESEARCH_NOT_PIT_QUALIFIED') {
            state.textContent = '尚无可展示的真实研究结果。需在独立 Qlib 环境执行并发布产物。'
            return
          }
          state.textContent = '历史研究（未满足 PIT、样本外经济与交易资格）'
          element('p', content, '实验：' + String(body.run_id || '未知'), style.dim)
          element('p', content, '预测日期：' + String(body.signal_cutoff || '未知') + ' · 发布：' + String(body.created_at || '未知'), style.dim)
          element('p', content, '研究周期：' + String(body.forecast_horizon_days || '?') + ' 个交易日。IC差值仅作排序诊断：' + String(body.rank_ic_difference ?? '未计算'), style.dim)
          const panel = element('div', content, null, style.card)
          const table = element('table', panel, null, style.table)
          const head = element('thead', table)
          const tr = element('tr', head)
          for (const label of ['证券代码', '模型排序分值', '个股详情']) element('th', tr, label, style.cell)
          const tbody = element('tbody', table)
          for (const p of (Array.isArray(body.predictions) ? body.predictions : []).slice(0,100)) {
            if (!/^\d{6}\.(SH|SZ)$/.test(p.symbol)) continue
            const row = element('tr', tbody)
            element('td', row, p.symbol, style.cell)
            element('td', row, Number(p.score).toFixed(5), style.cell)
            const c = element('td', row, null, style.cell)
            const button = element('button', c, '查看 K 线', 'cursor:pointer;text-decoration:underline;background:transparent;border:0;color:inherit')
            button.onclick = () => {
              if (!ctx.ui?.openStockPreview?.({symbol:p.symbol})) {
                state.textContent = '宿主个股详情接口不可用；请确认 TSP 版本与行情数据已就绪。'
              }
            }
          }
          if (!tbody.children.length) element('p', panel, '该实验没有可展示的候选证券。', style.dim)
        } catch (err) {
          if (!disposed) state.textContent = '研究数据读取失败：' + (err instanceof Error ? err.message : '未知错误')
        }
      }
      load()
      return () => {disposed=true; el.replaceChildren()}
    },
  }],
  navigation: [{ id:'aql-research-nav', routeId:'aql-research', label:'Qlib 研究', icon:'Brain' }],
}
export default extension
