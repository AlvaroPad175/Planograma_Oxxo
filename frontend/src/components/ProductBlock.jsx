const PALETTE = [
  '#E53E3E','#DD6B20','#D69E2E','#38A169','#319795',
  '#3182CE','#805AD5','#D53F8C','#C53030','#C05621',
  '#B7791F','#276749','#2C7A7B','#2B6CB0','#553C9A',
  '#97266D','#744210','#22543D','#1A365D','#44337A',
  '#E91E63','#FF5722','#FF9800','#FFC107','#8BC34A',
  '#4CAF50','#009688','#00BCD4','#03A9F4','#673AB7',
  '#9C27B0','#F44336','#795548','#607D8B','#455A64',
  '#F06292','#FFB74D','#81C784','#4DB6AC','#64B5F6',
]

const BRAND_COLORS = {
  'coca':       '#E53E3E',
  'pepsi':      '#3182CE',
  'sprite':     '#38A169',
  'fanta':      '#DD6B20',
  '7up':        '#276749',
  'manzanita':  '#D69E2E',
  'barrilitos': '#C05621',
  'jarritos':   '#E91E63',
  'agua':       '#319795',
  'squirt':     '#B7791F',
  'mirinda':    '#805AD5',
  'crush':      '#F06292',
  'del valle':  '#38A169',
  'jumex':      '#D69E2E',
  'boing':      '#DD6B20',
  'penafiel':   '#2C7A7B',
  'peñafiel':   '#2C7A7B',
  'topo chico': '#2B6CB0',
  'sangria':    '#97266D',
  'lift':       '#D53F8C',
  'tepachito':  '#744210',
  'sidral':     '#B7791F',
  'joya':       '#553C9A',
  'ciel':       '#319795',
}

