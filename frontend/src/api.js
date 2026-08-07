// Every request the app makes, in one place.
//
// Same origin (ADR-0001): no host, no CORS, no configuration to get wrong. The
// session cookie rides along because it is a cookie on this origin, so nothing here
// handles tokens.
//
// The 401 contract (ADR-0006): every data route refuses a caller without a session,
// so any request can be the one that discovers the session is gone. `onUnauthorized`
// is called for all of them, and the app turns that into the login screen rather than
// each caller writing its own redirect.

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

  // A 401 means two different things and they must not share a message. From a data
  // route it means the session is gone, and the app returns to the login screen. From
  // the login route itself it means the credential was wrong — the caller is already
  // on the login screen, and telling them their session ended when they simply
  // mistyped a password sends them looking for a problem that does not exist.
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
  returnItem: (id) => request('POST', `/api/hardware/${id}/return`),
  forceReturn: (id, reason) => request('POST', `/api/hardware/${id}/force-return`, { reason }),
  // The release carries the change it certifies (ADR-0017 as amended): one request,
  // one transaction, one audit row. `edits` holds only the fields the admin actually
  // changed — sending an unchanged field would look like a deliberate rewrite in the
  // trail, and sending them all would blank anything the form did not know about.
  clearReview: (id, reason, edits = {}, outcome = 'released') =>
    request('POST', `/api/hardware/${id}/clear-review`, { reason, outcome, ...edits }),
  editHardware: (id, edits) => request('PATCH', `/api/hardware/${id}`, edits),
  flagReview: (id, reason) => request('POST', `/api/hardware/${id}/flag-review`, { reason }),

  // The query is the caller's input; the filter object is the model's output and
  // never crosses this boundary (ADR-0015). `mode` says which path answered — the
  // UI shows it rather than hiding the fallback (ADR-0016).
  search: (query) => request('POST', '/api/search', { query }),
  runAudit: () => request('GET', '/api/admin/audit'),

  users: () => request('GET', '/api/users'),
  addUser: (account) => request('POST', '/api/users', account),
  setRole: (id, role) => request('PATCH', `/api/users/${id}`, { role }),
  deleteUser: (id) => request('DELETE', `/api/users/${id}`),
}
