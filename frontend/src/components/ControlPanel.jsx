import { useRef, useState } from 'react'
import { loadExample, uploadFile, getShelves, startOptimize, openProgressStream } from '../api/client'

function Slider({ label, name, min, max, step, value, onChange, hint }) {
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <label className="label">{label}</label>
        <span className="text-xs font-mono font-bold text-oxxo-red">{value}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(name, step < 1 ? parseFloat(e.target.value) : parseInt(e.target.value))}
        className="w-full accent-oxxo-red"
      />
      {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
    </div>
  )
}

function NumberInput({ label, name, min, max, value, onChange }) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type="number" min={min} max={max} value={value}
        onChange={e => {
          const v = parseInt(e.target.value)
          if (!isNaN(v)) onChange(name, Math.max(min, Math.min(max, v)))
        }}
        className="input-field"
      />
    </div>
  )
}

export default function ControlPanel({ onResult, onProgress }) {
  const fileRef = useRef(null)

  const [fileId, setFileId]     = useState(null)
  const [filename, setFilename] = useState('')
  const [formats, setFormats]   = useState([])
  const [selFmt, setSelFmt]     = useState(null)
  const [fmtSearch, setFmtSearch] = useState('')
  const [shelves, setShelves]   = useState([])
  const [maxFeasible, setMaxFeasible] = useState(null)
  const [loading, setLoading]   = useState(false)
  const [running, setRunning]   = useState(false)
  const [error, setError]       = useState('')

  const [params, setParams] = useState({
    alpha: 0.1, max_iter: 20, local_rounds: 20, seed: 42,
    lambda_hist: 3.0, beta_vis: 0.10,
    min_frentes: 1, max_frentes: 4,
    max_variedad: '',
  })

  function setP(k, v) { setParams(p => ({ ...p, [k]: v })) }

  // ── File handling ──────────────────────────────────────────────────────────

  async function handleExample() {
    setError(''); setLoading(true)
    try {
      const data = await loadExample()
      setFileId(data.file_id); setFilename(data.filename)
      setFormats(data.formats); setSelFmt(data.formats[0] || null)
      if (data.formats[0]) await fetchShelves(data.file_id, data.formats[0])
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0]; if (!file) return
    setError(''); setLoading(true)
    try {
      const data = await uploadFile(file)
      setFileId(data.file_id); setFilename(data.filename)
      setFormats(data.formats); setSelFmt(data.formats[0] || null)
      if (data.formats[0]) await fetchShelves(data.file_id, data.formats[0])
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  async function fetchShelves(fid, fmt) {
    try {
      const data = await getShelves(fid, { seg: fmt.seg, mue: fmt.mue, pg: fmt.pg, tam: fmt.tam, dir: fmt.dir })
      setShelves(data.shelves || [])
      if (data.max_feasible_frentes != null) {
        setMaxFeasible(data.max_feasible_frentes)
        setParams(p => ({ ...p, max_frentes: data.max_feasible_frentes }))
      }
    } catch { setShelves([]) }
  }

  async function handleFormatChange(e) {
    const fmt = formats.find(f => f.key === e.target.value)
    setSelFmt(fmt || null)
    if (fmt && fileId) await fetchShelves(fileId, fmt)
  }

  function updateShelf(idx, field, val) {
    setShelves(prev => prev.map((s, i) => i === idx ? { ...s, [field]: val } : s))
  }

  function addShelf() {
    const maxChar = shelves.reduce((m, s) => Math.max(m, s.CHAROLA), 0)
    const ref = shelves[0] || {}
    setShelves(prev => [...prev, {
      CHAROLA:  maxChar + 1,
      Ancho_cm: ref.Ancho_cm ?? 55,
      Alto_cm:  ref.Alto_cm  ?? 30,
      X:        ref.X        ?? 0,
      Y:        ref.Y        ?? 0,
    }])
  }

  function removeShelf(idx) {
    setShelves(prev => prev.filter((_, i) => i !== idx))
  }

  function addDoor() {
    if (shelves.length === 0) return
    // Agrupar por X para identificar puertas
    const xValues = [...new Set(shelves.map(s => s.X ?? 0))].sort((a, b) => a - b)
    const lastX   = xValues[xValues.length - 1]
    const doorShelves = shelves.filter(s => (s.X ?? 0) === lastX)
    const doorWidth   = doorShelves[0]?.Ancho_cm ?? 55
    const newX        = lastX + doorWidth
    let maxChar       = shelves.reduce((m, s) => Math.max(m, s.CHAROLA), 0)
    const newRows     = doorShelves.map(s => ({
      ...s,
      CHAROLA: ++maxChar,
      X: newX,
    }))
    setShelves(prev => [...prev, ...newRows])
  }

  function removeDoor() {
    if (shelves.length === 0) return
    const xValues = [...new Set(shelves.map(s => s.X ?? 0))].sort((a, b) => a - b)
    if (xValues.length <= 1) return   // no eliminar la última puerta
    const lastX = xValues[xValues.length - 1]
    setShelves(prev => prev.filter(s => (s.X ?? 0) !== lastX))
  }

  // ── Run ────────────────────────────────────────────────────────────────────

  async function handleRun() {
    if (!fileId || !selFmt) return
    setError(''); setRunning(true); onResult(null); onProgress(null)

    const overrides = shelves.map(s => ({
      CHAROLA:  s.CHAROLA,
      Ancho_cm: s.Ancho_cm,
      Alto_cm:  s.Alto_cm,
      X:        s.X  ?? 0,
      Y:        s.Y  ?? 0,
    }))

    try {
      const { task_id } = await startOptimize({
        file_id: fileId,
        seg: selFmt.seg, mue: selFmt.mue, pg: selFmt.pg,
        tam: selFmt.tam, dir: selFmt.dir,
        alpha:       params.alpha,
        max_iter:    params.max_iter,
        local_rounds: params.local_rounds,
        seed:        params.seed,
        lambda_hist: params.lambda_hist,
        beta_vis:    params.beta_vis,
        min_frentes: params.min_frentes,
        max_frentes: params.max_frentes,
        max_variedad: params.max_variedad ? parseInt(params.max_variedad) : null,
        shelf_overrides: overrides,
      })

      const es = openProgressStream(
        task_id,
        (msg) => {
          onProgress(prev => ({ ...(prev || {}), taskId: task_id, latest: msg }))
          if (msg.type === 'done') {
            es.close(); setRunning(false)
            onResult(msg.result)
          }
          if (msg.type === 'error') {
            es.close(); setRunning(false)
            setError(msg.text)
          }
          if (msg.type === 'infeasible') {
            es.close(); setRunning(false)
            setError(msg.text)
            // Auto-update the slider to the suggested value
            if (msg.max_frentes_sugerido != null) {
              setMaxFeasible(msg.max_frentes_sugerido)
              setParams(p => ({ ...p, max_frentes: msg.max_frentes_sugerido }))
            }
          }
        },
        () => { setRunning(false); setError('Conexión perdida.') }
      )
    } catch (e) {
      setError(e.message); setRunning(false)
    }
  }

  return (
    <aside className="w-80 shrink-0 flex flex-col gap-3">

      {/* ── Archivo ─────────────────────────────────────── */}
      <div className="card p-4">
        <p className="section-title">1. Datos de entrada</p>

        {filename ? (
          <div className="flex items-center gap-2 mb-2 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
            <span className="text-green-600 text-sm">✓</span>
            <span className="text-xs font-medium text-green-700 truncate">{filename}</span>
            <button onClick={() => { setFileId(null); setFilename(''); setFormats([]); setShelves([]) }}
              className="ml-auto text-gray-400 hover:text-gray-600 text-sm">✕</button>
          </div>
        ) : null}

        <div className="flex gap-2">
          <button onClick={() => fileRef.current?.click()} className="btn-secondary flex-1 text-center">
            📂 Subir archivo
          </button>
          <button onClick={handleExample} className="btn-secondary flex-1 text-center" disabled={loading}>
            📋 Ejemplo
          </button>
        </div>
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFileChange} className="hidden" />
        {loading && <p className="text-xs text-gray-400 mt-1 text-center">Cargando…</p>}
      </div>

      {/* ── Formato ─────────────────────────────────────── */}
      {formats.length > 0 && (
        <div className="card p-4">
          <p className="section-title">2. Formato</p>

          <div className="relative mb-2">
            <input
              type="text"
              placeholder="Buscar por segmento, tamaño, dirección…"
              value={fmtSearch}
              onChange={e => setFmtSearch(e.target.value)}
              className="input-field pr-7 text-xs"
            />
            {fmtSearch && (
              <button
                onClick={() => setFmtSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >✕</button>
            )}
          </div>

          {(() => {
            const q = fmtSearch.toLowerCase()
            const filtered = formats.filter(f => !q || f.label.toLowerCase().includes(q))
            return (
              <>
                <p className="text-xs text-gray-400 mb-1">{filtered.length} de {formats.length} formatos</p>
                <div className="overflow-auto max-h-48 flex flex-col gap-0.5">
                  {filtered.length === 0
                    ? <p className="text-xs text-gray-400 py-2 text-center">Sin resultados</p>
                    : filtered.map(f => (
                      <button
                        key={f.key}
                        onClick={() => { setSelFmt(f); if (fileId) fetchShelves(fileId, f) }}
                        title={f.label}
                        className={`w-full text-left text-xs px-2 py-1.5 rounded-lg transition-colors ${
                          selFmt?.key === f.key
                            ? 'bg-oxxo-red text-white font-semibold'
                            : 'hover:bg-gray-100 text-gray-700'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-bold truncate min-w-0">
                            {f.seg} · {f.mue} · {f.pg} · T={f.tam} · {f.dir}
                          </span>
                          <span className={`shrink-0 text-xs ${selFmt?.key === f.key ? 'text-red-100' : 'text-gray-400'}`}>
                            {f.n}p
                          </span>
                        </div>
                      </button>
                    ))
                  }
                </div>
              </>
            )
          })()}
        </div>
      )}

      {/* ── Dimensiones del mueble ───────────────────────── */}
      {shelves.length > 0 && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-1">
            <p className="section-title mb-0">3. Dimensiones del mueble</p>
            <div className="flex gap-1">
              <button onClick={addShelf}
                className="text-xs px-2 py-0.5 bg-green-50 text-green-700 border border-green-300 rounded-lg hover:bg-green-100 font-bold"
                title="Agregar charola suelta">+ Charola</button>
              <button onClick={addDoor}
                className="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-300 rounded-lg hover:bg-blue-100 font-bold"
                title="Duplicar última puerta">+ Puerta</button>
              <button onClick={removeDoor}
                disabled={[...new Set(shelves.map(s => s.X ?? 0))].length <= 1}
                className="text-xs px-2 py-0.5 bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 font-bold disabled:opacity-30"
                title="Eliminar última puerta">− Puerta</button>
            </div>
          </div>
          <p className="text-xs text-gray-400 mb-2">
            {[...new Set(shelves.map(s => s.X ?? 0))].length} puertas · {shelves.length} charolas
          </p>
          <div className="overflow-auto max-h-52 text-xs">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-gray-50">
                  <th className="border border-gray-200 px-1 py-1 text-left font-semibold text-gray-500">Ch.</th>
                  <th className="border border-gray-200 px-1 py-1 font-semibold text-gray-500">Ancho</th>
                  <th className="border border-gray-200 px-1 py-1 font-semibold text-gray-500">Alto</th>
                  <th className="border border-gray-200 px-1 py-1 font-semibold text-gray-500">Y</th>
                  <th className="border border-gray-200 px-1 py-1"></th>
                </tr>
              </thead>
              <tbody>
                {shelves.map((s, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="border border-gray-200 px-2 py-1 text-gray-500 font-mono">{s.CHAROLA}</td>
                    <td className="border border-gray-200 p-0.5">
                      <input type="number" min="10" max="500" step="0.5"
                        value={s.Ancho_cm}
                        onChange={e => updateShelf(i, 'Ancho_cm', parseFloat(e.target.value) || 55)}
                        className="w-full border-0 text-center focus:ring-1 focus:ring-oxxo-red/40 rounded text-xs py-0.5" />
                    </td>
                    <td className="border border-gray-200 p-0.5">
                      <input type="number" min="5" max="100" step="0.5"
                        value={s.Alto_cm}
                        onChange={e => updateShelf(i, 'Alto_cm', parseFloat(e.target.value) || 30)}
                        className="w-full border-0 text-center focus:ring-1 focus:ring-oxxo-red/40 rounded text-xs py-0.5" />
                    </td>
                    <td className="border border-gray-200 p-0.5">
                      <input type="number" min="0" max="999" step="1"
                        value={s.Y ?? 0}
                        onChange={e => updateShelf(i, 'Y', parseFloat(e.target.value) || 0)}
                        className="w-full border-0 text-center focus:ring-1 focus:ring-oxxo-red/40 rounded text-xs py-0.5" />
                    </td>
                    <td className="border border-gray-200 px-1 py-1 text-center">
                      <button
                        onClick={() => removeShelf(i)}
                        className="text-red-400 hover:text-red-600 font-bold text-sm leading-none"
                        title="Eliminar charola"
                      >×</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {shelves.length === 0 && (
            <p className="text-xs text-amber-600 mt-1">Sin charolas — agrega al menos una.</p>
          )}
        </div>
      )}

      {/* ── Parámetros GRASP ─────────────────────────────── */}
      <div className="card p-4">
        <p className="section-title">4. Parámetros GRASP</p>

        {/* Presets */}
        <div className="flex gap-1 mb-3">
          {[
            { label: 'Conservador', alpha: 0.05, lambda_hist: 5.0 },
            { label: 'Balanceado',  alpha: 0.10, lambda_hist: 3.0 },
            { label: 'Libre',       alpha: 0.30, lambda_hist: 1.0 },
          ].map(preset => (
            <button key={preset.label}
              onClick={() => setParams(p => ({ ...p, alpha: preset.alpha, lambda_hist: preset.lambda_hist }))}
              className={`flex-1 text-xs py-1 rounded-md font-semibold border transition-colors ${
                params.alpha === preset.alpha && params.lambda_hist === preset.lambda_hist
                  ? 'bg-oxxo-red text-white border-oxxo-red'
                  : 'bg-gray-50 text-gray-600 border-gray-200 hover:border-oxxo-red hover:text-oxxo-red'
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          <Slider label="Alpha (RCL)" name="alpha" min={0} max={1} step={0.05} value={params.alpha} onChange={setP}
            hint="Bajo = más conservador · Alto = más exploratorio" />
          <Slider label="Iteraciones" name="max_iter" min={1} max={100} step={1} value={params.max_iter} onChange={setP} />
          <Slider label="Búsqueda local" name="local_rounds" min={0} max={50} step={1} value={params.local_rounds} onChange={setP}
            hint="Incluye movimientos restore y reorder" />
          <Slider label="Peso histórico (λ)" name="lambda_hist" min={0} max={10} step={0.1} value={params.lambda_hist} onChange={setP}
            hint="Más alto = más apego al planograma histórico" />
          <Slider label="Peso visibilidad (β)" name="beta_vis" min={0} max={1} step={0.01} value={params.beta_vis} onChange={setP}
            hint="Premio por charolas visibles (efecto secundario)" />

          <div>
            <label className="label">Semilla (seed)</label>
            <input type="number" min={0} max={9999} value={params.seed}
              onChange={e => setP('seed', parseInt(e.target.value) || 0)}
              className="input-field" />
          </div>
        </div>
      </div>

      {/* ── Frentes y variedad ────────────────────────────── */}
      <div className="card p-4">
        <p className="section-title">5. Frentes y variedad</p>
        {maxFeasible != null && params.max_frentes > maxFeasible && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-2 text-xs text-amber-700">
            ⚠️ Con este dataset, máximo factible es <strong>{maxFeasible} frentes</strong>. Valores mayores causan infactibilidad.
          </div>
        )}
        {maxFeasible != null && (
          <p className="text-xs text-gray-400 mb-2">
            Capacidad del mueble permite hasta <strong className="text-green-600">{maxFeasible} frentes</strong> con todos los productos.
          </p>
        )}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <NumberInput label="Frentes mín." name="min_frentes" min={1} max={10} value={params.min_frentes} onChange={setP} />
          <NumberInput label="Frentes máx." name="max_frentes" min={1} max={20} value={params.max_frentes} onChange={setP} />
        </div>
        <div>
          <label className="label">Variedad máx. (opcional)</label>
          <input type="number" min={1} max={500} value={params.max_variedad}
            onChange={e => setP('max_variedad', e.target.value)}
            placeholder="Sin límite"
            className="input-field" />
        </div>
      </div>

      {/* ── Botón Run ─────────────────────────────────────── */}
      <button
        onClick={handleRun}
        disabled={!fileId || !selFmt || running}
        className="btn-primary w-full text-center text-base py-3"
      >
        {running ? '⏳ Optimizando…' : '🚀 Generar Planograma'}
      </button>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">
          <strong>Error:</strong> {error}
        </div>
      )}
    </aside>
  )
}
