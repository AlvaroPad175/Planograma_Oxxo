"""
data_loader.py — Carga y preparación de datos para el planograma OXXO.

Soporta dos formatos de entrada:
  - Formato A (single-file): un único CSV/Excel que contiene geometría de charolas
    y datos de producto en cada fila. Detectado por presencia de columnas Width y Height.
  - Formato B (two-files): CSV de productos + XLSX de charolas separados,
    como oxxo_1.csv + Caso de estudio TEC.xlsx.
"""
from __future__ import annotations

from pathlib import Path
from typing import IO, List, Optional, Tuple, Union

import pandas as pd

from .models import Product, Shelf
from .utils import safe_float, safe_int


# ─── Limpieza de columnas ────────────────────────────────────────────────────

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columnas: elimina BOM, arregla tildes mal codificadas."""
    rename = {}
    for c in df.columns:
        c2 = str(c).replace("﻿", "").replace("ï»¿", "").strip()
        c2 = c2.replace("TAMAÃ\x91O_POST", "TAMAÑO_POST")
        c2 = c2.replace("TAMAÃ'O_POST",    "TAMAÑO_POST")
        c2 = c2.replace("TAMANO_POST",     "TAMAÑO_POST")
        c2 = c2.replace("TAMANO",          "TAMAÑO")
        rename[c] = c2
    return df.rename(columns=rename)


def read_csv_safe(path_or_buffer) -> pd.DataFrame:
    """Lee un CSV probando encodings en orden: utf-8-sig, utf-8, latin1."""
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            if hasattr(path_or_buffer, "read"):
                path_or_buffer.seek(0)
            return clean_columns(pd.read_csv(path_or_buffer, encoding=enc))
        except UnicodeDecodeError:
            continue
    if hasattr(path_or_buffer, "read"):
        path_or_buffer.seek(0)
    return clean_columns(pd.read_csv(path_or_buffer))


def load_dataframe(path_or_buffer, filename: str = "") -> pd.DataFrame:
    """Carga CSV o Excel según extensión; normaliza columnas automáticamente."""
    name = filename or (str(path_or_buffer) if isinstance(path_or_buffer, (str, Path)) else "")
    if name.lower().endswith((".xlsx", ".xls")):
        df = clean_columns(pd.read_excel(path_or_buffer))
    else:
        df = read_csv_safe(path_or_buffer)
    return _normalize_aliases(df)


def _normalize_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Mapea alias a nombres canónicos sin modificar columnas que ya existen."""
    df = df.copy()
    if "UPC_CVE" not in df.columns and "ITEM" in df.columns:
        df["UPC_CVE"] = df["ITEM"]
    if "TAMAÑO" not in df.columns and "TAMAÑO_POST" in df.columns:
        df["TAMAÑO"] = df["TAMAÑO_POST"]
    # Output-format CSV uses NAME instead of ITEM_DESC
    if "ITEM_DESC" not in df.columns and "NAME" in df.columns:
        df["ITEM_DESC"] = df["NAME"]
    elif "ITEM_DESC" not in df.columns and "UPC_CVE" in df.columns:
        df["ITEM_DESC"] = df["UPC_CVE"]
    # Rellenar NaN en ITEM_DESC con UPC para que nunca quede vacío
    if "ITEM_DESC" in df.columns and "UPC_CVE" in df.columns:
        df["ITEM_DESC"] = df["ITEM_DESC"].fillna(df["UPC_CVE"])
    return df


# ─── Detección de formato ────────────────────────────────────────────────────

def is_single_file(df: pd.DataFrame) -> bool:
    """Devuelve True si el DataFrame contiene geometría de charolas integrada."""
    return "Width" in df.columns and "Height" in df.columns


# ─── Formatos disponibles ────────────────────────────────────────────────────

