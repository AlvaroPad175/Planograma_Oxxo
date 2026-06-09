function Card({ label, value, sub, accent, info }) {
  return (
    <div className="card p-4 flex flex-col gap-1" title={info}>
      <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide leading-none">{label}</span>
      <span className={`text-2xl font-black leading-none mt-1 ${accent || 'text-gray-900'}`}>{value}</span>
      {sub && <span className="text-xs text-gray-400 mt-0.5">{sub}</span>}
    </div>
  )
}

export default function MetricsCards({ metrics }) {
  if (!metrics) return null
  const {
    score, total_products, placed, unplaced,
    occupancy_pct, min_slack, total_capacity, used_capacity,
    hist_fidelity = 0, products_in_hist_charola = 0,
  } = metrics

  const scoreLabel = score >= 0 ? `+${score.toFixed(2)}` : score.toFixed(2)

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
      <Card
        label="Ocupación"
        value={`${occupancy_pct}%`}
        sub={`${used_capacity.toFixed(0)} / ${total_capacity.toFixed(0)} cm`}
        accent={occupancy_pct >= 85 ? 'text-green-600' : occupancy_pct >= 60 ? 'text-yellow-600' : 'text-red-500'}
        info="Porcentaje del espacio lineal usado respecto a la capacidad total de charolas"
      />
      <Card label="Colocados"    value={placed}   accent="text-green-600" />
      <Card label="No colocados" value={unplaced} accent={unplaced > 0 ? 'text-red-500' : 'text-gray-400'} />
      <Card label="Productos únicos" value={total_products} />
      <Card
        label="Fidelidad hist."
        value={`${hist_fidelity}%`}
        sub={`${products_in_hist_charola} en charola histórica`}
        accent={hist_fidelity >= 85 ? 'text-green-600' : hist_fidelity >= 60 ? 'text-yellow-600' : 'text-red-500'}
        info="Porcentaje de productos que quedaron en su charola histórica"
      />
      <Card
        label="Holgura prom."
        value={`${min_slack.toFixed(1)} cm`}
        accent={min_slack >= 5 ? 'text-gray-900' : min_slack >= 0 ? 'text-yellow-600' : 'text-red-500'}
        info="Espacio libre promedio por charola (capacidad - productos colocados)"
      />
      <Card label="Uso real" value={`${used_capacity.toFixed(0)} cm`} sub={`cap. ${total_capacity.toFixed(0)} cm`} />
      <Card
        label="Score GRASP"
        value={scoreLabel}
        sub="mayor = mejor vs histórico"
        accent="text-gray-500"
        info="Función objetivo. Valores positivos = buenos cuando λ es alto. Negativo si hay muchos desplazados."
      />
    </div>
  )
}
