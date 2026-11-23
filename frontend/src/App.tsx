import { useEffect, useRef, useState } from 'react'
import {
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Disc3,
  Download,
  ExternalLink,
  FolderHeart,
  Headphones,
  Library,
  Link2,
  ListMusic,
  LoaderCircle,
  Moon,
  Music2,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  Trash2,
  X,
} from 'lucide-react'
import {
  active,
  api,
  bytes,
  duration,
  type Health,
  type Job,
  type Preferences,
  type Preview,
  type Track,
} from './api'

type Page = 'Downloader' | 'Library' | 'Settings'
const statuses: Record<string, string> = {
  queued: 'In queue',
  downloading: 'Downloading',
  completed: 'Complete',
  failed: 'Failed',
  cancelled: 'Cancelled',
  partial: 'Partially complete',
  interrupted: 'Interrupted',
}

function Cover({ src, large = false }: { src?: string; large?: boolean }) {
  return (
    <div className={`cover ${large ? 'large' : ''}`}>
      {src ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          onError={(e) => {
            e.currentTarget.style.display = 'none'
          }}
        />
      ) : (
        <Music2 size={large ? 32 : 19} />
      )}
    </div>
  )
}

function TrackRow({
  job,
  track,
  index,
  onPlay,
}: {
  job: Job
  track: Track
  index: number
  onPlay: (job: Job, index: number) => void
}) {
  return (
    <div className="track-row">
      <span className="track-number">{String(index + 1).padStart(2, '0')}</span>
      <Cover src={track.song.cover_url} />
      <div className="track-info">
        <strong>{track.song.name}</strong>
        <small>{track.song.artists.join(', ')}</small>
        {track.error && <span className="track-error">{track.error}</span>}
      </div>
      <span className="track-duration">{duration(track.song.duration)}</span>
      {track.status === 'completed' ? (
        <div className="row-actions">
          <button
            className="icon-button"
            title={`Play ${track.song.name}`}
            onClick={() => onPlay(job, index)}
          >
            <Play size={16} />
          </button>
          <a
            className="icon-button"
            aria-label={`Save ${track.song.name}`}
            href={`/api/jobs/${job.id}/tracks/${index}/file`}
          >
            <Download size={16} />
          </a>
        </div>
      ) : (
        <span className={`track-state ${track.status}`}>
          {track.status === 'downloading'
            ? `${track.message} · ${Math.round(track.progress)}%`
            : statuses[track.status]}
        </span>
      )}
    </div>
  )
}

