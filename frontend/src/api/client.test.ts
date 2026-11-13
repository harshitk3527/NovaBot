import { describe, expect, it } from 'vitest'
import { ApiError } from './types'
describe('ApiError', () => { it('keeps status and backend code', () => { const error = new ApiError(429, 'limited', 'request_error'); expect(error.status).toBe(429); expect(error.code).toBe('request_error') }) })
