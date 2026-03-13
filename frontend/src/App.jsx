import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import SchemaEditor from './pages/SchemaEditor'
import ResumeUpload from './pages/ResumeUpload'
import ExtractedData from './pages/ExtractedData'

const NAV_ITEMS = [
  { path: '/',         label: 'Schema',    icon: '⬡', desc: 'Extraction template' },
  { path: '/upload',   label: 'Resumes',   icon: '↑',  desc: 'Upload & manage' },
  { path: '/data',     label: 'Insights',  icon: '⊞',  desc: 'Data & chatbot' },
]

function Layout() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Header />
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Routes>
          <Route path="/"       element={<SchemaEditor />} />
          <Route path="/upload" element={<ResumeUpload />} />
          <Route path="/data"   element={<ExtractedData />} />
        </Routes>
      </div>
    </div>
  )
}

function Header() {
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      gap: '40px',
      padding: '0 28px',
      height: '60px',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
      position: 'relative',
      zIndex: 10,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 160 }}>
        <span style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'var(--accent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, fontWeight: 700, color: '#000'
        }}>R</span>
        <span style={{ fontFamily: 'var(--sans)', fontWeight: 700, fontSize: 16, letterSpacing: '-0.02em' }}>
          Resume<span style={{ color: 'var(--accent)' }}>IQ</span>
        </span>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', gap: '4px' }}>
        {NAV_ITEMS.map(item => (
          <NavLink key={item.path} to={item.path} end={item.path === '/'}>
            {({ isActive }) => (
              <div style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '6px 14px', borderRadius: 'var(--radius)',
                background: isActive ? 'var(--accent-dim)' : 'transparent',
                border: `1px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
                color: isActive ? 'var(--accent)' : 'var(--text2)',
                fontSize: 13, fontWeight: 500,
                transition: 'all 0.15s ease',
              }}>
                <span style={{ fontSize: 14 }}>{item.icon}</span>
                <span style={{ fontFamily: 'var(--sans)' }}>{item.label}</span>
              </div>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Status dot */}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text3)', fontSize: 12 }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block', boxShadow: '0 0 6px var(--accent)' }}/>
        API Connected
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}
