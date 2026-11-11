import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDownUp, ArrowUpRight, BriefcaseBusiness, CalendarDays, Check, ChevronDown,
  CircleHelp, Clock3, ExternalLink, Filter, Mail, MapPin, Search, SlidersHorizontal,
  Sparkles, Trash2, X,
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const STATUSES = ['new', 'interested', 'saved', 'applied', 'interview', 'rejected', 'closed'] as const
type Status = typeof STATUSES[number]
type AppDetails = {
  status: Status; application_date?: string | null; resume_version?: string | null
  cover_letter?: string | null; contact_person?: string | null; follow_up_date?: string | null
  interview_notes?: string | null
}
type Match = {
  score: number; explanation: string; reasons: string[]; matched_skills: string[]
  missing_skills: string[]; experience_flags: string[]; score_breakdown: Record<string, number>
}
type Job = {
  id: number; title: string; company: string; location?: string | null; salary_text?: string | null
  employment_type?: string | null; description?: string | null; experience_required?: string | null
  date_posted?: string | null; closing_date?: string | null; date_discovered: string; original_url?: string | null
  source?: { name: string } | null; application?: AppDetails | null; match?: Match | null
}
type Form = AppDetails
type EmailPreview = {
  batch_id: number; total_rows: number; valid_rows: number; invalid_rows: number
  possible_duplicate_rows: number; found_count: number; expired_skipped: number
  rows: Array<{
    row_number: number; valid: boolean; errors: string[]
    duplicates: Array<{ similarity: number; title: string; company: string }>
    job: { title: string; company: string; location?: string | null; original_url?: string | null }
  }>
}

const areas = ['All Melbourne', 'Melbourne CBD', 'South East Melbourne', 'Bayside']
const areaTerms: Record<string, string[]> = {
  'Melbourne CBD': ['melbourne cbd', 'melbourne city', 'melbourne,', 'docklands', 'southbank', 'carlton', 'east melbourne', 'north melbourne'],
  'South East Melbourne': ['south east', 'south-east', 'south eastern', 'dandenong', 'clayton', 'monash', 'mulgrave', 'cranbourne', 'frankston', 'oakleigh', 'springvale', 'keysborough', 'noble park', 'pakenham', 'berwick', 'narre warren', 'moorabbin'],
  Bayside: ['bayside', 'brighton', 'sandringham', 'hampton', 'cheltenham', 'mentone', 'beaumaris', 'black rock', 'parkdale', 'mordialloc', 'edithvale', 'aspendale'],
}
const dateText = (value?: string | null) => value ? new Date(value).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : 'Recently added'
const closingDateText = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
const emptyForm = (job: Job): Form => ({
  status: job.application?.status || 'new', application_date: job.application?.application_date || '',
  resume_version: job.application?.resume_version || '', cover_letter: job.application?.cover_letter || '',
  contact_person: job.application?.contact_person || '', follow_up_date: job.application?.follow_up_date || '',
  interview_notes: job.application?.interview_notes || '',
})

