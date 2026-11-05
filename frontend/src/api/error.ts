import axios from 'axios'

/** Human-readable message from an axios error, understanding FastAPI's
 *  `{detail: "..."}` and pydantic's `{detail: [{msg, loc}, ...]}`. */
export function apiError(e: unknown, fallback = 'Request failed.'): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  }
  return fallback
}