def get_available_formats(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve las combinaciones de formato únicas presentes en el DataFrame."""
    cols = ["SEGMENTO_ID", "MUEBLE_ID", "PLANOGRUPO", "TAMAÑO", "DIRECCION_LEGO_ID"]
    present = [c for c in cols if c in df.columns]
    if len(present) < 5:
        return pd.DataFrame(columns=cols + ["n_productos"])
    return (
        df.groupby(present)
        .size()
        .reset_index(name="n_productos")
        .sort_values("n_productos", ascending=False)
        .reset_index(drop=True)
    )


# ─── Filtrado ────────────────────────────────────────────────────────────────

def filter_by_format(
    df: pd.DataFrame,
    segmento: str,
    mueble: str,
    planogrupo: str,
    tamano: float,
    direccion: str,
) -> pd.DataFrame:
    mask = (
        (df["SEGMENTO_ID"].astype(str) == str(segmento))
        & (df["MUEBLE_ID"].astype(str) == str(mueble))
        & (df["PLANOGRUPO"].astype(str) == str(planogrupo))
        & (df["TAMAÑO"].astype(float) == float(tamano))
        & (df["DIRECCION_LEGO_ID"].astype(str) == str(direccion))
    )
    return df[mask].copy().reset_index(drop=True)


def filter_shelves_df(
    shelves_df: pd.DataFrame,
    mueble: str,
    planogrupo: str,
    tamano: float,
    direccion: str,
) -> pd.DataFrame:
    """Filtra el DataFrame de charolas (formato B, sin SEGMENTO_ID)."""
    df = shelves_df.copy()
    # Normalizar alias de tamaño en charolas
    if "TAMAÑO" not in df.columns and "TAMAÑO_POST" in df.columns:
        df["TAMAÑO"] = df["TAMAÑO_POST"]
    mask = (
        (df["MUEBLE_ID"].astype(str) == str(mueble))
        & (df["PLANOGRUPO"].astype(str) == str(planogrupo))
        & (df["TAMAÑO"].astype(float) == float(tamano))
        & (df["DIRECCION_LEGO_ID"].astype(str) == str(direccion))
    )
    return df[mask].copy().reset_index(drop=True)


# ─── Construcción de charolas ────────────────────────────────────────────────

def _build_shelves(shelf_source: pd.DataFrame) -> List[Shelf]:
    """
    Construye lista de Shelf desde un DataFrame con columnas Width/Height/X/Y/CHAROLA.
    También acepta el formato de salida del planograma (columnas X_ABS/X_LOCAL/ALTO/X_FIN_LOCAL).

    height    = clearance físico real, calculado desde el espaciado entre Y consecutivos
                cuando la columna Height está en unidades de visualización (< 5 cm típicamente).
    draw_height = valor original de Height, para dibujar el rectángulo de la charola.
    """
    has_width  = "Width"  in shelf_source.columns
    has_height = "Height" in shelf_source.columns

    # Precompute per-charola fallbacks when native Width/Height columns are absent
    _charola_width:  dict[int, float] = {}
    _charola_height: dict[int, float] = {}
    _charola_xbase:  dict[int, float] = {}
    if not has_width or not has_height:
        for ch_raw, grp in shelf_source.groupby("CHAROLA"):
            ch = safe_int(ch_raw)
            if not has_width:
                if "X_FIN_LOCAL" in grp.columns:
                    _charola_width[ch] = float(grp["X_FIN_LOCAL"].max())
                elif "ANCHO_TOTAL" in grp.columns:
                    _charola_width[ch] = float(grp["ANCHO_TOTAL"].sum())
                else:
                    _charola_width[ch] = 55.0
            if not has_height:
                if "ALTO" in grp.columns:
                    _charola_height[ch] = float(grp["ALTO"].max())
                else:
                    _charola_height[ch] = 30.0
            # X base: X_ABS - X_LOCAL (module origin)
            if "X" not in shelf_source.columns and "X_ABS" in grp.columns and "X_LOCAL" in grp.columns:
                _charola_xbase[ch] = float(grp["X_ABS"].iloc[0]) - float(grp["X_LOCAL"].iloc[0])

    # Mapa charola → primera fila representativa
    shelf_rows = {}
    for charola, grp in shelf_source.sort_values("CHAROLA").groupby("CHAROLA"):
        shelf_rows[safe_int(charola)] = grp.iloc[0]

    y_vals   = {c: safe_float(r["Y"]) for c, r in shelf_rows.items()}
    y_min    = min(y_vals.values())
    y_max    = max(y_vals.values())
    y_range  = max(float(y_max - y_min), 1.0)

    # Calcular espaciados Y entre charolas consecutivas
    y_sorted = sorted(set(y_vals.values()))
    y_spacings = {}
    for i, yv in enumerate(y_sorted):
        if i + 1 < len(y_sorted):
            y_spacings[yv] = y_sorted[i + 1] - yv
        else:
            y_spacings[yv] = y_spacings.get(y_sorted[i - 1], 42.0) if len(y_sorted) > 1 else 42.0

    if has_height:
        raw_heights = [safe_float(r["Height"]) for r in shelf_rows.values()]
    else:
        raw_heights = [_charola_height.get(c, 30.0) for c in shelf_rows]
    max_raw_h = max(raw_heights) if raw_heights else 0.0

    # Si el máximo Height de charola es muy pequeño (< 5 cm) se asume que está
    # en unidades de visualización (no en cm reales). En ese caso se desactiva
    # el chequeo de restricción de altura configurando height=inf en cada Shelf.
    # El atributo draw_height conserva el valor original para el dibujado.
    height_is_visual = max_raw_h < 5.0

    shelves: List[Shelf] = []
    for charola, row in sorted(shelf_rows.items()):
        y     = safe_float(row["Y"])
        raw_h = safe_float(row["Height"]) if has_height else _charola_height.get(charola, 30.0)
        shelf_w = safe_float(row["Width"]) if has_width else _charola_width.get(charola, 55.0)

        if "X" in shelf_source.columns:
            x_base = safe_float(row.get("X", 0.0))
        else:
            x_base = _charola_xbase.get(charola, 0.0)

        # height: hard check — inf cuando Height es visual (sin bloqueo por alto).
        # clearance: mejor estimado del espacio disponible, siempre derivado del
        #   gap Y.  Se usa para la penalización suave en incremental_score.
        gap_y    = y_spacings.get(y, 42.0)
        phys_h   = float("inf") if height_is_visual else raw_h
        clearance = gap_y  # siempre disponible, incluso cuando height=inf

        visibility = 1.0 + (y - y_min) / y_range
        shelves.append(Shelf(
            charola=charola,
            width=shelf_w,
            height=phys_h,
            draw_height=raw_h,
            x_abs_base=x_base,
            y=y,
            visibility=visibility,
            clearance=clearance,
        ))
    return shelves


# ─── Validación de productos ─────────────────────────────────────────────────

def _validate_products(
    df: pd.DataFrame,
    shelves: List[Shelf],
    min_frentes: int,
    max_frentes: int,
    max_variedad: Optional[int],
) -> Tuple[List[Product], List[dict]]:
    """
    Construye la lista de Product validados y la lista de no colocados con razón.

    Razones posibles:
      - 'No fue seleccionado por restricción de variedad'
      - 'No cabe por alto'
      - 'No cabe por ancho'
    """
    if max_variedad and max_variedad < len(df):
        excluded = df.iloc[max_variedad:].copy()
        df = df.iloc[:max_variedad].copy()
    else:
        excluded = pd.DataFrame()

    unplaced: List[dict] = []

    # Productos excluidos por variedad
    for _, r in excluded.iterrows():
        unplaced.append({
            "UPC_CVE": str(r["UPC_CVE"]),
            "ITEM_DESC": str(r.get("ITEM_DESC", r["UPC_CVE"])),
            "RAZON": "No fue seleccionado por restricción de variedad",
        })

    max_shelf_height = max((s.height for s in shelves), default=0.0)
    max_shelf_width = max((s.width for s in shelves), default=0.0)

    products: List[Product] = []

    for idx, r in df.reset_index(drop=True).iterrows():
        ancho = safe_float(r["ANCHO"])
        raw_frentes = safe_float(r["NUM_FRENTES"], 1.0)
        frentes = float(max(min_frentes, min(max_frentes, int(round(raw_frentes)))))
        w_total = ancho * frentes

        alto = None
        if "ALTO" in df.columns and pd.notna(r.get("ALTO")):
            alto = safe_float(r["ALTO"])

        sep = 0.0
        if "SEPARADOR" in df.columns and pd.notna(r.get("SEPARADOR")):
            sep = safe_float(r["SEPARADOR"])

        ancho_ocupado = w_total + sep
        upc = str(r["UPC_CVE"])
        _desc = r.get("ITEM_DESC")
        name = upc if (pd.isna(_desc) or str(_desc).strip().lower() == "nan") else str(_desc).strip()

        image_path = None
        for img_col in ("IMAGE_PATH", "IMAGE_URL"):
            if img_col in df.columns and pd.notna(r.get(img_col)):
                image_path = str(r[img_col])
                break

        # Validar factibilidad
        if alto is not None and alto > max_shelf_height + 1e-9:
            unplaced.append({"UPC_CVE": upc, "ITEM_DESC": name, "RAZON": "No cabe por alto"})
            continue
        if ancho_ocupado > max_shelf_width + 1e-9:
            unplaced.append({"UPC_CVE": upc, "ITEM_DESC": name, "RAZON": "No cabe por ancho"})
            continue

        products.append(Product(
            id=idx,
            upc=upc,
            name=name,
            ancho=ancho,
            num_frentes=frentes,
            width_total=w_total,
            separador=sep,
            ancho_ocupado=ancho_ocupado,
            hist_charola=safe_int(r["CHAROLA"]),
            hist_pos=safe_int(r["UBICACION_BANDEJA"]),
            alto=alto,
            image_path=image_path,
            grupo=str(r.get("PLANOGRUPO", "")),
            categoria=str(r.get("categoria_producto", "")),
        ))

    return products, unplaced


# ─── Puntos de entrada públicos ──────────────────────────────────────────────

def build_instance_single(
    df: pd.DataFrame,
    segmento: str,
    mueble: str,
    planogrupo: str,
    tamano: float,
    direccion: str,
    min_frentes: int = 1,
    max_frentes: int = 10,
    max_variedad: Optional[int] = None,
) -> Tuple[List[Product], List[Shelf], List[dict], str]:
    """
    Construye la instancia desde un único archivo combinado (formato A).
    Retorna (products, shelves, unplaced, warning_msg).
    """
    filtered = filter_by_format(df, segmento, mueble, planogrupo, tamano, direccion)
    if filtered.empty:
        return [], [], [], "No se encontraron productos para ese formato."

    shelves = _build_shelves(filtered)
    if not shelves:
        return [], [], [], "No se encontraron charolas para ese formato."

    # Deduplicar por UPC_CVE: conservar la fila de mayor NUM_FRENTES por producto
    if "UPC_CVE" in filtered.columns and filtered.duplicated("UPC_CVE").any():
        filtered = (
            filtered
            .sort_values("NUM_FRENTES", ascending=False)
            .drop_duplicates("UPC_CVE")
            .reset_index(drop=True)
        )

    products, unplaced = _validate_products(
        filtered, shelves, min_frentes, max_frentes, max_variedad
    )

    warning = ""
    total_ancho = sum(p.ancho_ocupado for p in products)
    total_cap = sum(s.width for s in shelves)
    if total_ancho > total_cap + 1e-9:
        warning = (
            f"⚠️ Instancia no factible: ancho total {total_ancho:.1f} cm "
            f"> capacidad {total_cap:.1f} cm. Reduce frentes o variedad."
        )

    return products, shelves, unplaced, warning


def build_instance_two_files(
    products_df: pd.DataFrame,
    shelves_df: pd.DataFrame,
    segmento: str,
    mueble: str,
    planogrupo: str,
    tamano: float,
    direccion: str,
    min_frentes: int = 1,
    max_frentes: int = 10,
    max_variedad: Optional[int] = None,
) -> Tuple[List[Product], List[Shelf], List[dict], str]:
    """
    Construye la instancia desde dos archivos separados (formato B).
    Retorna (products, shelves, unplaced, warning_msg).
    """
    pf = filter_by_format(products_df, segmento, mueble, planogrupo, tamano, direccion)
    sf = filter_shelves_df(shelves_df, mueble, planogrupo, tamano, direccion)

    if pf.empty:
        return [], [], [], "No se encontraron productos para ese formato."
    if sf.empty:
        return [], [], [], "No se encontraron charolas para ese formato."

    # Asegurar que pf tenga las columnas alias necesarias
    pf = _normalize_aliases(pf)
    if "ITEM_DESC" not in pf.columns:
        pf["ITEM_DESC"] = pf["UPC_CVE"]

    shelves = _build_shelves(sf)
    products, unplaced = _validate_products(
        pf, shelves, min_frentes, max_frentes, max_variedad
    )

    warning = ""
    total_ancho = sum(p.ancho_ocupado for p in products)
    total_cap = sum(s.width for s in shelves)
    if total_ancho > total_cap + 1e-9:
        warning = (
            f"⚠️ Instancia no factible: ancho total {total_ancho:.1f} cm "
            f"> capacidad {total_cap:.1f} cm. Reduce frentes o variedad."
        )

    return products, shelves, unplaced, warning
