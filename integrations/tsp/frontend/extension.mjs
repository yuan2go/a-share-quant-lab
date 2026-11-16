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
const extension = {
  id: eid,
  apiVersion: 1,
  routes: [{
    id: 'aql-research',
    path: '/aql-research',
    mount: (el, ctx) => {
      const root = element('section', el, null, style.shell)
      element('h2', root, 'A 股 Qlib 选股实验室', 'font-size:24px;font-weight:650')
      element('p', root, '仅展示历史实验结果；不代表当日买卖建议、胜率或实际盈利。', style.dim)
      const state = element('p', root, '读取研究产物中…', style.dim)
      const content = element('div', root)
      let disposed = false
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
