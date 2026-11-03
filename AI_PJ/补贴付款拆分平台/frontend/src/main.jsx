import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API = '/api'

const navItems = [
  { key: 'workspace', label: '拆分工作台', icon: '▦' },
  { key: 'history', label: '任务记录', icon: '◷' },
  { key: 'rules', label: '付款规则', icon: '⌘' },
]

function money(value = 0) {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(Number(value || 0))
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function App() {
  const [active, setActive] = useState('workspace')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [task, setTask] = useState(null)
  const [history, setHistory] = useState([])
  const [rules, setRules] = useState([])
  const [selectedDept, setSelectedDept] = useState(null)
  const [notice, setNotice] = useState(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef(null)

  useEffect(() => {
    fetch(`${API}/rules`).then((res) => res.json()).then((data) => setRules(data.items || [])).catch(() => {})
    fetch(`${API}/tasks`).then((res) => res.json()).then((data) => setHistory(data.items || [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (!task?.id || ['completed', 'failed'].includes(task.status)) return undefined
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/tasks/${task.id}`)
        if (!response.ok) return
        const next = await response.json()
        setTask(next)
        if (['completed', 'failed'].includes(next.status)) {
          const historyResponse = await fetch(`${API}/tasks`)
          if (historyResponse.ok) setHistory((await historyResponse.json()).items || [])
          if (next.status === 'completed') setNotice({ type: 'success', text: '拆分完成，汇总表与 19 份子表已经准备好。' })
          else setNotice({ type: 'error', text: next.error || '拆分失败，请检查表头和部门归集规则。' })
        }
      } catch {
        // Keep polling if the browser briefly loses the connection.
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [task?.id, task?.status])

  const result = task?.result
  const stats = useMemo(() => {
    if (!result) return []
    return [
      { label: '有效明细', value: result.source_rows, suffix: '人', tone: 'purple' },
      { label: '付款部门', value: result.payment_departments, suffix: '个', tone: 'blue' },
      { label: '餐补合计', value: money(result.payment_total), suffix: '元', tone: 'orange' },
    ]
  }, [result])

  function chooseFile(file) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setNotice({ type: 'error', text: '请上传可编辑、未加密的 .xlsx 总表。' })
      return
    }
    setSelectedFile(file)
    setNotice(null)
  }

  async function submit() {
    if (!selectedFile || task?.status === 'running' || task?.status === 'queued') return
    const body = new FormData()
    body.append('file', selectedFile)
    setTask({ id: 'local', status: 'queued', file_name: selectedFile.name })
    setSelectedDept(null)
    try {
      const response = await fetch(`${API}/tasks`, { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '上传失败')
      setTask(data)
    } catch (error) {
      setTask(null)
      setNotice({ type: 'error', text: error.message || '上传失败，请确认后端服务已启动。' })
    }
  }

  function loadHistory(item) {
    setActive('workspace')
    setSidebarOpen(false)
    setTask(item)
    setSelectedFile(null)
    setSelectedDept(null)
  }

  const isBusy = task?.status === 'queued' || task?.status === 'running'

  return (
    <div className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand-block">
          <div className="brand-mark">FS</div>
          <div>
            <strong>FlowSplit</strong>
            <span>费用归集工作台</span>
          </div>
          <button className="close-mobile" onClick={() => setSidebarOpen(false)}>×</button>
        </div>
        <div className="workspace-chip"><span className="status-dot" /> 月度补贴空间</div>
        <nav>
          {navItems.map((item) => (
            <button key={item.key} className={active === item.key ? 'nav-item active' : 'nav-item'} onClick={() => { setActive(item.key); setSidebarOpen(false) }}>
              <span className="nav-icon">{item.icon}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="note-kicker">当前版本</span>
          <strong>规则引擎 1.0</strong>
          <p>按付款部门自动生成子表，支持后续扩展审批与钉钉连接。</p>
        </div>
        <div className="profile"><div className="avatar">管</div><div><strong>费用管理员</strong><span>本地工作区</span></div><span className="more">•••</span></div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="menu-button" onClick={() => setSidebarOpen(true)}>☰</button>
          <div className="crumb"><span>费用中心</span><b>/</b><strong>{active === 'workspace' ? '拆分工作台' : active === 'history' ? '任务记录' : '付款规则'}</strong></div>
          <div className="top-actions"><span className="online"><i /> 服务正常</span><button className="icon-button" title="帮助">?</button></div>
        </header>

        {active === 'workspace' && <Workspace {...{ selectedFile, chooseFile, submit, fileInput, dragging, setDragging, task, result, stats, selectedDept, setSelectedDept, isBusy, notice, setNotice }} />}
        {active === 'history' && <History items={history} onOpen={loadHistory} />}
        {active === 'rules' && <Rules rules={rules} />}
      </main>
    </div>
  )
}

function Workspace({ selectedFile, chooseFile, submit, fileInput, dragging, setDragging, task, result, stats, selectedDept, setSelectedDept, isBusy, notice, setNotice }) {
  return (
    <section className="content workspace-page">
      <div className="page-heading reveal"><div><p className="eyebrow">MONTHLY ALLOWANCE OPS</p><h1>把总表交给系统，<em>按部门整齐落地。</em></h1><p className="subheading">上传一份月度补贴总表，自动校验、归集并生成 19 份付款明细。</p></div><div className="date-pill"><span>工作模式</span><strong>自动拆分</strong></div></div>
      {notice && <div className={`notice ${notice.type}`}><span>{notice.type === 'success' ? '✓' : '!'}</span>{notice.text}<button onClick={() => setNotice(null)}>×</button></div>}
      <div className="dashboard-grid">
        <div className="primary-column">
          <UploadCard {...{ selectedFile, chooseFile, submit, fileInput, dragging, setDragging, task, isBusy }} />
          {result ? <SummaryCards stats={stats} result={result} /> : <HowItWorks />}
          {result && <DepartmentTable result={result} selectedDept={selectedDept} setSelectedDept={setSelectedDept} task={task} />}
        </div>
        <aside className="side-column">
          <StatusCard task={task} result={result} />
          {result ? <DownloadCard task={task} /> : <RulePreview />}
        </aside>
      </div>
    </section>
  )
}

function UploadCard({ selectedFile, chooseFile, submit, fileInput, dragging, setDragging, task, isBusy }) {
  return <div className={`upload-card ${dragging ? 'dragging' : ''} reveal delay-1`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files?.[0]) }}>
    <div className="card-topline"><span className="step-badge">01</span><div><p className="eyebrow">SOURCE FILE</p><h2>上传月度总表</h2></div><span className="secure">● 仅处理当前任务</span></div>
    <p className="card-copy">支持标准的 .xlsx 文件。系统会忽略原表总计行，并按最新金额口径重新计算合计。</p>
    <input ref={fileInput} type="file" accept=".xlsx" hidden onChange={(event) => chooseFile(event.target.files?.[0])} />
    <button className="drop-zone" onClick={() => fileInput.current?.click()}>
      <span className="upload-symbol">↑</span><span><strong>{selectedFile ? selectedFile.name : '点击选择文件或拖拽到这里'}</strong><small>{selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB · 已准备上传` : '未加密、可编辑的 Excel 总表'}</small></span><span className="choose-text">选择文件 →</span>
    </button>
    <div className="upload-footer"><span className="hint">会生成新汇总表 + 19 份部门子表</span><button className="primary-button" disabled={!selectedFile || isBusy} onClick={submit}>{isBusy ? <><span className="spinner" />正在处理</> : <>开始拆分 <span>↗</span></>}</button></div>
  </div>
}

function HowItWorks() {
  return <div className="how-card reveal delay-2"><div className="section-heading"><div><p className="eyebrow">WORKFLOW</p><h2>三步完成付款准备</h2></div><span className="muted">无需手工复制粘贴</span></div><div className="flow-steps"><div><span>01</span><strong>上传总表</strong><small>读取真实明细</small></div><i>→</i><div><span>02</span><strong>自动归集</strong><small>执行 19 条规则</small></div><i>→</i><div><span>03</span><strong>下载结果</strong><small>一键拿到子表</small></div></div></div>
}

function SummaryCards({ stats, result }) {
  return <div className="stat-grid reveal delay-2">{stats.map((item) => <div className={`stat-card ${item.tone}`} key={item.label}><span>{item.label}</span><strong>{money(item.value)}<small>{item.suffix}</small></strong><div className="sparkline"><i /><i /><i /><i /><i /><i /><i /></div></div>)}<div className="stat-card total"><span>处理月份</span><strong>{result.month}<small>账期</small></strong><div className="complete-badge">✓ 已校验</div></div></div>
}

function StatusCard({ task, result }) {
  const status = task?.status
  const label = status === 'completed' ? '拆分完成' : status === 'failed' ? '需要检查' : status === 'running' ? '正在计算' : status === 'queued' ? '排队中' : '等待上传'
  return <div className="status-card reveal delay-2"><div className="section-heading"><div><p className="eyebrow">RUN STATUS</p><h2>任务状态</h2></div><span className={`status-label ${status || 'idle'}`}>{label}</span></div><div className="progress-track"><div className={`progress-bar ${status === 'failed' ? 'failed' : ''} ${status === 'completed' ? 'done' : ''}`} /></div><div className="status-details"><span><i className={status ? 'filled' : ''} />上传文件 <b>{task?.file_name || '待开始'}</b></span><span><i className={status === 'running' || status === 'completed' ? 'filled' : ''} />读取并校验 <b>{status === 'running' ? '处理中' : result ? '已完成' : '—'}</b></span><span><i className={status === 'completed' ? 'filled' : ''} />生成付款文件 <b>{result ? '19 份' : '—'}</b></span></div></div>
}

function RulePreview() {
  return <div className="rule-preview reveal delay-3"><p className="eyebrow">RULE ENGINE</p><h3>默认付款规则已就绪</h3><div className="rule-line"><span>归集部门</span><strong>19 个</strong></div><div className="rule-line"><span>金额口径</span><strong>三类餐补相加</strong></div><div className="rule-line"><span>总计行</span><strong>自动补充</strong></div><div className="mini-visual"><span /><span /><span /><span /><span /><span /></div></div>
}

function DownloadCard({ task }) {
  return <div className="download-card reveal delay-3"><p className="eyebrow">RESULT CENTER</p><h3>结果文件</h3><p>已生成可直接用于钉钉付款流程的文件。</p><a className="download-main" href={`${API}/tasks/${task.id}/download/zip`}><span className="file-icon">↓</span><span><strong>19 份付款子表</strong><small>ZIP 压缩包 · 点击下载</small></span><b>↗</b></a><a className="download-link" href={`${API}/tasks/${task.id}/download/summary`}>下载带总计行的新汇总表 <span>→</span></a></div>
}

function DepartmentTable({ result, selectedDept, setSelectedDept, task }) {
  return <div className="department-card reveal delay-3"><div className="section-heading"><div><p className="eyebrow">PAYMENT DEPARTMENTS</p><h2>付款部门预览</h2></div><span className="muted">点击行查看归集口径</span></div><div className="table-wrap"><table><thead><tr><th>部门</th><th>人数</th><th>日常餐补</th><th>夜宵</th><th>付款金额</th><th /></tr></thead><tbody>{result.departments.map((item, index) => <React.Fragment key={`${item.file_name}-${index}`}><tr className={selectedDept === index ? 'selected' : ''} onClick={() => setSelectedDept(selectedDept === index ? null : index)}><td><span className="dept-avatar">{item.payment_department.slice(0, 1)}</span><strong>{item.payment_department}</strong><small>{item.company} · {item.scope}</small></td><td>{item.count}</td><td>¥ {money(item.daily)}</td><td>¥ {money(item.night)}</td><td className="amount">¥ {money(item.amount)}</td><td><span className="row-arrow">{selectedDept === index ? '⌃' : '›'}</span></td></tr>{selectedDept === index && <tr className="detail-row"><td colSpan="6"><div><span>出差餐补 <b>¥ {money(item.travel)}</b></span><span>文件 <b>{item.file_name}</b></span><a href={`${API}/tasks/${task.id}/download/department/${index}`}>下载此子表 ↗</a></div></td></tr>}</React.Fragment>)}</tbody></table></div></div>
}

function History({ items, onOpen }) {
  return <section className="content simple-page"><div className="page-heading reveal"><div><p className="eyebrow">TASK ARCHIVE</p><h1>任务记录</h1><p className="subheading">查看最近生成的月份与文件。</p></div></div><div className="history-card reveal delay-1">{items.length ? items.map((item) => <button className="history-row" key={item.id} onClick={() => onOpen(item)}><span className="history-icon">▦</span><span><strong>{item.file_name}</strong><small>{formatDate(item.created_at)}</small></span><em className={item.status}>{item.status === 'completed' ? '已完成' : item.status === 'failed' ? '失败' : '处理中'}</em><span>→</span></button>) : <div className="empty-state">还没有生成记录，先去上传一份总表吧。</div>}</div></section>
}

function Rules({ rules }) {
  return <section className="content simple-page"><div className="page-heading reveal"><div><p className="eyebrow">RULE LIBRARY</p><h1>付款规则</h1><p className="subheading">这些规则决定一条明细会进入哪一个付款子表。</p></div><div className="date-pill"><span>当前规则</span><strong>{rules.length || 19} 条</strong></div></div><div className="rules-grid">{rules.map((rule, index) => <div className="rule-card reveal" style={{ animationDelay: `${index * 35}ms` }} key={`${rule.filename_stem}-${index}`}><span className="rule-number">{String(index + 1).padStart(2, '0')}</span><h3>{rule.payment_department}</h3><p>{rule.company} · {rule.scope}</p><small>{rule.filename_stem}.xlsx</small></div>)}</div></section>
}

createRoot(document.getElementById('root')).render(<App />)
