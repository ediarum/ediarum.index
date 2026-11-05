import type { MountContext } from '@/platform/contract'
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

/** Where the platform's auth provider hands out a fresh `XSRF-TOKEN` cookie. */
export const CSRF_COOKIE_URL = '/api/auth/csrf-cookie'

export interface Http extends AxiosInstance {
  /** Abort every request in flight and refuse new ones — called on unmount. */
  dispose: () => void
}

/**
 * The backend client of one mount: requests go to `ctx.apiBase`, same-origin, so
 * the platform's session cookie authenticates them. axios sends the `XSRF-TOKEN`
 * cookie as `X-XSRF-TOKEN` on same-origin writes by itself.
 *
 * - 401: `ctx.onUnauthorized()` once — the platform shows its login and remounts.
 * - 419 (CSRF token missing or expired): fetch a fresh cookie, retry once.
 * - Every request carries the mount's `AbortSignal`; `dispose()` aborts them.
 */
export function createHttp(ctx: Pick<MountContext, 'apiBase' | 'onUnauthorized'>): Http {
  const controller = new AbortController()
  const http = axios.create({ baseURL: `${ctx.apiBase}/`, signal: controller.signal }) as Http
  let unauthorized = false

  http.interceptors.response.use(undefined, async (error) => {
    const status = error.response?.status
    const config = error.config as (InternalAxiosRequestConfig & { _csrfRetried?: boolean }) | undefined
    if (status === 419 && config && !config._csrfRetried) {
      config._csrfRetried = true
      await axios.get(CSRF_COOKIE_URL, { signal: controller.signal })
      return http.request(config)
    }
    if (status === 401 && !unauthorized) {
      unauthorized = true
      ctx.onUnauthorized()
    }
    throw error
  })

  http.dispose = () => controller.abort()
  return http
}
