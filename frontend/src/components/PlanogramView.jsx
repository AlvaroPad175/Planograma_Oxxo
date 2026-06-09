import { useEffect, useMemo, useRef, useState } from 'react'
import ProductBlock, { getProductColor, isBottleShape } from './ProductBlock'
import Legend from './Legend'

const GAP_CM    = 1.2
const MIN_ROW_H = 15

// Cache de imágenes persistente entre renders (module-level)
const _imgCache = new Map()

function offImageUrl(upc) {
  const c = upc.replace(/\D/g, '')
  if (c.length >= 13)
    return `https://images.openfoodfacts.org/images/products/${c.slice(0,3)}/${c.slice(3,6)}/${c.slice(6,9)}/${c.slice(9)}/front_es.400.jpg`
  if (c.length >= 8)
    return `https://images.openfoodfacts.org/images/products/${c}/front_es.400.jpg`
  return null
}

async function fetchImgDataUrl(upc) {
  const url = offImageUrl(upc)
  if (!url) return 'error'
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error('not found')
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  } catch {
    return 'error'
  }
}

// ── Layout ──────────────────────────────────────────────────────────────────

function computeLayout(shelves, assignments) {
  const yGroups = new Map()
  for (const s of shelves) {
    if (!yGroups.has(s.y)) yGroups.set(s.y, [])
    yGroups.get(s.y).push(s)
  }

  const rowH = new Map()
  for (const [y, rowShelves] of yGroups) {
    const charolas = new Set(rowShelves.map(s => s.charola))
    const prods = assignments.filter(a => charolas.has(a.charola))
    let h = prods.reduce((m, a) => Math.max(m, a.alto || 0), 0)
    if (h < 5) h = rowShelves.reduce((m, s) => Math.max(m, s.draw_height || 0), 0)
    rowH.set(y, Math.max(h, MIN_ROW_H))
  }

  const sortedYs = [...yGroups.keys()].sort((a, b) => b - a)
  const rowYStart = new Map()
  let cursor = 0
  for (const y of sortedYs) {
    rowYStart.set(y, cursor)
    cursor += rowH.get(y) + GAP_CM
  }

  const totalWidth  = Math.max(...shelves.map(s => s.x_abs_base + s.width))
  const totalHeight = cursor - GAP_CM
  const moduleXs    = [...new Set(shelves.map(s => s.x_abs_base))].sort((a, b) => a - b)
  const moduleWidth = shelves.find(s => s.x_abs_base === moduleXs[0])?.width ?? 55

  const shelfLayout = new Map()
  for (const s of shelves) {
    shelfLayout.set(s.charola, { yStart: rowYStart.get(s.y), h: rowH.get(s.y) })
  }

  return { totalWidth, totalHeight, moduleXs, moduleWidth, shelfLayout, sortedYs, rowH, rowYStart }
}

// ── Door ────────────────────────────────────────────────────────────────────

function Door({ xBase, width, totalHeight, sortedYs, rowYStart, rowH, assignments, shelfLayout, scale, imgMap }) {
  const doorAssignments = assignments.filter(a => {
    const lay = shelfLayout.get(a.charola)
    return lay && a.x_abs >= xBase - 0.01 && a.x_abs < xBase + width + 0.01
  })

  return (
    <g transform={`translate(${xBase * scale}, 0)`}>
      {/* Shelf row backgrounds */}
      {sortedYs.map((y, i) => (
        <rect key={y}
          x={0} y={rowYStart.get(y) * scale}
          width={width * scale} height={rowH.get(y) * scale}
          fill={i % 2 === 0 ? '#F8FAFC' : '#F1F5F9'}
        />
      ))}

      {/* Shelf floor lines */}
      {sortedYs.map(y => (
        <line key={y}
          x1={0} y1={(rowYStart.get(y) + rowH.get(y)) * scale}
          x2={width * scale} y2={(rowYStart.get(y) + rowH.get(y)) * scale}
          stroke="#94A3B8" strokeWidth="1.5"
        />
      ))}

      {/* Products */}
      {doorAssignments.map((a, idx) => {
        const lay = shelfLayout.get(a.charola)
        if (!lay) return null
        const yBottom = (lay.yStart + lay.h) * scale
        const h = Math.min(a.alto > 0 ? a.alto : lay.h * 0.92, lay.h * 0.97) * scale
        const w = a.width_total * scale
        const x = (a.x_abs - xBase) * scale
        const color    = getProductColor(a.planogrupo, a.upc, a.name)
        const label    = (a.name || a.upc).slice(0, 16)
        const isBottle = isBottleShape(a.name)
        const imgUrl   = imgMap?.[a.upc]
        return (
          <ProductBlock
            key={idx} x={x} yBottom={yBottom} w={w} h={h}
            color={color} label={label}
            isBottle={isBottle} imgUrl={imgUrl}
          />
        )
      })}

      {/* Door border */}
      <rect x={0.5} y={0.5}
        width={width * scale - 1} height={totalHeight * scale - 1}
        fill="none" stroke="#334155" strokeWidth="2.5" rx="2"
      />
    </g>
  )
}

