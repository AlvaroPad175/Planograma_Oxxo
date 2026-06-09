from __future__ import annotations

import re
import unicodedata


def fmt_tag(segmento: str, mueble: str, planogrupo: str, tamano: float, direccion: str) -> str:
    """Genera un slug seguro para nombres de archivo."""
    pg = re.sub(r"[^a-zA-Z0-9_]", "_", planogrupo)
    return f"{segmento}_{mueble}_{pg}_{int(tamano)}_{direccion}"


def short_label(name: str, upc: str, max_chars: int = 10) -> str:
    """Etiqueta corta para mostrar en el bloque visual del producto."""
    if name and name != upc and name != "nan":
        # Toma las primeras palabras que quepan
        words = name.split()
        label = ""
        for w in words:
            candidate = (label + " " + w).strip()
            if len(candidate) <= max_chars:
                label = candidate
            else:
                break
        return label if label else name[:max_chars]
    return upc[-6:] if len(upc) >= 6 else upc


def safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default
