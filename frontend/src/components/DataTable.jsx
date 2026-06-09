import { useState } from 'react'

export default function DataTable({ rows, columns, title, maxRows = 100 }) {
  const [search, setSearch] = useState('')
  if (!rows || rows.length === 0) return (
    <div className="text-sm text-gray-400 italic py-4 text-center">Sin datos.</div>
  )

  const filtered = search
    ? rows.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(search.toLowerCase())))
    : rows

  const displayed = filtered.slice(0, maxRows)

  return (
    <div>
      {title && <h3 className="font-semibold text-sm text-gray-700 mb-2">{title}</h3>}
      <div className="flex items-center gap-2 mb-2">
        <input
          type="search" placeholder="Buscar…" value={search}
          onChange={e => setSearch(e.target.value)}
          className="input-field w-48 text-xs py-1"
        />
        <span className="text-xs text-gray-400">{filtered.length} filas</span>
      </div>
      <div className="overflow-auto rounded-lg border border-gray-200">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              {columns.map(c => (
                <th key={c.key} className="px-3 py-2 text-left font-semibold text-gray-500 whitespace-nowrap border-b border-gray-200">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                {columns.map(c => (
                  <td key={c.key} className={`px-3 py-1.5 whitespace-nowrap ${c.className || ''}`}>
                    {c.render ? c.render(row[c.key], row) : String(row[c.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length > maxRows && (
        <p className="text-xs text-gray-400 mt-1">Mostrando {maxRows} de {filtered.length} filas.</p>
      )}
    </div>
  )
}
