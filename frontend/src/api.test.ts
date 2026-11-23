import { describe, expect, it, vi, afterEach } from 'vitest'
import { api, bytes, duration } from './api'
afterEach(() => vi.unstubAllGlobals())
describe('API error handling', () => {
  it('presents FastAPI validation errors as readable messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 422,
          json: async () => ({ detail: [{ msg: 'Paste a Spotify link.' }] }),
        }),
    )
    await expect(api('/preview')).rejects.toThrow('Paste a Spotify link.')
  })
  it('handles a deleted download without reading an empty body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 204 }))
    await expect(api('/jobs/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })
  it('handles non-JSON proxy failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('Invalid JSON')
        },
      }),
    )
    await expect(api('/health')).rejects.toThrow('Request failed (502)')
  })
})
describe('library metadata', () => {
  it('formats full minutes and remaining seconds', () => expect(duration(185)).toBe('3:05'))
  it('shows actual stored bytes in megabytes and gigabytes', () => {
    expect(bytes(1024 ** 2 * 3.4)).toBe('3.4 MB')
    expect(bytes(1024 ** 3 * 1.2)).toBe('1.2 GB')
  })
})
