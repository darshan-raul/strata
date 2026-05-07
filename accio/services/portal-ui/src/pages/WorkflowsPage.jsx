import React, { useState, useEffect } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import { getWorkflows, getWorkflowTypes, getWorkflowById, createWorkflow } from '../api.js'

const STATUS_STYLE = {
  pending:   { dot: 'pending',   label: 'Pending',   color: 'var(--accent-amber)' },
  running:   { dot: 'running',   label: 'Running',   color: 'var(--accent-sky)' },
  completed: { dot: 'completed', label: 'Completed', color: 'var(--accent-emerald)' },
  failed:    { dot: 'failed',    label: 'Failed',    color: 'var(--accent-rose)' },
}

function StepProgress({ steps = [], currentStep, totalSteps }) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
      {steps.map((step, i) => {
        const done = step.status === 'completed'
        const active = step.status === 'running'
        const pending = step.status === 'pending'
        return (
          <React.Fragment key={step.id}>
            <div title={step.name} style={{
              width: 28, height: 28, borderRadius: '50%',
              background: done ? 'var(--accent-emerald)' : active ? 'var(--accent-sky)' : 'var(--bg-tertiary)',
              border: active ? '2px solid var(--accent-sky)' : '2px solid transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 700, color: done || active ? 'white' : 'var(--text-muted)',
              animation: active ? 'pulse 1.5s ease-in-out infinite' : 'none',
              flexShrink: 0,
            }}>
              {done ? '✓' : i + 1}
            </div>
            {i < steps.length - 1 && (
              <div style={{ height: 2, width: 16, background: done ? 'var(--accent-emerald)' : 'var(--bg-tertiary)', flexShrink: 0 }} />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

function WorkflowRow({ wf, onSelect, selected }) {
  const s = STATUS_STYLE[wf.status] || STATUS_STYLE.pending
  const pct = wf.total_steps ? Math.round((wf.current_step / wf.total_steps) * 100) : 0
  return (
    <div
      onClick={() => onSelect(wf.id)}
      style={{
        padding: '16px 20px', borderBottom: '1px solid rgba(99,102,241,0.06)',
        cursor: 'pointer', background: selected ? 'rgba(99,102,241,0.05)' : 'transparent',
        transition: 'background 0.15s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div className={`deploy-status-dot ${s.dot}`} style={{ flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{wf.type}</span>
            {wf.entity_id && <span className="deploy-tag" style={{ fontSize: 11 }}>{wf.entity_type}: {wf.entity_id.slice(0,8)}</span>}
          </div>
          {wf.total_steps > 0 && (
            <div>
              <div style={{ height: 4, background: 'var(--bg-tertiary)', borderRadius: 2, overflow: 'hidden', marginBottom: 4 }}>
                <div style={{
                  height: '100%', width: `${pct}%`,
                  background: wf.status === 'completed' ? 'var(--accent-emerald)' : wf.status === 'failed' ? 'var(--accent-rose)' : 'var(--accent-sky)',
                  transition: 'width 0.5s ease',
                }} />
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                Step {wf.current_step}/{wf.total_steps} · {pct}%
              </div>
            </div>
          )}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 13, color: s.color, fontWeight: 600 }}>{s.label}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {new Date(wf.created_at).toLocaleTimeString()}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState([])
  const [types, setTypes]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)
  const [detail, setDetail]       = useState(null)
  const [showForm, setShowForm]   = useState(false)
  const [form, setForm]           = useState({ type: 'service-onboarding', entity_id: '', entity_type: 'service' })
  const [submitting, setSubmitting] = useState(false)

  const load = async () => {
    try {
      const [wfs, ts] = await Promise.all([getWorkflows(), getWorkflowTypes()])
      setWorkflows(wfs || [])
      setTypes(ts || [])
      if (!form.type && ts?.length) setForm(p => ({ ...p, type: ts[0].type }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 3000) // poll for running workflow progress
    return () => clearInterval(t)
  }, [])

  // Auto-refresh selected workflow detail
  useEffect(() => {
    if (!selected) return
    const t = setInterval(async () => {
      const d = await getWorkflowById(selected).catch(() => null)
      if (d) setDetail(d)
    }, 2000)
    getWorkflowById(selected).then(setDetail).catch(() => null)
    return () => clearInterval(t)
  }, [selected])

  const submit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const res = await createWorkflow(form)
      setShowForm(false)
      setSelected(res.id)
      load()
    } catch(err) {
      alert('Error: ' + err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="dashboard-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <h1>Workflow Engine</h1>
          <p>Multi-step platform workflows — onboarding, provisioning, decommission, rollout</p>
        </div>
        <div className="page-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 420px', gap: 20, height: 'calc(100vh - 130px)' }}>
            {/* Left: List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0 }}>
              <div className="page-actions">
                <button className="btn-primary" onClick={() => setShowForm(!showForm)}>▶ Run Workflow</button>
                <span style={{ fontSize: 13, color: 'var(--text-muted)', alignSelf: 'center', marginLeft: 8 }}>
                  {workflows.filter(w => w.status === 'running').length} running
                </span>
              </div>

              {showForm && (
                <div className="panel">
                  <div className="panel-header">
                    <span className="panel-title">Start Workflow</span>
                    <button className="btn-ghost" style={{ padding: '4px 12px', fontSize: 13 }} onClick={() => setShowForm(false)}>✕</button>
                  </div>
                  <form onSubmit={submit} style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
                    <div>
                      <label className="form-label">Workflow Type</label>
                      <select className="form-input" value={form.type} onChange={e => setForm(p => ({...p, type: e.target.value}))}>
                        {types.map(t => <option key={t.type} value={t.type}>{t.type} ({t.step_count} steps)</option>)}
                      </select>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                      <div>
                        <label className="form-label">Entity Type</label>
                        <input className="form-input" value={form.entity_type} onChange={e => setForm(p => ({...p, entity_type: e.target.value}))} placeholder="service" />
                      </div>
                      <div>
                        <label className="form-label">Entity ID (optional)</label>
                        <input className="form-input" value={form.entity_id} onChange={e => setForm(p => ({...p, entity_id: e.target.value}))} placeholder="service UUID or name" />
                      </div>
                    </div>
                    {form.type && types.find(t => t.type === form.type) && (
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Steps: {types.find(t => t.type === form.type)?.steps?.join(' → ')}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn-primary" type="submit" disabled={submitting}>{submitting ? 'Starting...' : '▶ Start'}</button>
                      <button className="btn-ghost" type="button" onClick={() => setShowForm(false)}>Cancel</button>
                    </div>
                  </form>
                </div>
              )}

              <div className="panel" style={{ flex: 1, overflow: 'auto' }}>
                <div className="panel-header">
                  <span className="panel-title">Workflow Runs</span>
                  <span className="panel-badge">{workflows.length}</span>
                </div>
                {loading ? (
                  <div style={{ padding: 32, textAlign: 'center' }}><div className="loading-spinner" style={{ margin: '0 auto' }} /></div>
                ) : workflows.length === 0 ? (
                  <div className="empty-state">No workflows yet — run one above</div>
                ) : (
                  workflows.map(wf => (
                    <WorkflowRow key={wf.id} wf={wf} selected={selected === wf.id} onSelect={id => {
                      setSelected(id === selected ? null : id)
                      setDetail(null)
                    }} />
                  ))
                )}
              </div>
            </div>

            {/* Right: Detail */}
            <div className="panel" style={{ overflow: 'auto' }}>
              <div className="panel-header">
                <span className="panel-title">Step Detail</span>
                {detail && <span className="deploy-tag">{detail.type}</span>}
              </div>
              {!selected ? (
                <div className="empty-state">Select a workflow to see steps</div>
              ) : !detail ? (
                <div style={{ padding: 32, textAlign: 'center' }}><div className="loading-spinner" style={{ margin: '0 auto' }} /></div>
              ) : (
                <div>
                  <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
                    <StepProgress steps={detail.steps || []} currentStep={detail.current_step} totalSteps={detail.total_steps} />
                  </div>
                  {(detail.steps || []).map(step => {
                    const isDone = step.status === 'completed'
                    const isRun  = step.status === 'running'
                    return (
                      <div key={step.id} style={{
                        padding: '12px 20px', borderBottom: '1px solid rgba(99,102,241,0.06)',
                        opacity: step.status === 'pending' ? 0.5 : 1,
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{
                            width: 22, height: 22, borderRadius: '50%',
                            background: isDone ? 'var(--accent-emerald)' : isRun ? 'var(--accent-sky)' : 'var(--bg-tertiary)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 11, fontWeight: 700, color: isDone || isRun ? 'white' : 'var(--text-muted)',
                            flexShrink: 0, animation: isRun ? 'pulse 1.5s infinite' : 'none',
                          }}>
                            {isDone ? '✓' : step.step_number}
                          </div>
                          <span style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>{step.name}</span>
                          <span style={{
                            fontSize: 11, fontWeight: 600,
                            color: isDone ? 'var(--accent-emerald)' : isRun ? 'var(--accent-sky)' : 'var(--text-muted)',
                          }}>
                            {step.status}
                          </span>
                        </div>
                        {step.output && isDone && (
                          <div style={{ marginTop: 4, marginLeft: 32, fontSize: 11, color: 'var(--text-muted)' }}>
                            ✓ {step.output}
                          </div>
                        )}
                        {step.completed_at && (
                          <div style={{ marginTop: 2, marginLeft: 32, fontSize: 10, color: 'var(--text-muted)' }}>
                            {new Date(step.completed_at).toLocaleTimeString()}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