export default function App() {
  const [page, setPage] = useState<Page>('Downloader')
  const [jobs, setJobs] = useState<Job[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [connectionError, setConnectionError] = useState('')
  const [url, setUrl] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [prefs, setPrefs] = useState<Preferences>({ format: 'mp3', bitrate: 'auto' })
  const [format, setFormat] = useState('mp3')
  const [bitrate, setBitrate] = useState('auto')
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [playing, setPlaying] = useState<{ job: Job; index: number } | null>(null)
  const [deleteJob, setDeleteJob] = useState<Job | null>(null)
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'dark')
  const input = useRef<HTMLInputElement>(null)
  const dialog = useRef<HTMLElement>(null)
  const [help, setHelp] = useState(false)

  async function refresh() {
    const [nextJobs, nextHealth] = await Promise.all([api<Job[]>('/jobs'), api<Health>('/health')])
    setJobs(nextJobs)
    setHealth(nextHealth)
    setConnectionError('')
  }
  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        if (alive) await refresh()
      } catch (e) {
        if (alive) setConnectionError((e as Error).message)
      }
      if (alive) timer = setTimeout(poll, 1800)
    }
    void poll()
    api<Preferences>('/preferences')
      .then((p) => {
        if (alive) {
          setPrefs(p)
          setFormat(p.format)
          setBitrate(p.bitrate)
        }
      })
      .catch(() => {})
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [])
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(''), 4500)
      return () => clearTimeout(timer)
    }
  }, [toast])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('side-a-theme', theme)
    } catch {
      /* private browsing */
    }
  }, [theme])
  useEffect(() => {
    if (!deleteJob && !help) return
    const previous = document.activeElement as HTMLElement | null
    const initialOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.current?.querySelector<HTMLButtonElement>('button')?.focus()
    function keydown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) {
        setDeleteJob(null)
        setHelp(false)
      }
      if (e.key === 'Tab') {
        const elements = dialog.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input, select',
        )
        if (!elements?.length) return
        const first = elements[0],
          last = elements[elements.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      document.body.style.overflow = initialOverflow
      previous?.focus()
    }
  }, [deleteJob, help, busy])

  async function loadPreview(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setPreview(null)
    try {
      const result = await api<Preview>('/preview', {
        method: 'POST',
        body: JSON.stringify({ url }),
      })
      setPreview(result)
      setSelected(new Set(result.songs.map((_, i) => i)))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  async function queueDownload() {
    if (!preview) return
    setBusy('queue')
    setError('')
    try {
      const job = await api<Job>('/jobs', {
        method: 'POST',
        body: JSON.stringify({ preview_id: preview.id, indices: [...selected], format, bitrate }),
      })
      setPreview(null)
      setUrl('')
      setExpanded(job.id)
      setToast('Added to your download queue')
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  async function action(job: Job, kind: 'cancel' | 'retry' | 'delete') {
    setBusy(job.id)
    try {
      await api(`/jobs/${job.id}${kind === 'delete' ? '' : `/${kind}`}`, {
        method: kind === 'delete' ? 'DELETE' : 'POST',
      })
      if (kind === 'delete' && playing?.job.id === job.id) setPlaying(null)
      setDeleteJob(null)
      await refresh()
      setToast(
        kind === 'delete'
          ? 'Download and files deleted'
          : kind === 'retry'
            ? 'Unfinished tracks added to queue'
            : 'Download cancelled',
      )
    } catch (e) {
      setToast((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  function go(next: Page) {
    setPage(next)
    setQuery('')
    setFilter('all')
  }
  const allTracks = jobs
    .flatMap((job) => job.tracks.map((track, index) => ({ job, track, index })))
    .filter((t) => t.track.status === 'completed')
  const totalSize = allTracks.reduce((sum, t) => sum + t.track.size, 0)
  const queued = jobs.filter(active)
  const visibleJobs = jobs.filter(
    (job) =>
      (filter === 'all' || (filter === 'active' ? active(job) : job.status === filter)) &&
      `${job.title} ${job.tracks.map((t) => t.song.artists.join(' ')).join(' ')}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  )
  const library = allTracks.filter((t) =>
    `${t.track.song.name} ${t.track.song.artists.join(' ')} ${t.track.song.album_name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  )
  const formatControls = (
    f: string,
    b: string,
    onFormat: (v: string) => void,
    onBitrate: (v: string) => void,
  ) => (
    <div className="format-controls">
      <label>
        Audio format
        <select value={f} onChange={(e) => onFormat(e.target.value)}>
          <option value="mp3">MP3 · Most compatible</option>
          <option value="m4a">M4A · AAC audio</option>
          <option value="opus">Opus · Smaller files</option>
          <option value="flac">FLAC · Larger files</option>
        </select>
      </label>
      <label>
        Encoding bitrate
        <select disabled={f === 'flac'} value={b} onChange={(e) => onBitrate(e.target.value)}>
          <option value="auto">Auto · Source quality</option>
          <option value="128k">128 kbps</option>
          <option value="192k">192 kbps</option>
          <option value="256k">256 kbps</option>
          <option value="320k">320 kbps</option>
        </select>
      </label>
    </div>
  )

  return (
    <div className={`app ${playing ? 'has-player' : ''}`}>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault()
            go('Downloader')
          }}
        >
          <span className="brand-icon">
            <AudioLines size={25} strokeWidth={2.5} />
          </span>
          <span>
            side a<span className="brand-dot">.</span>
          </span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {(
            [
              ['Downloader', ArrowDownToLine],
              ['Library', Library],
              ['Settings', Settings2],
            ] as const
          ).map(([name, Icon]) => (
            <button
              key={name}
              aria-label={name}
              title={name}
              className={`nav-item ${page === name ? 'selected' : ''}`}
              onClick={() => go(name)}
            >
              <Icon size={19} />
              <span>{name}</span>
              {name === 'Downloader' && queued.length > 0 && (
                <span className="nav-count">{queued.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="offline-note">
            <div className="mini-record">
              <Disc3 size={26} />
            </div>
            <strong>Good music. Anywhere.</strong>
            <p>
              Your collection, a little closer.
              <br />
              Made for offline listening.
            </p>
            <span>
              POWERED BY SPOTDL <ArrowRight size={12} />
            </span>
          </div>
          <button className="help-link" onClick={() => setHelp(true)}>
            <CircleHelp size={17} /> How it works <ExternalLink size={13} />
          </button>
          <div className="local-user">
            <span className="user-avatar">Y</span>
            <div>
              <strong>Your workspace</strong>
              <small>
                <span className="dot" /> Personal & local
              </small>
            </div>
            <button
              className="icon-button theme-toggle"
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className={`engine-state ${connectionError ? 'offline' : ''}`}>
            <span className="dot" />
            {connectionError
              ? 'Server disconnected'
              : health
                ? 'Download engine online'
                : 'Connecting to engine'}
          </div>
        </header>
        <main>
          {connectionError && (
            <div className="error-banner" role="alert">
              Cannot connect to the FastAPI server. {connectionError}
              <button
                onClick={() => {
                  void refresh().catch((e) => setConnectionError(e.message))
                }}
              >
                Reconnect
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <span className="eyebrow">YOUR OFFLINE COLLECTION STARTS HERE</span>
              <h1>
                {page === 'Downloader'
                  ? 'Bring your music home.'
                  : page === 'Library'
                    ? 'The good stuff. On repeat.'
                    : 'Make yourself at home.'}
              </h1>
              <p>
                {page === 'Downloader'
                  ? 'Turn your favorite tracks and playlists into your personal collection.'
                  : page === 'Library'
                    ? 'Everything you’ve downloaded, ready whenever you are.'
                    : 'A few small details. A better listening experience.'}
              </p>
            </div>
            <span className="page-mark">
              <Headphones size={23} />
            </span>
          </div>

          {page === 'Downloader' && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <span className="pill">
                    <span className="dot" /> FROM YOUR PLAYLIST. TO YOUR POCKET.
                  </span>
                  <h2>
                    Less streaming.
                    <br />
                    More <em>listening.</em>
                  </h2>
                  <p>
                    All the songs you love, with the artwork and details.
                    <br className="desktop-break" /> Paste a Spotify link. We’ll take it from there.
                  </p>
                  <div className="hero-tags">
                    <span>
                      <Check size={14} /> Tracks & playlists
                    </span>
                    <span>
                      <Check size={14} /> Album artwork
                    </span>
                    <span>
                      <Check size={14} /> Yours to keep
                    </span>
                  </div>
                </div>
                <div className="record-art" aria-hidden="true">
                  <div className="record-sleeve">
                    <span>SIDE A / VOL. 001</span>
                    <AudioLines size={46} />
                    <b>
                      for the
                      <br />
                      love of
                      <br />
                      <i>music.</i>
                    </b>
                    <small>THE OFFLINE SESSIONS</small>
                  </div>
                  <div className="vinyl">
                    <div className="vinyl-label">
                      <AudioLines size={26} />
                      <span>SIDE A</span>
                      <i />
                    </div>
                  </div>
                  <div className="record-caption">
                    SOUNDS BETTER WHEN IT’S YOURS <span>↗</span>
                  </div>
                </div>
              </section>
              <div className="stats-grid">
                <div className="stat">
                  <span className="stat-icon">
                    <Music2 size={19} />
                  </span>
                  <div>
                    <strong>
                      {allTracks.length}
                      <small>tracks</small>
                    </strong>
                    <p>In your collection</p>
                  </div>
                </div>
                <div className="stat">
                  <span className="stat-icon">
                    <ListMusic size={19} />
                  </span>
                  <div>
                    <strong>
                      {jobs.filter((j) => j.kind !== 'track' && j.status === 'completed').length}
                      <small>collections</small>
                    </strong>
                    <p>Downloaded in full</p>
                  </div>
                </div>
                <div className="stat">
                  <span className="stat-icon">
                    <ArrowDownToLine size={19} />
                  </span>
                  <div>
                    <strong>
                      {queued.length}
                      <small>downloads</small>
                    </strong>
                    <p>Currently in queue</p>
                  </div>
                </div>
                <div className="stat">
                  <span className="stat-icon">
                    <FolderHeart size={19} />
                  </span>
                  <div>
                    <strong>
                      {bytes(totalSize).split(' ')[0]}
                      <small>{bytes(totalSize).split(' ')[1]}</small>
                    </strong>
                    <p>Saved for a good time</p>
                  </div>
                </div>
              </div>
              <section className="panel download-panel">
                <div className="section-title">
                  <div className="section-icon">
                    <Link2 size={20} />
                  </div>
                  <div>
                    <h2>Add something good</h2>
                    <p>A song, an album, or the whole playlist.</p>
                  </div>
                  <span className="supported">SPOTIFY LINKS</span>
                </div>
                <form onSubmit={loadPreview}>
                  <div className="url-field">
                    <Link2 size={19} />
                    <input
                      ref={input}
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      aria-label="Spotify link"
                      placeholder="Paste your Spotify link here…"
                      required
                      maxLength={400}
                    />
                    <button className="primary" disabled={loading || !url.trim()}>
                      {loading ? <LoaderCircle size={17} className="spin" /> : <Plus size={17} />}
                      {loading ? 'Finding your music…' : 'Preview link'}
                      {!loading && <ArrowRight size={17} />}
                    </button>
                  </div>
                </form>
                <div className="input-note">
                  <ShieldCheck size={14} /> Public Spotify tracks, albums & playlists <span>·</span>{' '}
                  No Spotify login needed by default
                </div>
                {error && (
                  <div className="error-banner" role="alert">
                    {error}
                  </div>
                )}
                {loading && (
                  <div className="loading-preview">
                    <LoaderCircle className="spin" size={22} />
                    <div>
                      <strong>Getting the track list</strong>
                      <p>Large playlists can take a moment. Keep this tab open.</p>
                    </div>
                  </div>
                )}
                {preview && (
                  <div className="preview">
                    <div className="preview-header">
                      <Cover src={preview.cover_url} large />
                      <div>
                        <span className="eyebrow">{preview.kind}</span>
                        <h3>{preview.title}</h3>
                        <p>
                          {preview.songs.length} tracks ·{' '}
                          {Math.round(preview.songs.reduce((s, t) => s + t.duration, 0) / 60)} min
                        </p>
                      </div>
                      <button
                        className="icon-button"
                        title="Close preview"
                        onClick={() => setPreview(null)}
                      >
                        <X size={18} />
                      </button>
                    </div>
                    <div className="selection-header">
                      <label>
                        <input
                          type="checkbox"
                          checked={selected.size === preview.songs.length}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked
                                ? new Set(preview.songs.map((_, i) => i))
                                : new Set(),
                            )
                          }
                        />{' '}
                        Select all tracks
                      </label>
                      <span>{selected.size} selected</span>
                    </div>
                    <div className="preview-tracks">
                      {preview.songs.map((song, i) => (
                        <label className="preview-track" key={`${song.url}-${i}`}>
                          <input
                            type="checkbox"
                            aria-label={`Select ${song.name}`}
                            checked={selected.has(i)}
                            onChange={() => {
                              const next = new Set(selected)
                              if (next.has(i)) next.delete(i)
                              else next.add(i)
                              setSelected(next)
                            }}
                          />
                          <Cover src={song.cover_url} />
                          <span className="track-info">
                            <strong>{song.name}</strong>
                            <small>{song.artists.join(', ')}</small>
                          </span>
                          <small>{duration(song.duration)}</small>
                        </label>
                      ))}
                    </div>
                    {formatControls(format, bitrate, setFormat, setBitrate)}
                    <div className="preview-footer">
                      <small>
                        {format === 'flac'
                          ? 'FLAC conversion does not improve the original audio quality.'
                          : 'Encoding bitrate does not increase the quality of the source audio.'}
                      </small>
                      <button
                        className="primary"
                        disabled={selected.size === 0 || busy === 'queue'}
                        onClick={() => void queueDownload()}
                      >
                        <Download size={17} />
                        {busy === 'queue'
                          ? 'Adding…'
                          : `Download ${selected.size} ${selected.size === 1 ? 'track' : 'tracks'}`}
                      </button>
                    </div>
                  </div>
                )}
              </section>
            </>
          )}

          {page === 'Downloader' && (
            <section className="activity">
              <div className="activity-heading">
                <div>
                  <h2>
                    Your downloads <span className="count">{jobs.length}</span>
                  </h2>
                  <p>A little patience. A lot of good music.</p>
                </div>
                {jobs.length > 0 && (
                  <div className="filter-tabs" aria-label="Filter downloads">
                    {[
                      ['all', 'All'],
                      ['active', 'In progress'],
                      ['completed', 'Completed'],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        className={filter === value ? 'chosen' : ''}
                        onClick={() => setFilter(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {jobs.length > 0 && (
                <label className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search downloads"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Find a download…"
                  />
                </label>
              )}
              {visibleJobs.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    <ArrowDownToLine size={28} />
                    <span>
                      <Music2 size={13} />
                    </span>
                  </div>
                  <h3>
                    {jobs.length ? 'No downloads here yet' : 'Your next favorite is one link away'}
                  </h3>
                  <p>
                    {jobs.length
                      ? 'Try a different filter or search.'
                      : 'Paste a Spotify link above to start building your offline collection.'}
                  </p>
                  {!jobs.length && (
                    <button className="text-button" onClick={() => input.current?.focus()}>
                      Let’s add some music <ArrowRight size={15} />
                    </button>
                  )}
                </div>
              ) : (
                <div className="job-list">
                  {visibleJobs.map((job) => {
                    const done = job.tracks.filter((t) => t.status === 'completed').length
                    const progress = Math.round(
                      job.tracks.reduce((n, t) => n + t.progress, 0) / job.tracks.length,
                    )
                    return (
                      <article className="job-card" key={job.id}>
                        <div className="job-summary">
                          <Cover src={job.cover_url} />
                          <button
                            className="job-name"
                            onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                            aria-expanded={expanded === job.id}
                          >
                            <strong>{job.title}</strong>
                            <small>
                              {job.tracks.length} {job.tracks.length === 1 ? 'track' : 'tracks'}{' '}
                              <span>·</span> {job.format.toUpperCase()} <span>·</span>{' '}
                              {new Date(job.created_at).toLocaleDateString(undefined, {
                                month: 'short',
                                day: 'numeric',
                              })}
                            </small>
                          </button>
                          <span className={`status ${job.status}`}>
                            {job.status === 'downloading' && (
                              <LoaderCircle size={12} className="spin" />
                            )}
                            {job.status === 'completed' && <Check size={12} />}
                            {statuses[job.status]}
                          </span>
                          <div className="job-actions">
                            {done > 0 && (
                              <a
                                className="icon-button"
                                href={`/api/jobs/${job.id}/zip`}
                                title="Download ZIP"
                              >
                                <Download size={17} />
                              </a>
                            )}
                            {active(job) ? (
                              <button
                                className="icon-button"
                                title="Cancel download"
                                disabled={busy === job.id}
                                onClick={() => void action(job, 'cancel')}
                              >
                                <X size={17} />
                              </button>
                            ) : (
                              <>
                                {job.status !== 'completed' && (
                                  <button
                                    className="small-button"
                                    disabled={busy === job.id}
                                    onClick={() => void action(job, 'retry')}
                                  >
                                    Retry
                                  </button>
                                )}
                                <button
                                  className="icon-button"
                                  title={`Delete ${job.title}`}
                                  disabled={busy === job.id}
                                  onClick={() => setDeleteJob(job)}
                                >
                                  <Trash2 size={16} />
                                </button>
                              </>
                            )}
                            <button
                              className="icon-button"
                              title="Show tracks"
                              onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                            >
                              <ChevronDown
                                size={17}
                                className={expanded === job.id ? 'rotate' : ''}
                              />
                            </button>
                          </div>
                        </div>
                        {active(job) && (
                          <div className="job-progress">
                            <div>
                              <span>
                                {done} of {job.tracks.length} tracks ready
                              </span>
                              <span>{progress}%</span>
                            </div>
                            <progress max="100" value={progress} />
                          </div>
                        )}
                        {job.error && <div className="job-error">{job.error}</div>}
                        {expanded === job.id && (
                          <div className="job-tracks">
                            {job.tracks.map((track, i) => (
                              <TrackRow
                                onPlay={(job, index) => setPlaying({ job, index })}
                                job={job}
                                track={track}
                                index={i}
                                key={i}
                              />
                            ))}
                          </div>
                        )}
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          )}

          {page === 'Library' && (
            <section className="panel library-panel">
              <div className="library-header">
                <div>
                  <h2>
                    Your collection <span className="count">{allTracks.length}</span>
                  </h2>
                  <p>{bytes(totalSize)} of your favorite sounds, saved locally.</p>
                </div>
                <label className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Search library"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search tracks, artists, albums…"
                  />
                </label>
              </div>
              {library.length ? (
                <div className="library-list">
                  {library.map(({ job, track, index }) => (
                    <TrackRow
                      onPlay={(job, index) => setPlaying({ job, index })}
                      key={`${job.id}-${index}`}
                      job={job}
                      track={track}
                      index={index}
                    />
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">
                    <Library size={28} />
                  </div>
                  <h3>{query ? 'No tracks found' : 'A collection with your name on it'}</h3>
                  <p>
                    {query
                      ? 'Try another title, artist or album.'
                      : 'Your completed downloads will appear here, ready to play.'}
                  </p>
                  {!query && (
                    <button className="primary" onClick={() => go('Downloader')}>
                      <Plus size={16} /> Add your first tracks
                    </button>
                  )}
                </div>
              )}
            </section>
          )}

          {page === 'Settings' && (
            <div className="settings-grid">
              <section className="panel">
                <div className="section-title">
                  <Settings2 size={21} />
                  <div>
                    <h2>Download defaults</h2>
                    <p>A starting point for every new download.</p>
                  </div>
                </div>
                {formatControls(
                  prefs.format,
                  prefs.bitrate,
                  (v) => setPrefs({ ...prefs, format: v }),
                  (v) => setPrefs({ ...prefs, bitrate: v }),
                )}
                <p className="settings-note">
                  Audio is matched from YouTube. Higher encoding bitrates and FLAC conversion cannot
                  improve source quality. Artwork and track metadata are embedded by spotDL.
                </p>
                <button
                  className="primary"
                  disabled={busy === 'settings'}
                  onClick={async () => {
                    setBusy('settings')
                    try {
                      const result = await api<Preferences>('/preferences', {
                        method: 'PUT',
                        body: JSON.stringify(prefs),
                      })
                      setFormat(result.format)
                      setBitrate(result.bitrate)
                      setToast('Download defaults saved')
                    } catch (e) {
                      setToast((e as Error).message)
                    } finally {
                      setBusy(null)
                    }
                  }}
                >
                  <Check size={16} /> Save defaults
                </button>
              </section>
              <section className="panel">
                <div className="section-title">
                  <Sun size={21} />
                  <div>
                    <h2>Appearance</h2>
                    <p>Set the mood for your workspace.</p>
                  </div>
                </div>
                <div className="theme-options">
                  {(['dark', 'light'] as const).map((value) => (
                    <button
                      className={theme === value ? 'chosen' : ''}
                      onClick={() => setTheme(value)}
                      key={value}
                    >
                      {value === 'dark' ? <Moon size={20} /> : <Sun size={20} />}
                      <span>{value === 'dark' ? 'After hours' : 'Daylight'}</span>
                      {theme === value && <Check size={16} />}
                    </button>
                  ))}
                </div>
              </section>
              <section className="panel engine-panel">
                <div className="section-title">
                  <AudioLines size={21} />
                  <div>
                    <h2>Under the hood</h2>
                    <p>Your local download engine.</p>
                  </div>
                </div>
                {[
                  ['spotDL', health ? `v${health.spotdl}` : 'Connecting…'],
                  ['FFmpeg', health?.ffmpeg ? 'Available' : 'Unavailable'],
                  ['JavaScript runtime', health?.javascript_runtime ? 'Available' : 'Unavailable'],
                  [
                    'Spotify API mode',
                    health?.spotify_credentials ? 'Your credentials' : 'spotDL default',
                  ],
                  ['YouTube cookies', health?.cookies ? 'Configured' : 'Not configured'],
                ].map(([label, value]) => (
                  <div className="engine-row" key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
                <p className="settings-note">
                  Optional Spotify credentials and YouTube cookies are configured in the server’s
                  .env file. Restart the server after changing them.
                </p>
              </section>
            </div>
          )}

          <footer>
            <span>
              <AudioLines size={14} /> A little less online. A little more in tune.
            </span>
            <a href="https://github.com/spotdl/spotify-downloader" target="_blank" rel="noreferrer">
              Built with spotDL <ExternalLink size={12} />
            </a>
          </footer>
        </main>
      </div>
      {playing && (
        <div className="player">
          <Cover src={playing.job.tracks[playing.index].song.cover_url} />
          <div className="track-info">
            <strong>{playing.job.tracks[playing.index].song.name}</strong>
            <small>{playing.job.tracks[playing.index].song.artists.join(', ')}</small>
          </div>
          <audio
            key={`${playing.job.id}-${playing.index}`}
            controls
            autoPlay
            src={`/api/jobs/${playing.job.id}/tracks/${playing.index}/file?inline=true`}
            onError={() =>
              setToast(
                'This browser could not play the file. Download it to listen in your music player.',
              )
            }
          />
          <button className="icon-button" title="Close player" onClick={() => setPlaying(null)}>
            <X size={18} />
          </button>
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          <AudioLines size={17} />
          {toast}
          <button className="icon-button" title="Dismiss notification" onClick={() => setToast('')}>
            <X size={15} />
          </button>
        </div>
      )}
      {(deleteJob || help) && (
        <div
          className="modal-backdrop"
          onClick={() => {
            if (!busy) {
              setDeleteJob(null)
              setHelp(false)
            }
          }}
        >
          <section
            ref={dialog}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={deleteJob ? 'Delete download' : 'How Side A works'}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              title="Close dialog"
              onClick={() => {
                setDeleteJob(null)
                setHelp(false)
              }}
            >
              <X size={19} />
            </button>
            {deleteJob ? (
              <>
                <Trash2 size={28} />
                <h2>Clear this from your collection?</h2>
                <p>
                  “{deleteJob.title}” and its downloaded audio files will be permanently deleted
                  from this workspace.
                </p>
                <div className="modal-actions">
                  <button className="small-button" onClick={() => setDeleteJob(null)}>
                    Keep download
                  </button>
                  <button
                    className="danger-button"
                    disabled={!!busy}
                    onClick={() => void action(deleteJob, 'delete')}
                  >
                    Delete download & files
                  </button>
                </div>
              </>
            ) : (
              <>
                <Disc3 size={32} />
                <h2>Your music, unplugged.</h2>
                <div className="how-step">
                  <span>01</span>
                  <div>
                    <strong>Bring a Spotify link</strong>
                    <p>
                      Copy the link to a public song, album or playlist from Spotify’s Share menu.
                    </p>
                  </div>
                </div>
                <div className="how-step">
                  <span>02</span>
                  <div>
                    <strong>Make it your collection</strong>
                    <p>Preview the track list, choose what to keep, and pick an audio format.</p>
                  </div>
                </div>
                <div className="how-step">
                  <span>03</span>
                  <div>
                    <strong>Take it with you</strong>
                    <p>
                      spotDL matches the audio on YouTube and adds Spotify metadata. Play it here,
                      save individual files, or download a ZIP.
                    </p>
                  </div>
                </div>
                <p className="settings-note">
                  Use downloads for content you own or have permission to download. This app is
                  independent of Spotify.
                </p>
                <button className="primary" onClick={() => setHelp(false)}>
                  Sounds good <ArrowRight size={16} />
                </button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
