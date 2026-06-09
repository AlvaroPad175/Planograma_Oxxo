"""
export.py — Exportación de resultados del planograma.

Funciones:
  build_diagnostics()  — DataFrame de diagnóstico por charola (FIX 4).
  csv_bytes()          — Convierte DataFrame a bytes CSV (utf-8-sig).
  png_bytes()          — Convierte figura matplotlib a bytes PNG.
"""
from __future__ import annotations

import io
from typing import List

import matplotlib.pyplot as plt
import pandas as pd

from .models import Shelf


def build_diagnostics(output_df: pd.DataFrame, shelves: List[Shelf]) -> pd.DataFrame:
    """
    Genera el DataFrame de diagnóstico por charola.

    Columnas de salida:
        CHAROLA, ANCHO_USADO, ANCHO_CAPACIDAD, HOLGURA,
        NUM_PRODUCTOS, ES_FACTIBLE
    """
    if output_df.empty:
        return pd.DataFrame(columns=[
            "CHAROLA", "ANCHO_USADO", "ANCHO_CAPACIDAD",
            "HOLGURA", "NUM_PRODUCTOS", "ES_FACTIBLE",
        ])

    capacity = pd.Series(
        {s.charola: s.width for s in shelves},
        name="ANCHO_CAPACIDAD",
    )

    # ANCHO_NETO = ANCHO_TOTAL + SEP_APLICADO (0 para el último producto)
    # La suma por charola da el ancho real usado (sep entre productos, no después del último)
    ancho_col = "ANCHO_NETO" if "ANCHO_NETO" in output_df.columns else "ANCHO_TOTAL"
    used_w = output_df.groupby("CHAROLA")[ancho_col].sum().rename("ANCHO_USADO")
    num_prods = output_df.groupby("CHAROLA")["UPC_CVE"].count().rename("NUM_PRODUCTOS")

    diag = pd.concat([used_w, capacity, num_prods], axis=1)
    diag.index.name = "CHAROLA"
    # Charolas sin productos asignados quedan con NaN → rellenar con 0
    diag["ANCHO_USADO"]   = diag["ANCHO_USADO"].fillna(0.0)
    diag["NUM_PRODUCTOS"] = diag["NUM_PRODUCTOS"].fillna(0).astype(int)
    diag["HOLGURA"]       = diag["ANCHO_CAPACIDAD"] - diag["ANCHO_USADO"]
    diag["ES_FACTIBLE"]   = diag["HOLGURA"] >= -1e-9

    return diag.reset_index()


def csv_bytes(df: pd.DataFrame, index: bool = False) -> bytes:
    """Serializa un DataFrame a bytes CSV codificado en utf-8-sig."""
    buf = io.StringIO()
    df.to_csv(buf, index=index, encoding="utf-8-sig")
    return buf.getvalue().encode("utf-8-sig")


def png_bytes(fig: plt.Figure, dpi: int = 150) -> bytes:
    """Serializa una figura matplotlib a bytes PNG."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    return buf.read()
