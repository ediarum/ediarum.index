import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'
import { apiError } from './error'

function axiosErr(status: number, data: unknown) {
  return new AxiosError('req failed', 'ERR', undefined, undefined, {
    status,
    data,
  } as never)
}

describe('apiError', () => {
  it('returns a FastAPI `detail` string verbatim', () => {
    expect(apiError(axiosErr(409, { detail: "project 'dup' already exists" }))).toBe(
      "project 'dup' already exists",
    )
  })

  it('returns the first message of a pydantic 422 `detail` array', () => {
    expect(
      apiError(axiosErr(422, { detail: [{ msg: 'String should match pattern', loc: ['body', 'name'] }] })),
    ).toBe('String should match pattern')
  })

  it('falls back for non-axios errors', () => {
    expect(apiError(new Error('boom'), 'fallback')).toBe('fallback')
  })
})
