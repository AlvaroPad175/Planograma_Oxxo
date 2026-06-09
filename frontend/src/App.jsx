import { useState } from 'react'
import Header from './components/Header'
import ControlPanel from './components/ControlPanel'
import Tabs from './components/Tabs'
import PlanogramView from './components/PlanogramView'
import MetricsCards from './components/MetricsCards'
import DataTable from './components/DataTable'
import { csvDownloadUrl, diagCsvDownloadUrl } from './api/client'

const TABS = [
  { id: 'planograma',  label: '📊 Planograma' },
  { id: 'metricas',    label: '📈 Métricas' },
  { id: 'asignaciones',label: '📋 Asignaciones' },
  { id: 'no_asignados',label: '⚠️ No asignados' },
  { id: 'historico',   label: '📜 Comparación histórica' },
]

const ASSIGNMENT_COLS = [
  { key: 'charola',     label: 'Charola' },
  { key: 'ubicacion',   label: 'Pos.' },
  { key: 'upc',         label: 'UPC' },
  { key: 'name',        label: 'Producto',    className: 'max-w-xs truncate' },
  { key: 'planogrupo',  label: 'Familia' },
  { key: 'x_abs',       label: 'X abs.', render: v => v.toFixed(1) },
  { key: 'num_frentes', label: 'Frentes' },
  { key: 'ancho',       label: 'Ancho', render: v => `${v.toFixed(1)} cm` },
  { key: 'alto',        label: 'Alto',  render: v => `${v.toFixed(1)} cm` },
]

const DIAG_COLS = [
  { key: 'charola',     label: 'Charola' },
  { key: 'n_productos', label: 'Productos' },
  { key: 'ancho_usado', label: 'Usado', render: v => `${v.toFixed(1)} cm` },
  { key: 'capacidad',   label: 'Cap.',   render: v => `${v.toFixed(1)} cm` },
  { key: 'holgura',     label: 'Holgura', render: v => `${v.toFixed(1)} cm` },
  {
    key: 'es_factible', label: 'Factible',
    render: v => v
      ? <span className="text-green-600 font-bold">✓</span>
      : <span className="text-red-500 font-bold">✗</span>,
  },
]

const UNPLACED_COLS = [
  { key: 'upc',    label: 'UPC' },
  { key: 'name',   label: 'Producto' },
  { key: 'reason', label: 'Razón' },
]

const HIST_COLS = [
  { key: 'name',        label: 'Producto', className: 'max-w-xs truncate' },
  { key: 'planogrupo',  label: 'Familia' },
  { key: 'hist_charola',label: 'Charola hist.' },
  { key: 'charola',     label: 'Charola actual' },
  { key: 'hist_pos',    label: 'Pos. hist.' },
  { key: 'ubicacion',   label: 'Pos. actual' },
  {
    key: '_estado',
    label: 'Estado',
    render: (_, row) => {
      if (row.charola === row.hist_charola && row.ubicacion === row.hist_pos)
        return <span className="text-green-600 font-bold text-xs">✓ Exacto</span>
      if (row.charola === row.hist_charola)
        return <span className="text-yellow-600 font-semibold text-xs">~ Misma charola</span>
      return <span className="text-red-500 font-semibold text-xs">↻ Cambió charola</span>
    },
  },
]