function App() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [apiOnline, setApiOnline] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [view, setView] = useState<'all' | 'applied'>('all')
  const [area, setArea] = useState('All Melbourne')
  const [suburb, setSuburb] = useState('all')
  const [sort, setSort] = useState('relevance')
  const [selected, setSelected] = useState<Job | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [mobileFilters, setMobileFilters] = useState(false)
  const [emailOpen, setEmailOpen] = useState(false)
  const [emailBody, setEmailBody] = useState('')
  const [emailPreview, setEmailPreview] = useState<EmailPreview | null>(null)
  const [emailError, setEmailError] = useState('')
  const [emailBusy, setEmailBusy] = useState(false)
  const [gmailConnected, setGmailConnected] = useState(false)
  const [gmailClientConfigured, setGmailClientConfigured] = useState(false)
  const [emailPreviewSource, setEmailPreviewSource] = useState<'manual' | 'gmail'>('manual')
  const [gmailSyncStatus, setGmailSyncStatus] = useState('')
  const startupSyncStarted = useRef(false)
  const [deletingJobId, setDeletingJobId] = useState<number | null>(null)

  const loadJobs = async () => {
    setLoading(true); setError('')
    try {
      const response = await fetch(`${API}/api/jobs`)
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      setJobs(await response.json())
      setApiOnline(true)
    } catch { setApiOnline(false); setError(`Could not reach the API at ${API}. Start the FastAPI server and refresh.`) }
    finally { setLoading(false) }
  }
  useEffect(() => {
    if (startupSyncStarted.current) return
    startupSyncStarted.current = true
    void (async () => {
      await loadJobs()
      try {
        const statusResponse = await fetch(`${API}/api/email/gmail/status`)
        if (!statusResponse.ok || !(await statusResponse.json()).connected) return
        setGmailSyncStatus('Checking Gmail job alerts…')
        const syncResponse = await fetch(`${API}/api/email/gmail/sync`, { method: 'POST' })
        const result = await syncResponse.json()
        if (!syncResponse.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Gmail sync failed.')
        const added = Number(result.imported_count || 0)
        setGmailSyncStatus(added ? `Gmail checked · ${added} new ${added === 1 ? 'job' : 'jobs'} added` : 'Gmail checked · no new jobs')
        await loadJobs()
      } catch {
        setGmailSyncStatus('Could not check Gmail alerts. Use Import SEEK email to retry.')
      }
    })()
  }, [])
  useEffect(() => { if (selected) setForm(emptyForm(selected)) }, [selected])

  const suburbs = useMemo(() => {
    const values = new Set<string>()
    jobs.forEach(job => job.location?.split(/[,/|]/).map(s => s.trim()).filter(Boolean).forEach(s => values.add(s)))
    return [...values].sort((a, b) => a.localeCompare(b))
  }, [jobs])
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return jobs.filter(job => {
      const text = [job.title, job.company, job.location, job.description, job.source?.name].join(' ').toLowerCase()
      const location = (job.location || '').toLowerCase()
      const inArea = area === 'All Melbourne' || areaTerms[area].some(term => location.includes(term))
      const inSuburb = suburb === 'all' || location.includes(suburb.toLowerCase())
      const jobStatus = job.application?.status || 'new'
      const inView = view === 'all' || ['applied', 'interview'].includes(jobStatus)
      return inView && (!needle || text.includes(needle)) && (status === 'all' || jobStatus === status) && inArea && inSuburb
    }).sort((a, b) => sort === 'relevance'
      ? (b.match?.score || 0) - (a.match?.score || 0)
      : sort === 'oldest' ? +new Date(a.date_discovered) - +new Date(b.date_discovered)
        : +new Date(b.date_discovered) - +new Date(a.date_discovered))
  }, [jobs, query, status, area, suburb, sort, view])

  const newCount = jobs.filter(j => (j.application?.status || 'new') === 'new').length
  const appliedCount = jobs.filter(j => ['applied', 'interview'].includes(j.application?.status || '')).length
  const average = jobs.length ? Math.round(jobs.reduce((n, j) => n + (j.match?.score || 0), 0) / jobs.length) : 0

  const saveApplication = async () => {
    if (!selected || !form) return
    setSaving(true); setError(''); setSaved(false)
    try {
      const payload: Partial<Form> = {
        ...form,
        application_date: form.application_date || null,
        follow_up_date: form.follow_up_date || null,
      }
      if (form.status === 'applied' && !form.application_date) delete payload.application_date
      const response = await fetch(`${API}/api/jobs/${selected.id}/application`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error('Could not save application details')
      const refreshed = await fetch(`${API}/api/jobs`).then(r => r.json()) as Job[]
      setJobs(refreshed); setSelected(refreshed.find(j => j.id === selected.id) || null); setSaved(true)
    } catch { setError('Could not save your application details. Please try again.') }
    finally { setSaving(false) }
  }

  const update = (key: keyof Form, value: string) => setForm(current => current ? ({ ...current, [key]: value }) : current)

  const deleteJob = async (job: Job) => {
    if (!window.confirm(`Delete “${job.title}” at ${job.company}? Its application notes will also be removed.`)) return
    setDeletingJobId(job.id); setError('')
    try {
      const response = await fetch(`${API}/api/jobs/${job.id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Could not delete this role.')
      setJobs(current => current.filter(item => item.id !== job.id))
      if (selected?.id === job.id) { setSelected(null); setForm(null) }
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not delete this role.') }
    finally { setDeletingJobId(null) }
  }

  const previewSeekEmail = async () => {
    setEmailBusy(true); setEmailError(''); setEmailPreview(null); setEmailPreviewSource('manual')
    try {
      const response = await fetch(`${API}/api/imports/seek-grad-email/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: 'Forwarded SEEK Grad alert', body: emailBody }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not parse this email.')
      setEmailPreview(result)
    } catch (e) { setEmailError(e instanceof Error ? e.message : 'Could not parse this email.') }
    finally { setEmailBusy(false) }
  }

  const commitSeekEmail = async () => {
    if (!emailPreview) return
    setEmailBusy(true); setEmailError('')
    try {
      const endpoint = emailPreviewSource === 'gmail'
        ? `${API}/api/imports/gmail/seek-grad/${emailPreview.batch_id}/commit`
        : `${API}/api/imports/seek-grad-email/${emailPreview.batch_id}/commit`
      const response = await fetch(endpoint, { method: 'POST' })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not import these listings.')
      await loadJobs(); setEmailOpen(false); setEmailPreview(null); setEmailBody('')
    } catch (e) { setEmailError(e instanceof Error ? e.message : 'Could not import these listings.') }
    finally { setEmailBusy(false) }
  }

  const loadGmailStatus = async () => {
    try {
      const response = await fetch(`${API}/api/email/gmail/status`)
      if (!response.ok) return
      const result = await response.json()
      setGmailConnected(result.connected); setGmailClientConfigured(result.client_configured)
    } catch { /* Gmail remains optional; manual imports still work. */ }
  }

  const connectGmail = async () => {
    setEmailBusy(true); setEmailError('')
    try {
      const response = await fetch(`${API}/api/email/gmail/connect`, { method: 'POST' })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not connect Gmail.')
      setGmailConnected(true)
    } catch (e) { setEmailError(e instanceof Error ? e.message : 'Could not connect Gmail.') }
    finally { setEmailBusy(false); void loadGmailStatus() }
  }

  const previewGmail = async () => {
    setEmailBusy(true); setEmailError(''); setEmailPreview(null); setEmailPreviewSource('gmail')
    try {
      const response = await fetch(`${API}/api/imports/gmail/seek-grad/preview`, { method: 'POST' })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not read Gmail alerts.')
      setEmailPreview(result)
    } catch (e) { setEmailError(e instanceof Error ? e.message : 'Could not read Gmail alerts.') }
    finally { setEmailBusy(false) }
  }

  const loadEmailFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setEmailError(''); setEmailPreview(null)
    try { setEmailBody(await file.text()) }
    catch { setEmailError('Could not read that email file.') }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><BriefcaseBusiness size={20}/></span><span>job<span className="brand-light">finder</span></span></div>
      <div className="side-label">WORKSPACE</div>
      <button className={`nav-item ${view === 'all' ? 'active' : ''}`} onClick={() => {setView('all');setStatus('all')}}><span className="nav-icon"><BriefcaseBusiness size={17}/></span> Job dashboard <span className="nav-count">{jobs.length}</span></button>
      <button className={`nav-item ${view === 'applied' ? 'active' : ''}`} onClick={() => {setView('applied');setStatus('all')}}><span className="nav-icon"><Check size={17}/></span> Applied jobs <span className="nav-count">{appliedCount}</span></button>
      <div className="side-label sources-label">YOUR SEARCH</div>
      <div className="focus-card"><div className="focus-icon"><Sparkles size={16}/></div><div><strong>Melbourne focus</strong><span>Roles matched to your profile</span></div></div>
      <div className="sidebar-bottom"><div className="profile-avatar">E</div><div className="profile-name"><strong>Erik</strong><span>Candidate profile</span></div><ChevronDown size={15}/></div>
    </aside>

    <main className="main-area">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <strong>{view === 'applied' ? 'Applied jobs' : 'Job dashboard'}</strong></div><div className="topbar-right"><span className={`sync-dot ${apiOnline ? '' : 'offline'}`}/>{apiOnline ? 'API connected' : 'API offline'} <button className="avatar-small">E</button></div></header>
      <div className="content-wrap">
        <section className="welcome-row"><div><div className="eyebrow">{new Intl.DateTimeFormat('en-AU', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()).toUpperCase()}</div><h1>Your next move starts here.</h1><p className="welcome-sub">A clearer view of the roles that fit you.</p></div><div className="header-actions"><button className="icon-button mobile-filter-toggle" onClick={() => setMobileFilters(!mobileFilters)} aria-label="Toggle filters"><SlidersHorizontal size={18}/></button><button className="import-email-button" onClick={() => {setEmailOpen(true);setEmailError('');setEmailPreview(null);setEmailPreviewSource('manual');void loadGmailStatus()}}><Mail size={15}/> Import SEEK email</button><button className="refresh-button" onClick={() => void loadJobs()}><ArrowDownUp size={15}/> Refresh listings</button></div></section>
        {gmailSyncStatus && <div className="gmail-sync-status" role="status">{gmailSyncStatus}</div>}

        <section className="stat-grid">
          <div className="stat-card"><div className="stat-top"><span>New opportunities</span><span className="stat-icon green"><Sparkles size={16}/></span></div><div className="stat-value">{newCount}<small> roles</small></div><div className="stat-note">Ready for your review</div></div>
          <div className="stat-card"><div className="stat-top"><span>In progress</span><span className="stat-icon blue"><Clock3 size={16}/></span></div><div className="stat-value">{appliedCount}<small> roles</small></div><div className="stat-note">Applied or interviewing</div></div>
          <div className="stat-card"><div className="stat-top"><span>Average fit</span><span className="stat-icon purple"><Sparkles size={16}/></span></div><div className="stat-value">{average}<small> / 100</small></div><div className="stat-note">Across your saved roles</div></div>
          <div className="stat-card"><div className="stat-top"><span>Tracked roles</span><span className="stat-icon amber"><BriefcaseBusiness size={16}/></span></div><div className="stat-value">{jobs.length}<small> total</small></div><div className="stat-note">Your personal pipeline</div></div>
        </section>

        <section className="jobs-section">
          <div className="section-heading"><div><div className="section-kicker">{view === 'applied' ? 'YOUR APPLICATIONS' : 'YOUR OPPORTUNITIES'}</div><h2>{view === 'applied' ? 'Applied jobs' : 'Find your fit'} <span className="result-count">{filtered.length}</span></h2></div><div className="sort-wrap"><ArrowDownUp size={15}/><select aria-label="Sort jobs" value={sort} onChange={e => setSort(e.target.value)}><option value="relevance">Best match</option><option value="recent">Most recent</option><option value="oldest">Oldest first</option></select><ChevronDown size={14}/></div></div>

          <div className={`filter-bar ${mobileFilters ? 'filters-open' : ''}`}>
            <label className="search-box"><Search size={17}/><input placeholder="Search roles, companies, skills..." value={query} onChange={e => setQuery(e.target.value)}/>{query && <button onClick={() => setQuery('')} aria-label="Clear search"><X size={14}/></button>}</label>
            <label className="select-filter"><MapPin size={15}/><select value={area} onChange={e => { setArea(e.target.value); setSuburb('all') }} aria-label="Filter by area">{areas.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={13}/></label>
            <label className="select-filter suburb-filter"><select value={suburb} onChange={e => setSuburb(e.target.value)} aria-label="Filter by suburb"><option value="all">All suburbs</option>{suburbs.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={13}/></label>
            <label className="select-filter status-filter"><Filter size={15}/><select value={status} onChange={e => setStatus(e.target.value)} aria-label="Filter by status"><option value="all">All statuses</option>{STATUSES.map(s => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}</select><ChevronDown size={13}/></label>
          </div>

          {error && <div className="error-banner"><CircleHelp size={16}/>{error}<button onClick={() => void loadJobs()}><span>Retry</span></button></div>}
          {loading ? <div className="empty-state"><div className="loader"/><strong>Finding your opportunities...</strong><span>Loading your listings and match scores.</span></div> : filtered.length === 0 ? <div className="empty-state"><div className="empty-icon"><Search size={22}/></div><strong>{jobs.length ? 'No roles match these filters' : 'Your next opportunity is waiting'}</strong><span>{jobs.length ? 'Try widening your search or clearing a filter.' : 'Add jobs through the API or import a CSV to see your dashboard take shape.'}</span>{jobs.length > 0 && <button className="text-button" onClick={() => {setQuery('');setArea('All Melbourne');setSuburb('all');setStatus('all')}}>Clear all filters</button>}</div> : <div className="job-list">{filtered.map(job => <article className="job-card" key={job.id}>
            <div className="job-logo">{job.company.slice(0, 1).toUpperCase()}</div>
            <div className="job-main"><div className="job-meta"><span>{job.company}</span><span className="meta-dot">·</span><span>{job.source?.name || 'Manual entry'}</span></div><h3>{job.title}</h3><div className="job-details"><span><MapPin size={14}/>{job.location || 'Location not listed'}</span>{job.employment_type && <span><BriefcaseBusiness size={14}/>{job.employment_type}</span>}{job.salary_text && <span className="salary">{job.salary_text}</span>}{job.closing_date && <span className="closing-date"><CalendarDays size={14}/>Closes {closingDateText(job.closing_date)}</span>}</div><div className="job-foot"><span className="date-label"><CalendarDays size={13}/>{job.date_posted ? `Posted ${dateText(job.date_posted)}` : `Added ${dateText(job.date_discovered)}`}</span><span className={`status-pill ${job.application?.status || 'new'}`}>{job.application?.status || 'new'}</span></div></div>
            <div className="job-match"><div className={`score-ring ${scoreTone(job.match?.score || 0)}`}><span>{job.match?.score ?? '—'}</span></div><span className="score-caption">FIT SCORE</span></div>
            <div className="job-actions"><button className="details-button" onClick={() => setSelected(job)}>Track role <ArrowUpRight size={15}/></button>{job.original_url && <a className="details-button apply-link" href={job.original_url} target="_blank" rel="noreferrer">Open role <ExternalLink size={14}/></a>}<button className="delete-button" onClick={() => void deleteJob(job)} disabled={deletingJobId === job.id} aria-label={`Delete ${job.title}`}><Trash2 size={14}/><span>{deletingJobId === job.id ? 'Deleting…' : 'Delete'}</span></button></div>
          </article>)}</div>}
          {!loading && filtered.length > 0 && <div className="list-footer">Showing {filtered.length} of {jobs.length} roles <span>•</span> Sorted by {sort === 'relevance' ? 'best match' : sort === 'recent' ? 'most recent' : 'oldest first'}</div>}
        </section>
        <footer className="footer"><span>Made for your next chapter.</span><span>Your data stays on this device.</span></footer>
      </div>
    </main>

    {selected && form && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setSelected(null) }}><section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-head"><div><div className="section-kicker">ROLE DETAILS</div><h2 id="modal-title">{selected.title}</h2><div className="modal-company">{selected.company} <span>·</span> {selected.location || 'Location not listed'}</div></div><button className="icon-button" onClick={() => setSelected(null)} aria-label="Close details"><X size={19}/></button></div>
      <div className="modal-scroll"><div className="match-panel"><div className={`score-ring large ${scoreTone(selected.match?.score || 0)}`}><span>{selected.match?.score ?? '—'}</span></div><div><div className="panel-label">PROFILE MATCH <span>·</span> OUT OF 100</div><p>{selected.match?.explanation || 'No match analysis is available.'}</p></div></div>
        <div className="skill-groups">{Boolean(selected.match?.matched_skills.length) && <div><div className="panel-label">SKILLS YOU HAVE</div><div className="chips">{selected.match?.matched_skills.map(x => <span className="chip positive" key={x}><Check size={12}/>{x}</span>)}</div></div>}{Boolean(selected.match?.missing_skills.length) && <div><div className="panel-label">POTENTIAL SKILL GAPS</div><div className="chips">{selected.match?.missing_skills.map(x => <span className="chip" key={x}>{x}</span>)}</div></div>}{Boolean(selected.match?.experience_flags.length) && <div className="flags">{selected.match?.experience_flags.map(x => <p key={x}><CircleHelp size={14}/>{x}</p>)}</div>}</div>
        {selected.description && <div className="description-block"><div className="panel-label">JOB DESCRIPTION</div><p>{selected.description}</p></div>}
        <div className="application-form"><div className="form-heading"><div><div className="section-kicker">APPLICATION TRACKER</div><h3>Keep this role moving</h3></div><label className="status-edit"><span>Status</span><select value={form.status} onChange={e => update('status', e.target.value)}>{STATUSES.map(s => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}</select></label></div>
          <div className="form-grid"><label>Application date<input type="date" value={form.application_date || ''} onChange={e => update('application_date', e.target.value)}/></label><label>Resume version<input placeholder="e.g. Software CV v2" value={form.resume_version || ''} onChange={e => update('resume_version', e.target.value)}/></label><label>Contact person<input placeholder="Name or email" value={form.contact_person || ''} onChange={e => update('contact_person', e.target.value)}/></label><label>Follow-up date<input type="date" value={form.follow_up_date || ''} onChange={e => update('follow_up_date', e.target.value)}/></label><label className="wide">Cover letter<textarea rows={3} placeholder="Paste or note your cover letter..." value={form.cover_letter || ''} onChange={e => update('cover_letter', e.target.value)}/></label><label className="wide">Interview notes<textarea rows={3} placeholder="Questions, people, next steps..." value={form.interview_notes || ''} onChange={e => update('interview_notes', e.target.value)}/></label></div>
        </div>
      </div><div className="modal-actions">{saved && <span className="saved-note"><Check size={15}/> Saved</span>}<button className="cancel-button" onClick={() => setSelected(null)}>Close</button><button className="save-button" disabled={saving} onClick={() => void saveApplication()}>{saving ? 'Saving...' : 'Save application'}</button></div>
    </section></div>}
    {emailOpen && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setEmailOpen(false) }}><section className="detail-modal email-import-modal" role="dialog" aria-modal="true" aria-labelledby="email-modal-title">
      <div className="modal-head"><div><div className="section-kicker">SEEK GRAD ALERT</div><h2 id="email-modal-title">Import jobs from an email</h2><div className="modal-company">Paste the forwarded alert text. We preview listings and duplicates before saving.</div></div><button className="icon-button" onClick={() => setEmailOpen(false)} aria-label="Close import"><X size={19}/></button></div>
      <div className="modal-scroll"><div className="email-import-help">Gmail connection is optional. It requests read-only mailbox access and searches only the configured label plus SEEK Grad sender. Gmail still grants this scope access to mailbox messages and settings. The preview ignores listings whose closing date has passed.</div>
        <div className="gmail-connect-row"><span>{gmailConnected ? 'Gmail connected' : gmailClientConfigured ? 'OAuth file ready' : 'Gmail not configured'}</span><button className="cancel-button" disabled={emailBusy || !gmailClientConfigured} onClick={() => void connectGmail()}>{gmailConnected ? 'Reconnect Gmail' : 'Connect Gmail'}</button><button className="save-button" disabled={emailBusy || !gmailConnected} onClick={() => void previewGmail()}>{emailBusy ? 'Reading...' : 'Preview Gmail alerts'}</button></div>
        <div className="email-import-help">To import manually, open a forwarded alert in Gmail, choose More → Download message, then select its .eml file, or paste the message body.</div>
        <label className="email-file-label">Choose email file<input type="file" accept=".eml,message/rfc822" onChange={e => void loadEmailFile(e)}/></label>
        <label className="email-body-label">Forwarded email body<textarea rows={12} value={emailBody} onChange={e => {setEmailBody(e.target.value);setEmailPreview(null)}} placeholder="Paste the SEEK Grad alert body here..."/></label>
        {emailError && <div className="error-banner"><CircleHelp size={16}/>{emailError}</div>}
        {emailPreview && <div className="email-preview"><div className="email-preview-summary"><strong>{emailPreview.valid_rows} ready to import</strong><span>{emailPreview.expired_skipped} expired skipped · {emailPreview.possible_duplicate_rows} possible duplicate(s)</span></div>{emailPreview.rows.map(row => <div className="email-preview-row" key={row.row_number}><strong>{row.job.title}</strong><span>{row.job.company || 'Company not found'} · {row.job.location || 'Location not listed'}</span>{row.duplicates.length > 0 && <small>Possible match: {row.duplicates.map(d => `${d.title} at ${d.company}`).join('; ')}</small>}{row.errors.length > 0 && <small>{row.errors.join(', ')}</small>}</div>)}</div>}
      </div><div className="modal-actions"><button className="cancel-button" onClick={() => setEmailOpen(false)}>Close</button>{emailPreview ? <button className="save-button" disabled={emailBusy || emailPreview.valid_rows === 0} onClick={() => void commitSeekEmail()}>{emailBusy ? 'Importing...' : 'Import previewed jobs'}</button> : <button className="save-button" disabled={emailBusy || !emailBody.trim()} onClick={() => void previewSeekEmail()}>{emailBusy ? 'Reading alert...' : 'Preview jobs'}</button>}</div>
    </section></div>}
  </div>
}

function scoreTone(score: number) { return score >= 75 ? 'high' : score >= 50 ? 'medium' : 'low' }

export default App