function hashColor(str) {
  let h = 5381
  for (const c of str) h = (Math.imul(h, 33) ^ c.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

function brandColor(name) {
  const lower = (name || '').toLowerCase()
  for (const [brand, color] of Object.entries(BRAND_COLORS)) {
    if (lower.includes(brand)) return color
  }
  return null
}

export function getProductColor(planogrupo, upc, name) {
  const bc = brandColor(name)
  if (bc) return bc
  return hashColor(upc || name || planogrupo || '?')
}

function lighten(hex, pct = 0.35) {
  const n = parseInt(hex.replace('#',''), 16)
  const r = (n >> 16) & 255
  const g = (n >>  8) & 255
  const b =  n        & 255
  return `rgb(${Math.round(r+(255-r)*pct)},${Math.round(g+(255-g)*pct)},${Math.round(b+(255-b)*pct)})`
}

export function isBottleShape(name) {
  return !(name || '').toLowerCase().includes('lata')
}

// Bottle clip path — forma de botella con cuello y hombros
function bottlePath(x, yTop, w, h) {
  const cx     = x + w / 2
  const capHW  = w * 0.30           // mitad del ancho del cuello/tapa
  const bodyHW = w * 0.46           // mitad del ancho del cuerpo
  const capH   = Math.min(h * 0.07, 7)
  const neckEnd = yTop + h * 0.20   // donde termina el cuello
  const shoulderEnd = yTop + h * 0.28
  const bodyEnd = yTop + h * 0.97
  const r = Math.min(w * 0.10, 5)

  return [
    `M ${cx - capHW} ${yTop}`,
    `L ${cx + capHW} ${yTop}`,
    `L ${cx + capHW} ${yTop + capH}`,
    `L ${cx + capHW} ${neckEnd}`,
    `Q ${cx + bodyHW} ${neckEnd + (shoulderEnd - neckEnd) * 0.6} ${cx + bodyHW} ${shoulderEnd}`,
    `L ${cx + bodyHW} ${bodyEnd - r}`,
    `Q ${cx + bodyHW} ${bodyEnd} ${cx + bodyHW - r} ${bodyEnd}`,
    `L ${cx - bodyHW + r} ${bodyEnd}`,
    `Q ${cx - bodyHW} ${bodyEnd} ${cx - bodyHW} ${bodyEnd - r}`,
    `L ${cx - bodyHW} ${shoulderEnd}`,
    `Q ${cx - bodyHW} ${neckEnd + (shoulderEnd - neckEnd) * 0.6} ${cx - capHW} ${neckEnd}`,
    `L ${cx - capHW} ${yTop + capH}`,
    'Z',
  ].join(' ')
}

// Can clip path — lata cilíndrica ligeramente cónica
function canPath(x, yTop, w, h) {
  const lx = x + w * 0.06
  const rx = x + w * 0.94
  const bw = rx - lx
  const rx2 = Math.min(bw * 0.12, 6)
  return [
    `M ${lx + rx2} ${yTop}`,
    `L ${rx - rx2} ${yTop}`,
    `Q ${rx} ${yTop} ${rx} ${yTop + rx2}`,
    `L ${rx} ${yTop + h - rx2}`,
    `Q ${rx} ${yTop + h} ${rx - rx2} ${yTop + h}`,
    `L ${lx + rx2} ${yTop + h}`,
    `Q ${lx} ${yTop + h} ${lx} ${yTop + h - rx2}`,
    `L ${lx} ${yTop + rx2}`,
    `Q ${lx} ${yTop} ${lx + rx2} ${yTop}`,
    'Z',
  ].join(' ')
}

export default function ProductBlock({ x, yBottom, w, h, color, label, isBottle = true, imgUrl }) {
  const yTop   = yBottom - h
  const uid    = `${Math.round(x * 10)}_${Math.round(yTop * 10)}`
  const clipId = `cl_${uid}`
  const gradId = `gr_${uid}`
  const shineId = `sh_${uid}`
  const hasImg = imgUrl && imgUrl !== 'error'
  const showText = w > 10 && h > 14

  const shape = isBottle ? bottlePath(x, yTop, w, h) : canPath(x, yTop, w, h)

  // Colores del gradiente según tipo
  const gradTop    = lighten(color, 0.55)
  const gradBottom = color
  const gradMid    = lighten(color, 0.15)

  return (
    <g>
      <defs>
        <clipPath id={clipId}>
          <path d={shape} />
        </clipPath>

        {!hasImg && (
          <>
            <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%"   stopColor={gradTop} />
              <stop offset="50%"  stopColor={gradMid} />
              <stop offset="100%" stopColor={gradBottom} />
            </linearGradient>
            {/* Brillo lateral */}
            <linearGradient id={shineId} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%"   stopColor="white" stopOpacity="0.22" />
              <stop offset="35%"  stopColor="white" stopOpacity="0.08" />
              <stop offset="100%" stopColor="white" stopOpacity="0" />
            </linearGradient>
          </>
        )}
      </defs>

      {/* Cuerpo del producto */}
      <g clipPath={`url(#${clipId})`}>
        {hasImg ? (
          <image
            href={imgUrl}
            x={x} y={yTop} width={w} height={h}
            preserveAspectRatio="xMidYMid slice"
          />
        ) : (
          <>
            <path d={shape} fill={`url(#${gradId})`} />
            <path d={shape} fill={`url(#${shineId})`} />
          </>
        )}
      </g>

      {/* Contorno de la forma */}
      <path
        d={shape}
        fill="none"
        stroke={hasImg ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.35)'}
        strokeWidth="0.8"
      />

      {/* Etiqueta vertical */}
      {showText && (
        <text
          x={x + w / 2} y={yTop + h / 2}
          textAnchor="middle" dominantBaseline="middle"
          fill="white"
          fontSize={Math.min(9, w * 0.45, h * 0.18)}
          fontWeight="700"
          fontFamily="system-ui,sans-serif"
          transform={`rotate(-90,${x + w / 2},${yTop + h / 2})`}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
          stroke="rgba(0,0,0,0.55)"
          strokeWidth="2.5"
          paintOrder="stroke"
          opacity={hasImg ? 0.9 : 0.95}
        >
          {label}
        </text>
      )}
    </g>
  )
}
