export default function Legend({ families }) {
  if (!families || families.size === 0) return null

  return (
    <div className="flex flex-wrap gap-3 px-2">
      {[...families.entries()].map(([name, color]) => (
        <div key={name} className="flex items-center gap-1.5">
          <span
            className="inline-block w-4 h-4 rounded"
            style={{ backgroundColor: color }}
          />
          <span className="text-xs text-gray-600 font-medium">{name}</span>
        </div>
      ))}
    </div>
  )
}
