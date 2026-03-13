import { useState, useEffect } from 'react'

const API = '/api'

const HELP_TEXT = `{
  "field_name": "Description of what to extract",
  "another_field": "Another description",
  ...
}

Keys become column headers in the Insights view.
Values tell Claude what data to extract from each resume.
Changes apply to all future uploads.`

export default function SchemaEditor() {
  const [schema, setSchema] = useState(null)
  const [raw, setRaw]       = useState('')
  const [status, setStatus] = useState({ type: '', msg: '' })
  const [saving, setSaving] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => { fetchSchema() }, [])

  async function fetchSchema() {
    try {
      const res = await fetch(`${API}/schema`)
      const data = await res.json()
      setSchema(data)
      setRaw(JSON.stringify(data, null, 2))
    } catch (e) {
      setStatus({ type: 'error', msg: 'Failed to load schema from backend.' })
    }
  }

  function handleChange(e) {
    setRaw(e.target.value)
    setHasChanges(true)
    setStatus({ type: '', msg: '' })
  }

  async function handleSave() {
    let parsed
    try {
      parsed = JSON.parse(raw)
    } catch {
      setStatus({ type: 'error', msg: '✗ Invalid JSON — check syntax and try again.' })
      return
    }
    if (typeof parsed !== 'object' || Array.isArray(parsed)) {
      setStatus({ type: 'error', msg: '✗ Schema must be a JSON object (not an array).' })
      return
    }

    setSaving(true)
    try {
      const res = await fetch(`${API}/schema`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema: parsed }),
      })
      const data = await res.json()
      if (data.success) {
        setSchema(parsed)
        setHasChanges(false)
        setStatus({ type: 'success', msg: '✓ Schema saved — next uploads will use this template.' })
      }
    } catch (e) {
      setStatus({ type: 'error', msg: '✗ Failed to save. Is the backend running?' })
    } finally {
      setSaving(false)
    }
  }

  function handleReset() {
    if (!schema) return
    setRaw(JSON.stringify(schema, null, 2))
    setHasChanges(false)
    setStatus({ type: '', msg: '' })
  }

  function handleFormat() {
    try {
      const pretty = JSON.stringify(JSON.parse(raw), null, 2)
      setRaw(pretty)
      setStatus({ type: 'success', msg: '✓ JSON formatted.' })
    } catch {
      setStatus({ type: 'error', msg: '✗ Cannot format — fix JSON errors first.' })
    }
  }

  const fieldCount = schema ? Object.keys(schema).length : 0

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Main editor panel */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '28px', overflow: 'auto' }}>
        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 6 }}>
            <h1 style={{ fontFamily: 'var(--sans)', fontSize: 22, fontWeight: 700, letterSpacing: '-0.03em' }}>
              Extraction Schema
            </h1>
            {fieldCount > 0 && (
              <span style={{
                fontFamily: 'var(--mono)', fontSize: 11,
                background: 'var(--accent-dim)', color: 'var(--accent)',
                border: '1px solid var(--accent)', borderRadius: 4,
                padding: '2px 7px',
              }}>{fieldCount} fields</span>
            )}
          </div>
          <p style={{ color: 'var(--text2)', fontSize: 13 }}>
            Define what data to extract from uploaded resumes. Each key becomes a column in the Insights view.
          </p>
        </div>

        {/* Editor container */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          background: 'var(--surface)',
          border: `1px solid ${hasChanges ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          transition: 'border-color 0.2s',
          minHeight: 300,
        }}>
          {/* Editor toolbar */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 16px',
            background: 'var(--surface2)',
            borderBottom: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', gap: '6px' }}>
              {['#ff5f57','#febc2e','#28c840'].map(c => (
                <div key={c} style={{ width: 11, height: 11, borderRadius: '50%', background: c }} />
              ))}
            </div>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text3)' }}>
              schema.json
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <ToolBtn onClick={handleFormat} label="Format" />
              <ToolBtn onClick={handleReset} label="Reset" disabled={!hasChanges} />
            </div>
          </div>

          {/* Textarea */}
          <textarea
            value={raw}
            onChange={handleChange}
            spellCheck={false}
            style={{
              flex: 1,
              padding: '18px 20px',
              background: 'transparent',
              color: 'var(--text)',
              fontFamily: 'var(--mono)',
              fontSize: 13,
              lineHeight: 1.8,
              border: 'none',
              resize: 'none',
              minHeight: 300,
            }}
            placeholder={`{\n  "name": "Full name of the candidate",\n  "email": "Email address"\n}`}
          />
        </div>

        {/* Status + Save */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges}
            style={{
              padding: '9px 22px',
              background: hasChanges ? 'var(--accent)' : 'var(--surface2)',
              color: hasChanges ? '#000' : 'var(--text3)',
              border: 'none', borderRadius: 'var(--radius)',
              fontWeight: 600, fontSize: 13,
              fontFamily: 'var(--sans)',
              cursor: hasChanges ? 'pointer' : 'not-allowed',
              transition: 'all 0.2s',
            }}
          >
            {saving ? 'Saving…' : 'Save Schema'}
          </button>

          {status.msg && (
            <span style={{
              fontSize: 13,
              color: status.type === 'error' ? 'var(--warn)' : 'var(--accent)',
              fontFamily: 'var(--mono)',
            }}>
              {status.msg}
            </span>
          )}
        </div>
      </div>

      {/* Sidebar: live preview + help */}
      <aside style={{
        width: 280,
        borderLeft: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        flexShrink: 0,
      }}>
        {/* Field preview */}
        <div style={{ padding: '20px', borderBottom: '1px solid var(--border)', flex: 1, overflow: 'auto' }}>
          <p style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 14 }}>
            Columns Preview
          </p>
          {schema && Object.keys(schema).length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {Object.keys(schema).map((key, i) => (
                <div key={key} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 10px',
                  background: 'var(--surface2)',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                }}>
                  <span style={{
                    fontFamily: 'var(--mono)', fontSize: 10,
                    color: 'var(--accent)', opacity: 0.6,
                    minWidth: 18, paddingTop: 1,
                  }}>{String(i+1).padStart(2,'0')}</span>
                  <div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>
                      {key}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2, lineHeight: 1.4 }}>
                      {String(schema[key]).substring(0, 60)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: 'var(--text3)', fontSize: 12 }}>No fields defined yet.</p>
          )}
        </div>

        {/* How-to */}
        <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border)', background: 'var(--surface)' }}>
          <p style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 10 }}>
            Format
          </p>
          <pre style={{
            fontFamily: 'var(--mono)', fontSize: 11,
            color: 'var(--text3)', lineHeight: 1.7,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>{HELP_TEXT}</pre>
        </div>
      </aside>
    </div>
  )
}

function ToolBtn({ onClick, label, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: '3px 10px',
      background: 'transparent',
      color: disabled ? 'var(--text3)' : 'var(--text2)',
      border: '1px solid var(--border)',
      borderRadius: 4, fontSize: 11,
      cursor: disabled ? 'not-allowed' : 'pointer',
    }}>
      {label}
    </button>
  )
}
