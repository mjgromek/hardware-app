// Every request the app makes, in one place. Same origin (ADR-0001), so nothing
// here handles tokens. Any request can be the one that discovers the session is
// gone; `onUnauthorized` turns that into the login screen once, for all of them.

let onUnauthorized = () => {}

export function handleUnauthorized(handler) {
  onUnauthorized = handler
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request(method, path, body, { ownsUnauthorized = false } = {}) {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  // A 401 from a data route means the session is gone; from the login route it
  // means the credential was wrong — two meanings that must not share a message.
  if (response.status === 401 && !ownsUnauthorized) {
    onUnauthorized()
    throw new ApiError(401, 'Your session has ended. Sign in again.')
  }

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    // FastAPI puts the readable reason in `detail` — including the 409 a guard
    // raises, which is written to be shown to whoever tried (CONTEXT.md).
    throw new ApiError(response.status, detailOf(payload) || `Request failed (${response.status})`)
  }

  return payload
}

// A 422 from FastAPI is a list of field errors, not a sentence. Flatten it to
// something a person can act on rather than printing `[object Object]`.
function detailOf(payload) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = item.loc?.filter((part) => part !== 'body').join('.')
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .join('; ')
  }
  return null
}

export const api = {
  session: () => request('GET', '/api/session'),
  // `ownsUnauthorized`: a refused login is this call's own result, not a lost session.
  logIn: (email, password) =>
    request('POST', '/api/login', { email, password }, { ownsUnauthorized: true }),

  hardware: ({ status, sort, heldBy } = {}) => {
    const query = new URLSearchParams()
    if (status) query.set('status', status)
    if (sort) query.set('sort', sort)
    if (heldBy) query.set('held_by', heldBy)
    const suffix = query.toString()
    return request('GET', suffix ? `/api/hardware?${suffix}` : '/api/hardware')
  },
  addHardware: (item) => request('POST', '/api/hardware', item),
  setHardwareStatus: (id, status) => request('PATCH', `/api/hardware/${id}`, { status }),
  deleteHardware: (id) => request('DELETE', `/api/hardware/${id}`),

  rent: (id) => request('POST', `/api/hardware/${id}/rent`),
  //: `issue` omitted entirely for a clean return, rather than sent as null — the server
  //: treats a present-but-blank issue as a refusal, and an absent one as "all good".
  returnItem: (id, issue = null) =>
    request('POST', `/api/hardware/${id}/return`, issue ? { issue } : {}),
  forceReturn: (id, reason) => request('POST', `/api/hardware/${id}/force-return`, { reason }),
  // The release carries the change it certifies (ADR-0017): one request, one audit
  // row. `edits` holds only the fields the admin actually changed.
  clearReview: (id, reason, edits = {}, outcome = 'released') =>
    request('POST', `/api/hardware/${id}/clear-review`, { reason, outcome, ...edits }),
  editHardware: (id, edits) => request('PATCH', `/api/hardware/${id}`, edits),
  flagReview: (id, reason) => request('POST', `/api/hardware/${id}/flag-review`, { reason }),

  // The filter object is the model's output and never crosses this boundary (ADR-0015).
  search: (query) => request('POST', '/api/search', { query }),
  runAudit: () => request('GET', '/api/admin/audit'),

  users: () => request('GET', '/api/users'),
  addUser: (account) => request('POST', '/api/users', account),
  setRole: (id, role) => request('PATCH', `/api/users/${id}`, { role }),
  deleteUser: (id) => request('DELETE', `/api/users/${id}`),
}
