from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

Solution = Dict[int, List[int]]  # charola_id -> [product_id, ...]


@dataclass(frozen=True)
class Product:
    id: int
    upc: str
    name: str                     # ITEM_DESC si existe, si no UPC
    ancho: float
    num_frentes: float
    width_total: float            # ANCHO × NUM_FRENTES  (ancho visual)
    separador: float              # por producto; 0.0 si no existe columna
    ancho_ocupado: float          # width_total + separador (espacio real)
    hist_charola: int
    hist_pos: int
    alto: Optional[float]         # None si la columna no existe o es NaN
    image_path: Optional[str] = None   # IMAGE_PATH o IMAGE_URL opcionales
    peso: float = 0.0
    grupo: str = ""
    categoria: str = ""
    demanda: float = 1.0
    ganancia: float = 1.0
    rotacion: float = 1.0
    promo: float = 0.0
    estacional: float = 1.0


@dataclass(frozen=True)
class Shelf:
    charola: int
    width: float
    height: float          # clearance para hard check (inf cuando Height es visual)
    draw_height: float     # alto visual para el planograma
    x_abs_base: float
    y: float
    visibility: float = 1.0
    clearance: float = float('inf')  # clearance estimado del gap Y (soft constraint)
