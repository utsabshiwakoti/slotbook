// Thin fetch wrapper: adds the token, turns FastAPI error bodies into readable messages.
const TOKEN_KEY = 'slotbook.token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token) =>
  token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY)

function errorMessage(data, status) {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  // Pydantic validation errors: a list of {loc, msg}. Show the field and the message.
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = d.loc?.filter((p) => p !== 'body').join(' ')
        const msg = d.msg.replace(/^Value error, /, '')
        return field ? `${field}: ${msg}` : msg
      })
      .join('; ')
  }
  return `Something went wrong (${status}). Please try again.`
}

export async function api(path, { method = 'GET', body, form, params } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (form) payload = new URLSearchParams(form)
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const query = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    : ''
  const res = await fetch(`/api${path}${query}`, { method, headers, body: payload })
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const error = new Error(errorMessage(data, res.status))
    error.status = res.status
    throw error
  }
  return data
}
