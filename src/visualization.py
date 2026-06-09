"""
visualization.py — Visualización 2D del planograma OXXO (estilo comercial).

Estructura real del planograma:
  - Eje X: módulos contiguos (X_ABS = posición absoluta en el mueble).
  - Eje Y: filas (charolas) apiladas compactamente usando ALTO real de productos.
  - Separadores verticales entre módulos.
  - Separadores horizontales negros entre charolas.
  - Cada producto dibuja NUM_FRENTES frentes individuales de ANCHO cm cada uno.
"""
from __future__ import annotations

import hashlib
import io
from typing import Dict, List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

from .models import Shelf
from .utils import short_label

_PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    "#D37295", "#FABFD2", "#8CD17D", "#B6992D", "#499894",
    "#86BCB6", "#E49444", "#D4A6C8", "#A0CBE8", "#FFBE7D",
]


def _stable_color(key: str) -> str:
    h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    return _PALETTE[h % len(_PALETTE)]


def _try_load_image(path_or_url: str) -> Optional[np.ndarray]:
    try:
        if path_or_url.startswith("http"):
            import urllib.request
            from PIL import Image
            with urllib.request.urlopen(path_or_url, timeout=3) as r:
                img = Image.open(io.BytesIO(r.read())).convert("RGBA")
        else:
            from PIL import Image
            img = Image.open(path_or_url).convert("RGBA")
        return np.array(img)
    except Exception:
        return None


