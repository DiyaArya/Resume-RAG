import { useState, useEffect, useRef } from 'react'

const API = '/api'

// Flatten nested objects/arrays into a display string
function flatten(val) {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'string') return val
  if (typeof val === 'number' || typeof val === 'boolean') return String(val)
  if (Array.isArray(val)) {
    return val.map(item => {
      if (typeof item === 'object' && item !== null) {
        return Object.values(item).filter(Boolean).join(' · ')
      }
      return String(item)
    }).join('\n')
  }
  if (typeof val === 'object') {
    return Object.entries(val).map(([k, v]) => `${k}: ${flatten(v)}`).join(' | ')
  }
  return String(val)
}

export default function ExtractedData() {
  const [rows, setRows] = useState([])
  const [columns, setColumns] = useState([])
  const [loading, setLoading] = useState(true)
  const [chatOpen, setChatOpen] = useState(true)
  const [filterResume, setFilterResume] = useState(null) // null = all
  const [resumes, setResumes] = useState([])

  useEffect(() => {
    Promise.all([
      fetch(`${API}/extracted`).then(r => r.json()),
      fetch(`${API}/resumes`).then(r => r.json()),
    ]).then(([extracted, resList]) => {
      setResumes(resList)
      processData(extracted)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  // Poll for new data every 10 seconds
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const data = await fetch(`${API}/extracted`).then(r => r.json())
        processData(data)
      } catch { }
    }, 10000)
    return () => clearInterval(id)
  }, [])

  function processData(extracted) {
    if (!extracted?.length) { setRows([]); setColumns([]); return }
    // Gather all unique keys across all entries
    const keySet = new Set()
    extracted.forEach(e => Object.keys(e.data || {}).forEach(k => keySet.add(k)))
    setColumns(['original_filename', 'uploaded_at', ...Array.from(keySet)])
    setRows(extracted)
  }

  const displayCols = columns.filter(c => c !== 'id' && c !== 'filename')
  const filteredRows = filterResume
    ? rows.filter(r => r.id === filterResume)
    : rows

  const colLabel = (c) => c.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Main table area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header bar */}
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 12,
          background: 'var(--surface)', flexShrink: 0,
        }}>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontFamily: 'var(--sans)', fontSize: 18, fontWeight: 700, letterSpacing: '-0.03em' }}>
              Candidate Insights
            </h1>
            <p style={{ color: 'var(--text3)', fontSize: 12 }}>
              {rows.length} candidate{rows.length !== 1 ? 's' : ''} · {displayCols.length} columns · Auto-updates on upload
            </p>
          </div>

          {/* Filter by resume */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text3)' }}>Filter:</span>
            <select
              value={filterResume || ''}
              onChange={e => setFilterResume(e.target.value || null)}
              style={{
                padding: '5px 10px', fontSize: 12,
                background: 'var(--surface2)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: 6,
              }}
            >
              <option value="">All candidates</option>
              {resumes.map(r => (
                <option key={r.id} value={r.id}>{r.original_filename}</option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setChatOpen(o => !o)}
            style={{
              padding: '6px 14px', fontSize: 12, fontFamily: 'var(--sans)',
              background: chatOpen ? 'var(--accent-dim)' : 'var(--surface2)',
              color: chatOpen ? 'var(--accent)' : 'var(--text2)',
              border: `1px solid ${chatOpen ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 6, fontWeight: 500,
            }}
          >
            {chatOpen ? 'Hide Chat' : 'Show Chat'}
          </button>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text3)' }}>
              Loading data…
            </div>
          ) : rows.length === 0 ? (
            <EmptyState />
          ) : (
            <table style={{
              width: '100%', borderCollapse: 'collapse',
              fontFamily: 'var(--body)', fontSize: 12,
            }}>
              <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
                <tr>
                  <th style={thStyle}>#</th>
                  {displayCols.map(col => (
                    <th key={col} style={thStyle}>{colLabel(col)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, i) => (
                  <tr key={row.id} style={{
                    borderBottom: '1px solid var(--border)',
                    background: i % 2 === 0 ? 'var(--surface)' : 'var(--bg)',
                  }}>
                    <td style={{ ...tdStyle, color: 'var(--text3)', fontFamily: 'var(--mono)', width: 40 }}>
                      {i + 1}
                    </td>
                    {displayCols.map(col => {
                      const val = col === 'original_filename'
                        ? row.original_filename
                        : col === 'uploaded_at'
                          ? formatDate(row.uploaded_at)
                          : flatten(row.data?.[col])
                      const isMultiline = val?.includes?.('\n')
                      return (
                        <td key={col} style={{
                          ...tdStyle,
                          ...(col === 'original_filename' ? {
                            fontWeight: 500, color: 'var(--accent)',
                            whiteSpace: 'nowrap', minWidth: 180,
                          } : {}),
                          ...(col === 'uploaded_at' ? {
                            color: 'var(--text3)', fontFamily: 'var(--mono)',
                            whiteSpace: 'nowrap', fontSize: 11,
                          } : {}),
                        }}>
                          {isMultiline
                            ? <MultilineCell text={val} />
                            : <span title={val}>{truncate(val, 80)}</span>
                          }
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Chat panel */}
      {chatOpen && (
        <ChatPanel resumes={resumes} filterResume={filterResume} />
      )}
    </div>
  )
}

function MultilineCell({ text }) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  return (
    <div>
      {expanded ? (
        <div>
          {lines.map((l, i) => (
            <div key={i} style={{ marginBottom: 3, lineHeight: 1.5 }}>{l}</div>
          ))}
          <button onClick={() => setExpanded(false)} style={expandBtn}>▲ less</button>
        </div>
      ) : (
        <div>
          <div title={text}>{truncate(lines[0], 70)}</div>
          {lines.length > 1 && (
            <button onClick={() => setExpanded(true)} style={expandBtn}>
              +{lines.length - 1} more
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function ChatPanel({ resumes, filterResume }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Hello! Ask me anything — about uploaded candidates OR general questions like current news, prices, tech topics, and more. I search the web in real time for non-resume questions.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('chat_session_id'))
  const [historyList, setHistoryList] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const bottomRef = useRef()

  // Fetch session history and initial message context on mount
  useEffect(() => {
    fetch(`${API}/chat/history`)
      .then(r => r.json())
      .then(data => setHistoryList(data || []))
      .catch(e => console.error("Failed to fetch chat history:", e))

    // If we have a persisted sessionId, load its messages
    const persistedSid = localStorage.getItem('chat_session_id')
    if (persistedSid) {
      loadSession(persistedSid)
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: msg }])
    setLoading(true)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 90000) // 90s timeout

    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          resume_id: filterResume || null,
          session_id: sessionId,
        }),
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
      const data = await res.json()
      if (data.session_id) {
        setSessionId(data.session_id)
        localStorage.setItem('chat_session_id', data.session_id)
      }
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: data.answer || data.response || 'No response.',
          isMarkdown: true,
          citations: Array.isArray(data.citations) ? data.citations : [],
        },
      ])

      // Update history list in background
      fetch(`${API}/chat/history`)
        .then(r => r.json())
        .then(hdata => setHistoryList(hdata || []))
        .catch(() => { })
    } catch (e) {
      clearTimeout(timeoutId)
      const errMsg = e.name === 'AbortError'
        ? '✗ Request timed out (>90s). The server may be busy — please try again.'
        : '✗ Error contacting backend. Make sure the server is running.'
      setMessages(prev => [...prev, { role: 'assistant', text: errMsg }])
    } finally {
      setLoading(false)
    }
  }

  const SUGGESTIONS = [
    'Who has the most experience?',
    'List all Python developers',
    'Compare the candidates',
    'Who studied computer science?',
  ]

  async function loadSession(sid) {
    if (loading) return
    setLoading(true)
    try {
      const res = await fetch(`${API}/chat/history/${sid}`)
      const data = await res.json()
      if (data && data.messages) {
        setMessages(data.messages)
        setSessionId(sid)
        localStorage.setItem('chat_session_id', sid)
        setShowHistory(false)
      }
    } catch (e) {
      console.error("Failed to load session:", e)
    } finally {
      setLoading(false)
    }
  }

  function startNewChat() {
    setSessionId(null)
    localStorage.removeItem('chat_session_id')
    setMessages([{ role: 'assistant', text: 'Hello! Ask me anything — about uploaded candidates OR general questions like current news, prices, tech topics, and more. I search the web in real time for non-resume questions.' }])
    setShowHistory(false)
  }

  return (
    <div style={{
      width: 380, borderLeft: '1px solid var(--border)',
      display: 'flex', flexDirection: 'column',
      background: 'var(--surface)', flexShrink: 0,
      height: '100%',
    }}>
      {/* Chat header */}
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 10,
        flexShrink: 0,
        position: 'relative'
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'var(--accent-dim)', border: '1px solid var(--accent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14,
        }}>⊛</div>
        <div style={{ flex: 1 }}>
          <p style={{ fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 13 }}>Resume Assistant</p>
          <p style={{ color: 'var(--text3)', fontSize: 11 }}>
            {filterResume
              ? `Filtered: ${resumes.find(r => r.id === filterResume)?.original_filename || 'one candidate'}`
              : `All ${resumes.length} candidate${resumes.length !== 1 ? 's' : ''}`}
          </p>
        </div>

        <button
          onClick={() => setShowHistory(!showHistory)}
          style={{
            background: 'transparent', border: '1px solid var(--border)',
            borderRadius: '6px', padding: '4px 8px', fontSize: '11px',
            color: 'var(--text2)', cursor: 'pointer'
          }}>
          History ▼
        </button>

        {/* History Dropdown — inside header so position:absolute is anchored correctly */}
        {showHistory && (
          <div style={{
            position: 'absolute', top: 52, right: 10, width: 240, maxHeight: 300,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
            zIndex: 200, overflow: 'auto', display: 'flex', flexDirection: 'column'
          }}>
            <button
              onClick={startNewChat}
              style={{
                padding: '10px 14px', textAlign: 'left', background: 'var(--accent)',
                border: 'none', borderBottom: '1px solid var(--border)', color: '#000',
                fontWeight: 600, fontSize: 12, cursor: 'pointer', width: '100%'
              }}
            >
              + New Chat
            </button>

            {historyList.length === 0 ? (
              <div style={{ padding: '14px', fontSize: 12, color: 'var(--text3)', textAlign: 'center' }}>
                No past sessions
              </div>
            ) : (
              historyList.map(h => (
                <button
                  key={h.session_id}
                  onClick={() => loadSession(h.session_id)}
                  style={{
                    padding: '10px 14px', textAlign: 'left',
                    background: h.session_id === sessionId ? 'var(--surface2)' : 'transparent',
                    border: 'none', borderBottom: '1px solid var(--border)',
                    color: 'var(--text)', fontSize: 12, cursor: 'pointer',
                    display: 'flex', flexDirection: 'column', gap: 4, width: '100%'
                  }}
                >
                  <span style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {h.title}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--text3)' }}>
                    {formatDate(h.created_at)}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            display: 'flex',
            justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{ maxWidth: '88%' }}>
              <div style={{
                padding: '10px 13px',
                borderRadius: m.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                background: m.role === 'user' ? 'var(--accent)' : 'var(--surface2)',
                color: m.role === 'user' ? '#000' : 'var(--text)',
                fontSize: 13, lineHeight: 1.55,
                border: m.role === 'user' ? 'none' : '1px solid var(--border)',
                whiteSpace: 'pre-wrap',
              }}>
                {m.isMarkdown ? <MarkdownText text={m.text} /> : m.text}
              </div>
              {m.role === 'assistant' && Array.isArray(m.citations) && m.citations.length > 0 && (
                <CitationBlock citations={m.citations} />
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div style={{
              padding: '10px 14px',
              background: 'var(--surface2)', border: '1px solid var(--border)',
              borderRadius: '14px 14px 14px 4px',
            }}>
              <TypingDots />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {
        messages.length === 1 && (
          <div style={{ padding: '0 12px 10px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => setInput(s)} style={{
                padding: '5px 10px', fontSize: 11,
                background: 'var(--surface2)', border: '1px solid var(--border)',
                borderRadius: 20, color: 'var(--text2)', cursor: 'pointer',
              }}>{s}</button>
            ))}
          </div>
        )
      }

      {/* Input */}
      <div style={{
        padding: '12px',
        borderTop: '1px solid var(--border)',
        display: 'flex', gap: 8, flexShrink: 0,
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Ask about candidates…"
          style={{
            flex: 1,
            padding: '9px 12px',
            background: 'var(--surface2)',
            border: '1px solid var(--border)',
            borderRadius: 8, color: 'var(--text)',
            fontSize: 13,
          }}
        />
        <button
          onClick={send}
          disabled={!input.trim() || loading}
          style={{
            padding: '9px 14px',
            background: input.trim() && !loading ? 'var(--accent)' : 'var(--surface2)',
            color: input.trim() && !loading ? '#000' : 'var(--text3)',
            border: 'none', borderRadius: 8,
            fontSize: 14, fontWeight: 600,
            cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
          }}
        >↑</button>
      </div>
    </div >
  )
}

// Renders markdown links [text](url) and **bold** as HTML
function MarkdownText({ text }) {
  // Split on newlines, render each line with inline link/bold support
  const lines = text.split('\n')
  return (
    <span>
      {lines.map((line, li) => {
        // Replace **bold** and [text](url)
        const parts = []
        const regex = /\*\*(.*?)\*\*|\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g
        let last = 0, match
        while ((match = regex.exec(line)) !== null) {
          if (match.index > last) parts.push(line.slice(last, match.index))
          if (match[1] !== undefined) {
            parts.push(<strong key={match.index}>{match[1]}</strong>)
          } else {
            parts.push(
              <a key={match.index} href={match[3]} target="_blank" rel="noopener noreferrer"
                style={{ color: 'var(--accent)', textDecoration: 'underline' }}>
                {match[2]}
              </a>
            )
          }
          last = match.index + match[0].length
        }
        if (last < line.length) parts.push(line.slice(last))
        return (
          <span key={li}>
            {parts.length ? parts : line}
            {li < lines.length - 1 && '\n'}
          </span>
        )
      })}
    </span>
  )
}

function CitationBlock({ citations }) {
  return (
    <div style={{
      marginTop: 8,
      padding: '8px 10px',
      border: '1px solid var(--border)',
      borderRadius: 8,
      background: 'var(--surface)',
      fontSize: 11,
    }}>
      <div style={{ color: 'var(--text3)', marginBottom: 6, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
        Citations
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {citations.map((c, idx) => (
          <details key={`${c.chunk_id || c.url || idx}-${idx}`} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px', background: 'var(--surface2)' }}>
            <summary style={{ cursor: 'pointer', color: 'var(--text2)' }}>
              [{c.citation ?? idx + 1}] {c.source || c.url || 'Source'}
              {c.chunk_id ? ` • chunk_id: ${c.chunk_id}` : ''}
              {typeof c.chunk_index === 'number' ? ` • chunk_index: ${c.chunk_index}` : ''}
            </summary>
            <div style={{ marginTop: 6, color: 'var(--text)', whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>
              {truncate((c.text || '').trim(), 420) || 'No snippet available.'}
            </div>
            {c.url && (
              <a
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: 'inline-block', marginTop: 6, color: 'var(--accent)', textDecoration: 'underline' }}
              >
                Open source
              </a>
            )}
          </details>
        ))}
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ padding: 60, textAlign: 'center' }}>
      <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
      <p style={{ fontFamily: 'var(--sans)', fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
        No data yet
      </p>
      <p style={{ color: 'var(--text3)', fontSize: 13 }}>
        Upload resumes in the Resumes tab to see extracted data here.
      </p>
    </div>
  )
}

function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', height: 16 }}>
      <style>{`
        @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }
      `}</style>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: '50%',
          background: 'var(--text3)',
          animation: `bounce 1.2s ${i * 0.2}s infinite`,
          display: 'inline-block',
        }} />
      ))}
    </div>
  )
}

// Styles
const thStyle = {
  padding: '10px 14px',
  textAlign: 'left',
  background: 'var(--surface)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text3)',
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
  fontFamily: 'var(--sans)',
  position: 'sticky', top: 0,
}

const tdStyle = {
  padding: '10px 14px',
  verticalAlign: 'top',
  color: 'var(--text)',
  maxWidth: 220,
  lineHeight: 1.5,
}

const expandBtn = {
  background: 'none', border: 'none', cursor: 'pointer',
  color: 'var(--accent)', fontSize: 10, fontFamily: 'var(--mono)',
  padding: '2px 0', marginTop: 3,
}

function truncate(str, n) {
  if (!str || str.length <= n) return str
  return str.substring(0, n) + '…'
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}
