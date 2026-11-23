import { test, expect, type Page } from '@playwright/test'

const song = {
  name: 'First track',
  artists: ['Local artist'],
  album_name: 'Test album',
  duration: 165,
  url: 'https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT',
}
const preview = {
  id: 'preview-1',
  title: 'My playlist',
  url: 'https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M',
  kind: 'playlist',
  songs: [song, { ...song, name: 'Second track' }],
}
const job = {
  id: 'job-1',
  title: 'My playlist',
  kind: 'playlist',
  url: preview.url,
  format: 'mp3',
  bitrate: 'auto',
  status: 'completed',
  created_at: '2026-11-23T10:00:00Z',
  tracks: [
    { song, status: 'completed', progress: 100, message: 'Ready', file: true, size: 1024000 },
  ],
}

async function mock(page: Page, withJob = false) {
  let jobs: unknown[] = withJob ? [job] : []
  let preferences = { format: 'mp3', bitrate: 'auto' }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    let data: unknown = {}
    if (path === '/api/jobs' && request.method() === 'POST') {
      const body = request.postDataJSON()
      expect(body.indices).toEqual([0])
      jobs = [job]
      data = job
    } else if (path === '/api/jobs') data = jobs
    else if (path === '/api/health')
      data = { status: 'ok', spotdl: '4.6.0', ffmpeg: true, javascript_runtime: true }
    else if (path === '/api/preview') data = preview
    else if (path === '/api/preferences') {
      if (request.method() === 'PUT') preferences = request.postDataJSON()
      data = preferences
    } else if (path.endsWith('/zip')) {
      await route.fulfill({
        body: 'test archive',
        headers: {
          'Content-Disposition': 'attachment; filename="My playlist.zip"',
          'Content-Type': 'application/zip',
        },
      })
      return
    } else if (request.method() === 'DELETE') {
      jobs = []
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({ json: data })
  })
}

test('selects playlist tracks, queues a download and opens the library', async ({ page }) => {
  await mock(page)
  await page.goto('/')
  await page.getByRole('textbox', { name: 'Spotify link' }).fill(preview.url)
  await page.getByRole('button', { name: 'Preview link' }).click()
  await expect(page.getByRole('heading', { name: 'My playlist' })).toBeVisible()
  await page.getByRole('checkbox', { name: 'Select Second track' }).uncheck()
  await page.getByRole('button', { name: 'Download 1 track', exact: true }).click()
  await expect(page.getByText('Added to your download queue')).toBeVisible()
  await page.getByRole('button', { name: 'Library', exact: true }).click()
  await expect(page.getByText('First track', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: 'Search library' }).fill('absent')
  await expect(page.getByRole('heading', { name: 'No tracks found' })).toBeVisible()
})

test('downloads a ZIP in dark mode and confirms file deletion', async ({ page }) => {
  await mock(page, true)
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const download = page.waitForEvent('download')
  await page.getByTitle('Download ZIP').click()
  expect((await download).suggestedFilename()).toBe('My playlist.zip')
  await page.getByTitle('Delete My playlist').click()
  await page.getByRole('button', { name: 'Keep download' }).click()
  await expect(page.getByText('My playlist', { exact: true })).toBeVisible()
  await page.getByTitle('Delete My playlist').click()
  await page.getByRole('button', { name: 'Delete download & files' }).click()
  await expect(
    page.getByRole('heading', { name: 'Your next favorite is one link away' }),
  ).toBeVisible()
})

test('persists theme and saves download defaults', async ({ page }) => {
  await mock(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await page.getByRole('button', { name: 'Daylight' }).click()
  await page.getByLabel('Audio format').selectOption('opus')
  await page.getByRole('button', { name: 'Save defaults' }).click()
  await expect(page.getByText('Download defaults saved')).toBeVisible()
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(page.getByLabel('Audio format')).toHaveValue('opus')
})

test('fits a mobile viewport and presents preview errors', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mock(page)
  await page.route('**/api/preview', (route) =>
    route.fulfill({ status: 502, json: { detail: 'Spotify is unavailable. Try again.' } }),
  )
  await page.goto('/')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('textbox', { name: 'Spotify link' }).fill(preview.url)
  await page.getByRole('button', { name: 'Preview link' }).click()
  await expect(page.getByRole('alert')).toContainText('Spotify is unavailable')
  await page.getByRole('button', { name: 'Library', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'A collection with your name on it' }),
  ).toBeVisible()
})
