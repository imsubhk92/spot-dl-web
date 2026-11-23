export type Song = {
  name: string
  artists: string[]
  album_name: string
  duration: number
  cover_url?: string
  url: string
  [key: string]: unknown
}
export type Preview = {
  id: string
  title: string
  kind: string
  url: string
  cover_url?: string
  songs: Song[]
}
export type Track = {
  song: Song
  status: string
  progress: number
  message: string
  file: boolean
  size: number
  error?: string
}
export type Job = {
  id: string
  title: string
  url: string
  kind: string
  status: string
  created_at: string
  format: string
  bitrate: string
  tracks: Track[]
  error?: string
  cover_url?: string
}
export type Preferences = { format: string; bitrate: string }
export type Health = {
  status: string
  spotdl: string
  ffmpeg: boolean
  javascript_runtime: boolean
  spotify_credentials: boolean
  cookies: boolean
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const detail = data.detail
    throw new Error(
      Array.isArray(detail)
        ? detail.map((e: { msg: string }) => e.msg).join(' ')
        : detail || `Request failed (${response.status})`,
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
export const active = (job: Job) => ['queued', 'downloading'].includes(job.status)
export const duration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
export const bytes = (size: number) =>
  size >= 1024 ** 3 ? `${(size / 1024 ** 3).toFixed(1)} GB` : `${(size / 1024 ** 2).toFixed(1)} MB`
