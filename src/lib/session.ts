// CSRF proof lives only in memory. Authentication stays in an HttpOnly cookie.
let csrf = ''
let userId = ''
let generation = 0
let redirecting = false
export function setBrowserSession(id: string, token: string) {
  if (id !== userId) generation++
  userId = id; csrf = token
  localStorage.removeItem('access_token')
  localStorage.removeItem('user')
}
export function clearBrowserSession() { userId = ''; csrf = ''; generation++ }
export function getCsrfToken() { return csrf }
export function getSessionGeneration() { return generation }
export function redirectToLogin() {
  if (redirecting) return
  redirecting = true
  clearBrowserSession()
  window.location.assign('/login')
}
