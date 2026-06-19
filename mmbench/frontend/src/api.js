const BASE = '/api'
async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.json()
}
export const fetchLeaderboard = () => get('/leaderboard')
export const fetchSessions = () => get('/sessions')
export const fetchCaseBreakdown = () => get('/case-breakdown')
export const fetchCell = (a, p) => get(`/cell?assistant=${encodeURIComponent(a)}&profile=${encodeURIComponent(p)}`)
export const fetchSession = (id) => get(`/session/${encodeURIComponent(id)}`)