function ProgressPanel({ progress }) {
  if (!progress) return null
  const { latest, taskId } = progress

  if (!latest) return null

  let pct = 0
  let text = ''
  let color = 'bg-oxxo-red'

  if (latest.type === 'progress') {
    pct  = Math.round((latest.it / latest.total) * 100)
    text = `Iteración ${latest.it}/${latest.total} — score: ${latest.score > 0 ? '+' : ''}${latest.score}  |  mejor: ${latest.best > 0 ? '+' : ''}${latest.best}`
    color = 'bg-oxxo-red'
  } else if (latest.type === 'status') {
    text = latest.text; pct = 5
  } else if (latest.type === 'warning') {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-3 text-sm text-yellow-700">
        ⚠️ {latest.text}
      </div>
    )
  } else if (latest.type === 'done') {
    pct = 100; text = '✅ Optimización completada'; color = 'bg-green-500'
  }

  return (
    <div className="card p-4">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{text}</span>
        <span className="font-mono font-bold">{pct}%</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div
          className={`${color} h-2 rounded-full transition-all duration-300 ${pct < 100 ? 'progress-pulse' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function HistoricoTab({ assignments, metrics }) {
  const exact    = assignments.filter(a => a.charola === a.hist_charola && a.ubicacion === a.hist_pos)
  const sameShelf = assignments.filter(a => a.charola === a.hist_charola && a.ubicacion !== a.hist_pos)
  const moved    = assignments.filter(a => a.charola !== a.hist_charola)
  const total    = assignments.length

  return (
    <div className="flex flex-col gap-4">
      {/* Resumen */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card p-3 text-center border-l-4 border-green-500">
          <div className="text-2xl font-black text-green-600">{exact.length}</div>
          <div className="text-xs font-semibold text-gray-600 mt-0.5">Posición exacta</div>
          <div className="text-xs text-gray-400">{total > 0 ? Math.round(exact.length / total * 100) : 0}% del total</div>
        </div>
        <div className="card p-3 text-center border-l-4 border-yellow-400">
          <div className="text-2xl font-black text-yellow-600">{sameShelf.length}</div>
          <div className="text-xs font-semibold text-gray-600 mt-0.5">Misma charola, distinta pos.</div>
          <div className="text-xs text-gray-400">{total > 0 ? Math.round(sameShelf.length / total * 100) : 0}% del total</div>
        </div>
        <div className="card p-3 text-center border-l-4 border-red-400">
          <div className="text-2xl font-black text-red-600">{moved.length}</div>
          <div className="text-xs font-semibold text-gray-600 mt-0.5">Cambió de charola</div>
          <div className="text-xs text-gray-400">{total > 0 ? Math.round(moved.length / total * 100) : 0}% del total</div>
        </div>
      </div>

      {/* Tabla */}
      <DataTable
        rows={assignments}
        columns={HIST_COLS}
        title={`${assignments.length} productos — comparación vs histórico`}
        maxRows={300}
      />
    </div>
  )
}

function Welcome() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-6xl mb-4">🛒</div>
      <h2 className="text-2xl font-bold text-gray-700 mb-2">
        Optimizador Inteligente de Planogramas
      </h2>
      <p className="text-gray-400 max-w-sm text-sm">
        Carga un archivo CSV o Excel en el panel izquierdo,
        selecciona el formato y genera tu planograma optimizado con GRASP.
      </p>
    </div>
  )
}

export default function App() {
  const [result, setResult]     = useState(null)
  const [progress, setProgress] = useState(null)
  const [activeTab, setActiveTab] = useState('planograma')

  function handleResult(r) {
    setResult(r)
    if (r) setActiveTab('planograma')
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 flex gap-4 p-4 max-w-screen-2xl mx-auto w-full">

        {/* ── Left sidebar ─────────────────────────────────────────────── */}
        <ControlPanel onResult={handleResult} onProgress={setProgress} />

        {/* ── Right content ────────────────────────────────────────────── */}
        <section className="flex-1 min-w-0 flex flex-col gap-4">

          {/* Progress */}
          {progress && <ProgressPanel progress={progress} />}

          {!result ? (
            <div className="card flex-1">
              <Welcome />
            </div>
          ) : (
            <>
              {/* Download buttons */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-gray-600">Descargar:</span>
                <a href={csvDownloadUrl(result.task_id)}
                   className="btn-secondary" download>
                  📥 CSV Planograma
                </a>
                <a href={diagCsvDownloadUrl(result.task_id)}
                   className="btn-secondary" download>
                  📥 CSV Diagnóstico
                </a>
                <button
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
                    const url = URL.createObjectURL(blob)
                    Object.assign(document.createElement('a'), { href: url, download: `planograma_${result.tag}.json` }).click()
                  }}
                  className="btn-secondary"
                >
                  📥 JSON
                </button>
              </div>

              {/* Tabs */}
              <div className="card p-4">
                <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

                {activeTab === 'planograma' && (
                  <PlanogramView
                    assignments={result.assignments}
                    shelves={result.shelves}
                    metrics={result.metrics}
                  />
                )}

                {activeTab === 'metricas' && (
                  <div className="flex flex-col gap-6">
                    <MetricsCards metrics={result.metrics} />
                    <DataTable
                      rows={result.diagnostics}
                      columns={DIAG_COLS}
                      title="Diagnóstico por charola"
                    />
                  </div>
                )}

                {activeTab === 'asignaciones' && (
                  <DataTable
                    rows={result.assignments}
                    columns={ASSIGNMENT_COLS}
                    title={`${result.assignments.length} productos colocados`}
                    maxRows={200}
                  />
                )}

                {activeTab === 'no_asignados' && (
                  result.unplaced.length === 0
                    ? <p className="text-green-600 font-semibold text-sm py-4">✅ Todos los productos fueron colocados.</p>
                    : <DataTable rows={result.unplaced} columns={UNPLACED_COLS}
                        title={`${result.unplaced.length} productos no colocados`} />
                )}

                {activeTab === 'historico' && (
                  <HistoricoTab assignments={result.assignments} metrics={result.metrics} />
                )}
              </div>

              {/* Metrics always visible at bottom */}
              <MetricsCards metrics={result.metrics} />
            </>
          )}
        </section>
      </main>
    </div>
  )
}
