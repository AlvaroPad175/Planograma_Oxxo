export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 border-b border-gray-200 mb-4 overflow-x-auto">
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={[
            'px-4 py-2.5 text-sm font-semibold rounded-t-lg whitespace-nowrap transition-colors duration-100',
            active === t.id
              ? 'bg-white border border-b-white border-gray-200 text-oxxo-red -mb-px'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50',
          ].join(' ')}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
