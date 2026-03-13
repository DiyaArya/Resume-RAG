import { useState, useEffect, useRef } from 'react'

const API = '/api'

export default function ResumeUpload() {
  const [resumes, setResumes]     = useState([])
  const [dragging, setDragging]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress]   = useState('')
  const [error, setError]         = useState('')
  const [selected, setSelected]   = useState(null)
  const fileInputRef = useRef()

  useEffect(() => { fetchResumes() }, [])

  async function fetchResumes() {
    try {
      const res = await fetch(`${API}/resumes`)
      setResumes(await res.json())
    } catch {
      setError('Could not load resume list.')
    }
  }

  async function uploadFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.')
      return
    }
    setUploading(true)
    setError('')
    setProgress(`Uploading "${file.name}"…`)

    const form = new FormData()
    form.append('file', file)

    try {
      setProgress('Extracting text and running AI analysis…')
      const res = await fetch(`${API}/upload`, { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setProgress(`✓ "${file.name}" processed successfully!`)
      await fetchResumes()
      setTimeout(() => setProgress(''), 3000)
    } catch (e) {
      setError(`✗ ${e.message}`)
      setProgress('')
    } finally {
      setUploading(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  function handleFileInput(e) {
    const file = e.target.files[0]
    if (file) uploadFile(file)
    e.target.value = ''
  }

  async function handleDelete(id, name, e) {
    e.stopPropagation()
    if (!confirm(`Delete "${name}"? This also removes it from the AI index.`)) return
    try {
      await fetch(`${API}/resume/${id}`, { method: 'DELETE' })
      if (selected === id) setSelected(null)
      await fetchResumes()
    } catch {
      setError('Failed to delete resume.')
    }
  }

  function formatDate(iso) {
    if (!iso) return '—'
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  }

  function initials(name) {
    return name.replace(/\.pdf$/i, '').split(/[\s_-]/).slice(0,2).map(w => w[0]?.toUpperCase() || '').join('')
  }

  const AVATAR_COLORS = ['#00e5a0','#5b8fff','#ff6b35','#c084fc','#fbbf24']

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left column: upload + list */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '28px', gap: '20px', overflow: 'auto' }}>
        {/* Header */}
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6 }}>
            <h1 style={{ fontFamily: 'var(--sans)', fontSize: 22, fontWeight: 700, letterSpacing: '-0.03em' }}>
              Resume Library
            </h1>
            {resumes.length > 0 && (
              <span style={{
                fontFamily: 'var(--mono)', fontSize: 11,
                background: 'var(--accent-dim)', color: 'var(--accent)',
                border: '1px solid var(--accent)', borderRadius: 4,
                padding: '2px 7px',
              }}>{resumes.length} files</span>
            )}
          </div>
          <p style={{ color: 'var(--text2)', fontSize: 13 }}>
            Upload PDF resumes. Each upload is stored persistently and indexed for AI search.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${dragging ? 'var(--accent)' : uploading ? 'var(--border2)' : 'var(--border)'}`,
            borderRadius: 'var(--radius-lg)',
            padding: '36px 24px',
            textAlign: 'center',
            cursor: uploading ? 'wait' : 'pointer',
            background: dragging ? 'var(--accent-dim)' : 'var(--surface)',
            transition: 'all 0.2s',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleFileInput} style={{ display: 'none' }} />

          {uploading ? (
            <div>
              <div style={{ marginBottom: 12 }}>
                <Spinner />
              </div>
              <p style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--accent)' }}>{progress}</p>
              <p style={{ color: 'var(--text3)', fontSize: 12, marginTop: 6 }}>
                Claude is extracting structured data…
              </p>
            </div>
          ) : (
            <div>
              <div style={{
                width: 52, height: 52, borderRadius: '50%',
                background: 'var(--surface2)',
                border: `1px solid ${dragging ? 'var(--accent)' : 'var(--border)'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 14px', fontSize: 22,
                transition: 'all 0.2s',
              }}>
                {dragging ? '↓' : '↑'}
              </div>
              <p style={{ fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
                {dragging ? 'Drop to upload' : 'Drop PDF or click to browse'}
              </p>
              <p style={{ color: 'var(--text3)', fontSize: 12 }}>PDF files only · No size limit</p>
              {progress && !uploading && (
                <p style={{ marginTop: 10, fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--accent)' }}>{progress}</p>
              )}
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            padding: '10px 14px', borderRadius: 'var(--radius)',
            background: 'rgba(255,107,53,0.1)', border: '1px solid var(--warn)',
            color: 'var(--warn)', fontFamily: 'var(--mono)', fontSize: 12,
          }}>
            {error}
          </div>
        )}

        {/* Resume list */}
        {resumes.length === 0 ? (
          <div style={{
            padding: '40px', textAlign: 'center',
            background: 'var(--surface)', borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
          }}>
            <p style={{ fontSize: 28, marginBottom: 10 }}>📄</p>
            <p style={{ color: 'var(--text2)', fontSize: 14 }}>No resumes uploaded yet.</p>
            <p style={{ color: 'var(--text3)', fontSize: 12, marginTop: 4 }}>Upload a PDF to get started.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <p style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text3)' }}>
              Uploaded Resumes
            </p>
            {resumes.map((r, i) => {
              const color = AVATAR_COLORS[i % AVATAR_COLORS.length]
              const isSelected = selected === r.id
              return (
                <div
                  key={r.id}
                  onClick={() => setSelected(isSelected ? null : r.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 14px',
                    background: isSelected ? 'var(--surface2)' : 'var(--surface)',
                    border: `1px solid ${isSelected ? 'var(--border2)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius)',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                >
                  {/* Avatar */}
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: `${color}22`, border: `1px solid ${color}55`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: 'var(--sans)', fontWeight: 700, fontSize: 13,
                    color, flexShrink: 0,
                  }}>
                    {initials(r.original_filename)}
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.original_filename}
                    </p>
                    <p style={{ color: 'var(--text3)', fontSize: 11, fontFamily: 'var(--mono)', marginTop: 2 }}>
                      {formatDate(r.uploaded_at)}
                    </p>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <a
                      href={`${API}/resume/${r.id}/file`} target="_blank" rel="noreferrer"
                      onClick={e => e.stopPropagation()}
                      style={{
                        padding: '4px 10px', fontSize: 11,
                        background: 'var(--surface2)', border: '1px solid var(--border)',
                        borderRadius: 5, color: 'var(--text2)',
                      }}
                    >
                      View
                    </a>
                    <button
                      onClick={(e) => handleDelete(r.id, r.original_filename, e)}
                      style={{
                        padding: '4px 10px', fontSize: 11,
                        background: 'transparent', border: '1px solid transparent',
                        borderRadius: 5, color: 'var(--text3)',
                      }}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Right sidebar: stats */}
      <aside style={{
        width: 240, borderLeft: '1px solid var(--border)',
        padding: '24px 20px', display: 'flex', flexDirection: 'column', gap: 20,
        flexShrink: 0, overflow: 'auto',
      }}>
        <div>
          <p style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 14 }}>
            Statistics
          </p>
          <StatCard label="Total Resumes" value={resumes.length} />
          <StatCard label="Indexed for RAG" value={resumes.length} />
          <StatCard label="Schema fields" value="—" subtitle="see Schema tab" />
        </div>

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 20 }}>
          <p style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 12 }}>
            How it works
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              ['1', 'PDF text extracted'],
              ['2', 'Claude parses schema fields'],
              ['3', 'Chunks stored in FAISS'],
              ['4', 'Query in Insights tab'],
            ].map(([n, t]) => (
              <div key={n} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <span style={{
                  width: 20, height: 20, borderRadius: '50%',
                  background: 'var(--accent-dim)', border: '1px solid var(--accent)',
                  color: 'var(--accent)', fontSize: 10, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, marginTop: 1,
                }}>{n}</span>
                <span style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{t}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  )
}

function StatCard({ label, value, subtitle }) {
  return (
    <div style={{
      padding: '12px', marginBottom: 8,
      background: 'var(--surface2)', borderRadius: 8,
      border: '1px solid var(--border)',
    }}>
      <p style={{ color: 'var(--text3)', fontSize: 11 }}>{label}</p>
      <p style={{ fontFamily: 'var(--mono)', fontSize: 20, fontWeight: 500, color: 'var(--accent)', margin: '2px 0' }}>
        {value}
      </p>
      {subtitle && <p style={{ color: 'var(--text3)', fontSize: 10 }}>{subtitle}</p>}
    </div>
  )
}

function Spinner() {
  return (
    <div style={{
      width: 36, height: 36, margin: '0 auto',
      border: '3px solid var(--border)',
      borderTopColor: 'var(--accent)',
      borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
    }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
