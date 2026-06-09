const BASE = ''  // proxy via vite to http://localhost:8000

export async function loadExample() {
  const r = await fetch(`${BASE}/api/example-formats`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function getShelves(fileId, { seg, mue, pg, tam, dir }) {
  const r = await fetch(`${BASE}/api/shelves`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: fileId, seg, mue, pg, tam, dir }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function startOptimize(params) {
  const r = await fetch(`${BASE}/api/optimize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

// Returns an EventSource connected to the SSE progress stream
export function openProgressStream(taskId, onMessage, onError) {
  const es = new EventSource(`${BASE}/api/progress/${taskId}`)
  es.onmessage = (e) => onMessage(JSON.parse(e.data))
  es.onerror   = (e) => { es.close(); onError(e) }
  return es
}

export function csvDownloadUrl(taskId) {
  return `${BASE}/api/result/${taskId}/csv`
}
export function diagCsvDownloadUrl(taskId) {
  return `${BASE}/api/result/${taskId}/diag-csv`
}
