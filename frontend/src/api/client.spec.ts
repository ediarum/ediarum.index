import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHttp, CSRF_COOKIE_URL } from './client'

/** An adapter answering each request with the next status of `statuses`. */
function answering(...statuses: number[]) {
  const seen: InternalAxiosRequestConfig[] = []
  const adapter: AxiosAdapter = async (config) => {
    seen.push(config)
    const status = statuses.shift() ?? 200
    const response = { data: { status }, status, statusText: '', headers: {}, config } as AxiosResponse
    if (status >= 400) {
      throw new axios.AxiosError('failed', String(status), config, undefined, response)
    }
    return response
  }
  return { adapter, seen }
}

function http(onUnauthorized = vi.fn()) {
  return { client: createHttp({ apiBase: '/api/index', onUnauthorized }), onUnauthorized }
}

afterEach(() => vi.restoreAllMocks())

describe('createHttp', () => {
  it('sends requests to the app backend under ctx.apiBase', async () => {
    const { client } = http()
    const { adapter, seen } = answering(200)
    client.defaults.adapter = adapter
    await client.get('mop/entries')
    expect(`${seen[0]!.baseURL}${seen[0]!.url}`).toBe('/api/index/mop/entries')
  })

  it('calls onUnauthorized once on 401, however many requests fail', async () => {
    const { client, onUnauthorized } = http()
    client.defaults.adapter = answering(401, 401).adapter
    await expect(client.get('projects')).rejects.toThrow()
    await expect(client.get('entry-types')).rejects.toThrow()
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('refreshes the CSRF cookie and retries once on 419', async () => {
    const csrf = vi.spyOn(axios, 'get').mockResolvedValue({ status: 204 })
    const { client } = http()
    const { adapter, seen } = answering(419, 201)
    client.defaults.adapter = adapter
    const res = await client.post('mop/comments', { entry_id: 1, text: 'x' })
    expect(res.status).toBe(201)
    expect(csrf).toHaveBeenCalledWith(CSRF_COOKIE_URL, expect.anything())
    expect(seen).toHaveLength(2)
  })

  it('gives up after a second 419', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ status: 204 })
    const { client } = http()
    const { adapter, seen } = answering(419, 419)
    client.defaults.adapter = adapter
    await expect(client.post('mop/comments', {})).rejects.toThrow()
    expect(seen).toHaveLength(2)
  })

  it('aborts every request once disposed', async () => {
    const { client } = http()
    client.dispose()
    await expect(client.get('projects')).rejects.toThrow(/cancel/i)
  })
})
