import { useEffect, useMemo, useState } from 'react'
import Brand from '../components/Brand'
import { toast } from '../toast'
import '../App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

type Candidate = {
  token: string
  name: string
  email: string
  role: string
  score: number | null
  status: string
  flags: string
  verdict: string
}

function verdictBadgeClass(verdict: string) {
  if (verdict === 'Pass') return 'badge-completed'
  if (verdict === 'Fail') return 'badge-disqualified'
  if (verdict === 'Pending') return 'badge-in_progress'
  return 'badge-pending'
}

function initials(name: string) {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

function HRDashboard() {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([])

  async function refreshCandidates() {
    const res = await fetch(`${API_BASE}/api/candidates`)
    const data = await res.json()
    setCandidates(data)
  }

  useEffect(() => {
    refreshCandidates()
    const interval = setInterval(refreshCandidates, 5000)
    return () => clearInterval(interval)
  }, [])

  const stats = useMemo(() => {
    const total = candidates.length
    const completed = candidates.filter((c) => c.status === 'completed').length
    const inProgress = candidates.filter((c) => c.status === 'in_progress').length
    const scored = candidates.filter((c) => c.score !== null)
    const avgScore = scored.length
      ? (scored.reduce((sum, c) => sum + (c.score ?? 0), 0) / scored.length).toFixed(1)
      : '-'
    return { total, completed, inProgress, avgScore }
  }, [candidates])

  async function uploadFile(selected: File) {
    setUploading(true)
    const formData = new FormData()
    formData.append('file', selected)

    try {
      const res = await fetch(`${API_BASE}/api/candidates/upload`, { method: 'POST', body: formData })
      if (!res.ok) {
        const err = await res.json()
        toast.error(`Upload failed: ${err.detail || res.status}`)
        return
      }
      const data = await res.json()
      toast.success(
        `Sent ${data.sent.length} of ${data.total} invites` +
          (data.failed.length > 0 ? ` — ${data.failed.length} failed` : ''),
      )
      refreshCandidates()
    } catch (err) {
      toast.error(`Upload request failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setUploading(false)
      setFile(null)
    }
  }

  function handleDownload() {
    window.location.href = `${API_BASE}/api/candidates/export`
  }

  return (
    <div className="app">
      <Brand subtitle="HR Dashboard" />
      <h1>Candidate Interviews</h1>

      <div className="stats-grid">
        <div className="stat-tile">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total Candidates</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.completed}</div>
          <div className="stat-label">Completed</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.inProgress}</div>
          <div className="stat-label">In Progress</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.avgScore}</div>
          <div className="stat-label">Avg Score</div>
        </div>
      </div>

      <div className="panel">
        <label>Upload candidate sheet (Name, Email, Role columns)</label>
        <div
          className={`dropzone ${dragging ? 'dragging' : ''}`}
          onClick={() => document.getElementById('sheet-input')?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            const dropped = e.dataTransfer.files?.[0]
            if (dropped) setFile(dropped)
          }}
        >
          <input
            id="sheet-input"
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <div className="dropzone-icon">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path
                d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 9l5-5 5 5M12 4v12"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="dropzone-text">Drag & drop your Excel file here, or click to browse</div>
          {file && <div className="dropzone-filename">{file.name}</div>}
        </div>
        <button
          onClick={() => file && uploadFile(file)}
          disabled={uploading || !file}
        >
          {uploading ? 'Sending invites...' : 'Proceed'}
        </button>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Results</h2>
          <button className="secondary" onClick={handleDownload}>
            Download Results
          </button>
        </div>

        {candidates.length === 0 ? (
          <p className="empty-state">No candidates yet — upload a sheet above to get started.</p>
        ) : (
          <table className="results-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Role</th>
                <th>Score</th>
                <th>Result</th>
                <th>Status</th>
                <th>Cheating</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.token}>
                  <td data-label="Candidate">
                    <div className="candidate-cell">
                      <div className="avatar">{initials(c.name)}</div>
                      <div>
                        <div>{c.name}</div>
                        <div className="brand-sub">{c.email}</div>
                      </div>
                    </div>
                  </td>
                  <td data-label="Role">{c.role}</td>
                  <td data-label="Score">{c.score ?? '-'}</td>
                  <td data-label="Result">
                    <span className={`badge ${verdictBadgeClass(c.verdict)}`}>{c.verdict}</span>
                  </td>
                  <td data-label="Status">
                    <span className={`badge badge-${c.status}`}>{c.status.replace('_', ' ')}</span>
                  </td>
                  <td data-label="Cheating">
                    <span className={`badge ${c.flags ? 'badge-disqualified' : 'badge-completed'}`}>
                      {c.flags ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td data-label="Reason">{c.flags || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default HRDashboard