def _ensure_x_abs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garantiza que el DataFrame tenga columna X_ABS.

    - Si ya existe X_ABS (output de decode()): la usa directamente.
    - Si hay X_LOCAL + X del CSV: X_ABS = X + X_LOCAL.
    - Si solo hay el CSV crudo con UBICACION_BANDEJA: computa posiciones
      acumulando ANCHO × NUM_FRENTES + SEPARADOR por grupo (CHAROLA, X).
    """
    if "X_ABS" in df.columns:
        return df

    # Caso 2: X_LOCAL ya calculado + X del módulo
    if "X_LOCAL" in df.columns and "X" in df.columns:
        df = df.copy()
        df["X_ABS"] = df["X"].astype(float) + df["X_LOCAL"].astype(float)
        return df

    # Caso 3: CSV crudo — reconstruir desde UBICACION_BANDEJA
    df = df.copy()
    x_mod_col = "X" if "X" in df.columns else None
    group_keys = (["CHAROLA", x_mod_col] if x_mod_col else ["CHAROLA"])

    rows_out = []
    for _, grp in df.groupby(group_keys, sort=False):
        grp = grp.copy()
        if "UBICACION_BANDEJA" in grp.columns:
            grp = grp.sort_values("UBICACION_BANDEJA")
        x_mod = float(grp[x_mod_col].iloc[0]) if x_mod_col else 0.0
        cursor = 0.0
        for idx, row in grp.iterrows():
            ancho = float(row.get("ANCHO") or row.get("ANCHO_TOTAL") or 1.0)
            n_fr  = max(1, int(float(row.get("NUM_FRENTES", 1) or 1)))
            sep   = float(row.get("SEPARADOR", 0.0) or 0.0)
            grp.at[idx, "X_LOCAL"] = cursor
            grp.at[idx, "X_ABS"]   = x_mod + cursor
            cursor += ancho * n_fr + sep
        rows_out.append(grp)

    return pd.concat(rows_out).reset_index(drop=True) if rows_out else df


def _compute_grid(
    output_df: pd.DataFrame,
    shelves: List[Shelf],
    shelf_gap: float = 1.5,
    min_row_h: float = 10.0,
) -> Tuple[Dict[int, dict], float, List[float], List[float]]:
    """
    Calcula el layout de grilla módulos × charolas.

    Agrupa las charolas por Y físico (cada Y único = una fila horizontal
    que abarca todos los módulos). Apila las filas compactamente usando
    max(ALTO) de los productos como altura de fila.

    Returns:
        layout      — {charola_id: {"y_vis": float, "h": float}}
        total_width — ancho total del mueble (todos los módulos)
        module_xs   — posiciones X absolutas de inicio de cada módulo
        y_lines     — posiciones Y visuales de las líneas horizontales
    """
    shelf_map = {s.charola: s for s in shelves}

    # Agrupar charolas por Y físico
    y_groups: Dict[float, List[int]] = {}
    for c, s in shelf_map.items():
        y_groups.setdefault(s.y, []).append(c)

    # Altura visual por fila
    y_row_h: Dict[float, float] = {}
    for y_phys, charolas in y_groups.items():
        h = 0.0
        if "ALTO" in output_df.columns:
            for c in charolas:
                vals = output_df.loc[output_df["CHAROLA"] == c, "ALTO"].dropna()
                vals = vals[vals > 0]
                if len(vals):
                    h = max(h, float(vals.max()))
        if h <= 0:
            for c in charolas:
                dh = shelf_map[c].draw_height
                h  = max(h, dh if dh > 5.0 else 30.0)
        y_row_h[y_phys] = max(h, min_row_h)

    # Posiciones Y visuales (apilar de menor a mayor Y físico)
    sorted_y = sorted(y_groups)
    y_vis_map: Dict[float, float] = {}
    y_cursor = 0.0
    for y_phys in sorted_y:
        y_vis_map[y_phys] = y_cursor
        y_cursor += y_row_h[y_phys] + shelf_gap

    layout = {
        c: {"y_vis": y_vis_map[shelf_map[c].y], "h": y_row_h[shelf_map[c].y]}
        for c in shelf_map
    }

    total_width = max(s.x_abs_base + s.width for s in shelves)
    module_xs   = sorted(set(s.x_abs_base for s in shelves))
    y_lines     = [y_vis_map[y] for y in sorted_y] + [y_cursor - shelf_gap]

    return layout, total_width, module_xs, y_lines


def plot_planograma(
    output_df: pd.DataFrame,
    shelves: List[Shelf],
    title: str = "Planograma OXXO — GRASP",
    px_per_cm: float = 8.0,
    min_fig_width: float = 20.0,
    show_images: bool = True,
    show_labels: bool = True,
    show_product_borders: bool = True,
    show_vertical_dividers: bool = False,
    compact: bool = False,
    font_size: float = 5.5,
    dpi: int = 150,
) -> plt.Figure:
    """
    Genera la figura matplotlib del planograma en estilo comercial.

    La visualización respeta la grilla real del mueble:
      - Eje X: posición absoluta dentro del mueble (todos los módulos lado a lado).
      - Eje Y: charolas apiladas compactamente (altura = max ALTO de productos).

    Args:
        output_df:             DataFrame de decode() o CSV de referencia.
        shelves:               Lista de Shelf del formato.
        title:                 Título del planograma.
        px_per_cm:             Escala (puntos matplotlib por cm).
        min_fig_width:         Ancho mínimo de la figura en pulgadas.
        show_images:           Cargar imágenes de productos.
        show_labels:           Mostrar texto en los bloques de color.
        show_product_borders:  Borde en cada frente individual.
        show_vertical_dividers: Línea entre frentes del mismo producto.
        compact:               Productos llenan el alto de la charola.
        font_size:             Tamaño base de fuente.
        dpi:                   Resolución de la figura.
    """
    if output_df.empty or not shelves:
        fig, ax = plt.subplots(figsize=(8, 4), dpi=dpi)
        ax.set_facecolor("white")
        fig.patch.set_facecolor("white")
        ax.text(0.5, 0.5, "Sin datos para mostrar",
                ha="center", va="center", fontsize=12, color="#555555")
        ax.set_axis_off()
        return fig

    # Asegurar columna X_ABS
    output_df = _ensure_x_abs(output_df)

    layout, total_width, module_xs, y_lines = _compute_grid(output_df, shelves)
    shelf_map = {s.charola: s for s in shelves}

    y_vis_max = y_lines[-1]
    margin_x  = 3.0
    margin_y  = 2.0

    scale = px_per_cm / 72.0
    fig_w = max(min_fig_width, total_width * scale)
    fig_h = max(5.0, y_vis_max * scale * 1.20)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    # ── Fondos de charola (por fila completa) ────────────────────────────────
    shelf_fill = "#F5F5F5" if not compact else "#FAFAFA"
    # Agrupar charolas por Y físico para dibujar fondos por fila
    y_groups: Dict[float, List[int]] = {}
    for c, lay in layout.items():
        s = shelf_map[c]
        y_groups.setdefault(s.y, []).append(c)

    for y_phys, charolas in y_groups.items():
        c0  = charolas[0]
        lay = layout[c0]
        ax.add_patch(mpatches.Rectangle(
            (0, lay["y_vis"]), total_width, lay["h"],
            facecolor=shelf_fill, edgecolor="none", zorder=1,
        ))
        # Etiqueta de fila a la izquierda
        ax.text(
            -margin_x * 0.35, lay["y_vis"] + lay["h"] / 2,
            f"Y={int(y_phys)}",
            ha="right", va="center",
            fontsize=font_size, color="#333333", fontweight="bold",
        )

    # ── Borde exterior del mueble ─────────────────────────────────────────────
    ax.add_patch(mpatches.Rectangle(
        (0, 0), total_width, y_vis_max,
        facecolor="none", edgecolor="#111111",
        linewidth=3.0, zorder=10,
    ))

    # ── Líneas horizontales entre charolas ───────────────────────────────────
    for yp in y_lines:
        ax.hlines(yp, 0, total_width, colors="#111111", linewidth=2.0, zorder=9)

    # ── Separadores verticales de módulo ─────────────────────────────────────
    for x_mod in module_xs[1:]:          # omitir x=0 (borde izquierdo)
        ax.vlines(x_mod, 0, y_vis_max,
                  colors="#555555", linewidth=1.5, zorder=8)

    # ── Productos ────────────────────────────────────────────────────────────
    image_cache: Dict[str, Optional[np.ndarray]] = {}

    for _, row in output_df.iterrows():
        c = int(row["CHAROLA"])
        if c not in layout:
            continue

        lay      = layout[c]
        h_shelf  = lay["h"]
        y_shelf  = lay["y_vis"]

        x_abs    = float(row["X_ABS"])
        ancho_1  = float(row.get("ANCHO") or row.get("ANCHO_TOTAL") or 1.0)
        n_frentes = max(1, int(float(row.get("NUM_FRENTES", 1) or 1)))
        upc      = str(row["UPC_CVE"])
        name     = str(row.get("NAME") or row.get("ITEM_DESC") or upc)
        color    = _stable_color(upc)

        # Altura visual del producto
        if compact:
            h_product = h_shelf * 0.92
        else:
            alto = float(row.get("ALTO", 0) or 0)
            h_product = min(alto if alto > 0 else h_shelf * 0.92, h_shelf * 0.97)

        y_product = y_shelf          # productos descansan en la base de la charola

        # Imagen (cache por UPC)
        if show_images and upc not in image_cache:
            img_col = row.get("IMAGE_PATH") or row.get("IMAGE_URL")
            if img_col and str(img_col) not in ("nan", "None", ""):
                image_cache[upc] = _try_load_image(str(img_col))
            else:
                image_cache[upc] = None
        img_data = image_cache.get(upc) if show_images else None

        label = short_label(name, upc, max_chars=8) if show_labels else ""

        # Dibujar cada frente individualmente
        for i in range(n_frentes):
            x_frente = x_abs + i * ancho_1
            xp, yp   = 0.06, 0.06

            if img_data is not None:
                ax.imshow(
                    img_data,
                    extent=[x_frente + xp, x_frente + ancho_1 - xp,
                            y_product + yp, y_product + h_product - yp],
                    aspect="auto", zorder=3,
                )
                if show_product_borders:
                    ax.add_patch(mpatches.Rectangle(
                        (x_frente, y_product), ancho_1, h_product,
                        facecolor="none", edgecolor="#888888",
                        linewidth=0.4, zorder=4,
                    ))
            else:
                rect_w = max(ancho_1 - 2 * xp, 0.1)
                rect_h = max(h_product - 2 * yp, 0.1)
                edge_c = "white" if show_product_borders else color
                ax.add_patch(mpatches.FancyBboxPatch(
                    (x_frente + xp, y_product + yp),
                    rect_w, rect_h,
                    boxstyle="round,pad=0.06",
                    facecolor=color, edgecolor=edge_c,
                    linewidth=0.5, alpha=0.94, zorder=2,
                ))
                if label and ancho_1 >= 2.0:
                    fs       = max(font_size * 0.7, min(font_size, ancho_1 * 0.85))
                    rotation = 90 if h_product > ancho_1 * 2.0 else 0
                    ax.text(
                        x_frente + ancho_1 / 2,
                        y_product + h_product / 2,
                        label,
                        ha="center", va="center",
                        fontsize=fs, color="white", fontweight="bold",
                        rotation=rotation, zorder=5, clip_on=True,
                    )

            if show_vertical_dividers and i > 0:
                ax.vlines(x_frente, y_product + yp, y_product + h_product - yp,
                          colors="#CCCCCC", linewidth=0.4, zorder=5)

    # ── Ejes ─────────────────────────────────────────────────────────────────
    ax.set_xlim(-margin_x * 1.5, total_width + margin_x * 0.3)
    ax.set_ylim(-margin_y, y_vis_max + margin_y)
    ax.set_xlabel("Posición en el mueble (cm)", fontsize=font_size + 2, color="#444444")
    ax.set_title(title, fontsize=font_size + 7, fontweight="bold", pad=14, color="#111111")
    ax.xaxis.set_major_locator(ticker.MultipleLocator(55))
    ax.yaxis.set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#CCCCCC")
    ax.tick_params(axis="x", labelsize=font_size, colors="#666666")

    fig.tight_layout(pad=1.2)
    return fig


def save_planograma_png(fig: plt.Figure, path: str, dpi: int = 200) -> None:
    """Guarda el planograma como PNG de alta calidad."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")


def planograma_to_bytes(fig: plt.Figure, dpi: int = 150) -> bytes:
    """Retorna el planograma como bytes PNG para st.image o descarga."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    return buf.getvalue()
