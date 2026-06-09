from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FormatOption(BaseModel):
    key: str
    label: str
    seg: str
    mue: str
    pg: str
    tam: float
    dir: str
    n: int


class ShelfInfo(BaseModel):
    charola: int
    x_abs_base: float
    y: float
    width: float
    draw_height: float
    visibility: float = 1.0


class ShelfOverride(BaseModel):
    CHAROLA: int
    Ancho_cm: float
    Alto_cm: float
    X: float = 0.0
    Y: float = 0.0


class OptimizeRequest(BaseModel):
    file_id: str
    seg: str
    mue: str
    pg: str
    tam: float
    dir: str
    alpha: float = 0.2
    max_iter: int = 20
    local_rounds: int = 20
    seed: int = 42
    lambda_hist: float = 1.0
    beta_vis: float = 0.10
    min_frentes: int = 1
    max_frentes: int = 4
    max_variedad: Optional[int] = None
    shelf_overrides: List[ShelfOverride] = []


class ProductAssignment(BaseModel):
    upc: str
    name: str
    charola: int
    x_abs: float
    x_local: float
    ancho: float
    num_frentes: int
    width_total: float
    alto: float
    planogrupo: str
    ubicacion: int
    sep_aplicado: float = 0.0
    hist_charola: int = 0
    hist_pos: int = 0


class Metrics(BaseModel):
    score: float
    total_products: int
    placed: int
    unplaced: int
    occupancy_pct: float
    min_slack: float
    total_capacity: float
    used_capacity: float
    hist_fidelity: float = 0.0
    products_in_hist_charola: int = 0


class DiagRow(BaseModel):
    charola: int
    n_productos: int
    ancho_usado: float
    capacidad: float
    holgura: float
    es_factible: bool


class UnplacedProduct(BaseModel):
    upc: str
    name: str
    reason: str


class OptimizeResult(BaseModel):
    task_id: str
    assignments: List[ProductAssignment]
    shelves: List[ShelfInfo]
    metrics: Metrics
    diagnostics: List[DiagRow]
    unplaced: List[UnplacedProduct]
    tag: str