// ── Full / Single views ──────────────────────────────────────────────────────

function FullView({ layout, assignments, scale, imgMap }) {
  const { totalWidth, totalHeight, moduleXs, moduleWidth, shelfLayout, sortedYs, rowH, rowYStart } = layout
  const svgW = totalWidth * scale
  const svgH = totalHeight * scale
  return (
    <svg width={svgW + 1} height={svgH + 1} viewBox={`0 0 ${svgW+1} ${svgH+1}`} style={{ display:'block' }}>
      <rect width={svgW} height={svgH} fill="white" />
      {moduleXs.map((xBase) => (
        <Door key={xBase}
          xBase={xBase} width={moduleWidth} totalHeight={totalHeight}
          sortedYs={sortedYs} rowYStart={rowYStart} rowH={rowH}
          assignments={assignments} shelfLayout={shelfLayout}
          scale={scale} imgMap={imgMap}
        />
      ))}
    </svg>
  )
}

function SingleDoorView({ layout, assignments, doorIndex, scale, imgMap }) {
  const { moduleXs, moduleWidth, totalHeight, shelfLayout, sortedYs, rowH, rowYStart } = layout
  const xBase = moduleXs[doorIndex] ?? 0
  const svgW  = moduleWidth * scale
  const svgH  = totalHeight * scale
  const vx    = xBase * scale
  return (
    <svg width={svgW + 1} height={svgH + 1} viewBox={`${vx} 0 ${svgW+1} ${svgH+1}`} style={{ display:'block' }}>
      <rect x={vx} width={svgW} height={svgH} fill="white" />
      <Door
        xBase={xBase} width={moduleWidth} totalHeight={totalHeight}
        sortedYs={sortedYs} rowYStart={rowYStart} rowH={rowH}
        assignments={assignments} shelfLayout={shelfLayout}
        scale={scale} imgMap={imgMap}
      />
    </svg>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

export default function PlanogramView({ assignments, shelves }) {
  const [scale, setScale]           = useState(5)
  const [activeDoor, setActiveDoor] = useState('all')
  const [downloading, setDownloading] = useState(false)
  const [showImages, setShowImages]   = useState(true)
  const [imgMap, setImgMap]           = useState({})
  const [imgProgress, setImgProgress] = useState(null) // {loaded, total}
  const svgContainerRef = useRef(null)

  const layout = useMemo(() => computeLayout(shelves, assignments), [shelves, assignments])
  const { totalWidth, totalHeight, moduleXs } = layout

  // Cargar imágenes de Open Food Facts en background
  useEffect(() => {
    if (!showImages || assignments.length === 0) return

    const upcs = [...new Set(assignments.map(a => a.upc))]
    const missing = upcs.filter(u => !_imgCache.has(u))

    // Aplicar inmediatamente lo que ya está cacheado
    if (missing.length === 0) {
      const m = {}
      upcs.forEach(u => { m[u] = _imgCache.get(u) })
      setImgMap(m)
      setImgProgress(null)
      return
    }

    setImgProgress({ loaded: upcs.length - missing.length, total: upcs.length })

    // Fetch con concurrencia limitada (semáforo simple de 5)
    let active = 0
    let idx = 0
    let done = upcs.length - missing.length

    function next() {
      while (active < 5 && idx < missing.length) {
        const upc = missing[idx++]
        active++
        fetchImgDataUrl(upc).then(result => {
          _imgCache.set(upc, result)
          active--
          done++
          // Actualizar estado progresivamente
          setImgMap(prev => ({ ...prev, [upc]: result }))
          setImgProgress(p => p ? { ...p, loaded: done } : null)
          if (done >= upcs.length) setImgProgress(null)
          next()
        })
      }
    }
    next()
  }, [assignments, showImages])

  const families = useMemo(() => {
    const seen = new Map()
    for (const a of assignments) {
      const color = getProductColor(a.planogrupo, a.upc, a.name)
      const key = a.name?.split(' ').slice(0, 2).join(' ') || a.upc
      if (!seen.has(key)) seen.set(key, color)
    }
    return seen
  }, [assignments])

  function downloadPNG() {
    const svg = svgContainerRef.current?.querySelector('svg')
    if (!svg) return
    setDownloading(true)
    const serializer = new XMLSerializer()
    const svgStr = serializer.serializeToString(svg)
    const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(svgBlob)
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width  = img.width  * 2
      canvas.height = img.height * 2
      const ctx = canvas.getContext('2d')
      ctx.scale(2, 2)
      ctx.fillStyle = 'white'
      ctx.fillRect(0, 0, img.width, img.height)
      ctx.drawImage(img, 0, 0)
      URL.revokeObjectURL(url)
      canvas.toBlob(blob => {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = `planograma_${activeDoor === 'all' ? 'mueble_completo' : `puerta_${activeDoor + 1}`}.png`
        a.click()
        setDownloading(false)
      }, 'image/png')
    }
    img.onerror = () => setDownloading(false)
    img.src = url
  }

  const effectiveImgMap = showImages ? imgMap : {}

  return (
    <div className="flex flex-col gap-3">
      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 font-medium">Escala:</span>
          <input type="range" min={2} max={14} step={0.5} value={scale}
            onChange={e => setScale(parseFloat(e.target.value))}
            className="w-28 accent-oxxo-red" />
          <span className="text-xs font-mono text-oxxo-red font-bold">{scale}px/cm</span>
        </div>
        <span className="text-xs text-gray-400">
          {totalWidth.toFixed(0)} cm × {totalHeight.toFixed(0)} cm · {moduleXs.length} puertas
        </span>

        {/* Toggle imágenes */}
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <div
            onClick={() => setShowImages(v => !v)}
            className={`w-8 h-4 rounded-full transition-colors ${showImages ? 'bg-oxxo-red' : 'bg-gray-300'}`}
          >
            <div className={`w-3 h-3 bg-white rounded-full mt-0.5 transition-transform ${showImages ? 'translate-x-4' : 'translate-x-0.5'}`} />
          </div>
          <span className="text-xs text-gray-500">Imágenes reales</span>
          {imgProgress && (
            <span className="text-xs text-gray-400">
              ({imgProgress.loaded}/{imgProgress.total})
            </span>
          )}
        </label>

        <button onClick={downloadPNG} disabled={downloading}
          className="ml-auto btn-secondary text-xs py-1 px-3 flex items-center gap-1">
          {downloading ? '⏳' : '🖼️'} {downloading ? 'Generando…' : 'Descargar PNG'}
        </button>
      </div>

      {/* Door tabs */}
      <div className="flex gap-1 flex-wrap">
        <button onClick={() => setActiveDoor('all')}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
            activeDoor === 'all' ? 'bg-oxxo-dark text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}>
          Mueble completo
        </button>
        {moduleXs.map((_, i) => (
          <button key={i} onClick={() => setActiveDoor(i)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              activeDoor === i ? 'bg-oxxo-red text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}>
            Puerta {i + 1}
          </button>
        ))}
      </div>

      {/* Door labels */}
      {activeDoor === 'all' && (
        <div className="flex">
          {moduleXs.map((_, i) => (
            <div key={i} className="text-center text-xs font-bold text-oxxo-red"
              style={{ width: layout.moduleWidth * scale, flexShrink: 0 }}>
              PUERTA {i + 1}
            </div>
          ))}
        </div>
      )}

      {/* SVG */}
      <div ref={svgContainerRef} className="overflow-auto border border-gray-200 rounded-xl bg-white shadow-inner">
        {activeDoor === 'all'
          ? <FullView layout={layout} assignments={assignments} scale={scale} imgMap={effectiveImgMap} />
          : <SingleDoorView layout={layout} assignments={assignments} doorIndex={activeDoor} scale={scale} imgMap={effectiveImgMap} />
        }
      </div>

      <Legend families={families} />
    </div>
  )
}
