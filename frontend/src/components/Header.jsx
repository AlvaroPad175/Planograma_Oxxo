export default function Header() {
  return (
    <header className="bg-oxxo-dark border-b-4 border-oxxo-yellow shadow-md sticky top-0 z-50">
      <div className="max-w-screen-2xl mx-auto px-6 py-3 flex items-center gap-4">
        {/* OXXO logo mark */}
        <div className="flex items-center gap-2">
          <div className="bg-oxxo-red rounded px-2 py-1 text-white font-black text-sm tracking-widest">
            OXXO
          </div>
        </div>

        <div className="h-6 w-px bg-gray-600" />

        <div>
          <h1 className="text-white font-bold text-base leading-none">
            Optimizador Inteligente de Planogramas
          </h1>
          <p className="text-gray-400 text-xs mt-0.5">
            Powered by GRASP · Optimización Metaheurística
          </p>
        </div>

        <div className="ml-auto flex items-center gap-3 text-xs text-gray-400">
          <span className="hidden md:block">v1.0</span>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
            <span>API activa</span>
          </div>
        </div>
      </div>
    </header>
  )
}
