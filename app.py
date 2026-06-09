"""
app.py — Planograma OXXO: Optimizador GRASP interactivo (Streamlit).

Uso:
    streamlit run app.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

# Asegura que src/ sea importable
sys.path.insert(0, str(Path(__file__).parent))

from src.data_loader import (
    build_instance_single,
    build_instance_two_files,
    filter_by_format,
    get_available_formats,
    is_single_file,
    load_dataframe,
    read_csv_safe,
)
from src.export import build_diagnostics, csv_bytes, png_bytes
from src.grasp_solver import GRASPPlanograma
from src.utils import fmt_tag
from src.visualization import planograma_to_bytes, plot_planograma

# ─── Configuración de página ─────────────────────────────────────────────────

st.set_page_config(
    page_title="Planograma OXXO — GRASP",
    page_icon="🛒",
    layout="wide",
)

EXAMPLE_PATH = Path(__file__).parent / "data" / "ejemplo_planograma.csv"

# ─── Helpers de estado ───────────────────────────────────────────────────────

def _reset_results():
    for key in ("output_df", "diag_df", "fig", "score", "unplaced_df"):
        st.session_state.pop(key, None)


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Configuración")

    # ── Carga de archivo ──────────────────────────────────────────────────
    st.subheader("1. Datos de entrada")

    input_mode = st.radio(
        "Modo de entrada",
        ["Archivo único (combinado)", "Dos archivos (productos + charolas)", "Formulario manual"],
        help=(
            "Archivo único: CSV/Excel con geometría de charola por fila. "
            "Dos archivos: CSV de productos + XLSX de charolas. "
            "Formulario manual: ingresa charolas y productos directamente en la app."
        ),
        on_change=_reset_results,
    )
    single_mode = input_mode.startswith("Archivo único")
    manual_mode = input_mode.startswith("Formulario")

    if manual_mode:
        uploaded_main    = None
        uploaded_shelves = None
        st.subheader("Parámetros del formato")
        _man_seg = st.text_input("Segmento ID", "HRN", key="man_seg")
        _man_mue = st.text_input("Mueble ID",   "CF",  key="man_mue")
        _man_pg  = st.text_input("Planogrupo",  "Refrescos", key="man_pg")
        _man_tam = st.number_input("Tamaño", min_value=0.1, max_value=99.0, value=5.0, step=0.5, key="man_tam")
        _man_dir = st.selectbox("Dirección", ["ID", "DI"], key="man_dir")
    elif single_mode:
        uploaded_main = st.file_uploader(
            "Sube tu archivo (CSV o Excel)",
            type=["csv", "xlsx", "xls"],
            key="upload_main",
            on_change=_reset_results,
        )
        uploaded_shelves = None
    else:
        uploaded_main = st.file_uploader(
            "Archivo de productos (CSV)",
            type=["csv"],
            key="upload_products",
            on_change=_reset_results,
        )
        uploaded_shelves = st.file_uploader(
            "Archivo de charolas (XLSX)",
            type=["xlsx", "xls"],
            key="upload_shelves",
            on_change=_reset_results,
        )

    # ── Carga de DataFrames ───────────────────────────────────────────────
    @st.cache_data(show_spinner=False)
    def _load_single(file_bytes: bytes, filename: str) -> pd.DataFrame:
        import io
        return load_dataframe(io.BytesIO(file_bytes), filename)

    @st.cache_data(show_spinner=False)
    def _load_shelves(file_bytes: bytes, filename: str) -> pd.DataFrame:
        import io
        return load_dataframe(io.BytesIO(file_bytes), filename)

    df_main: pd.DataFrame | None = None
    df_shelves: pd.DataFrame | None = None
    using_example = False

    if not manual_mode:
        if uploaded_main is not None:
            try:
                df_main = _load_single(uploaded_main.getvalue(), uploaded_main.name)
            except Exception as e:
                st.error(f"Error al leer el archivo principal: {e}")
        else:
            if EXAMPLE_PATH.exists():
                df_main = _load_single(EXAMPLE_PATH.read_bytes(), EXAMPLE_PATH.name)
                using_example = True
            else:
                st.warning("No se encontró el archivo de ejemplo. Sube un archivo.")

        if not single_mode and uploaded_shelves is not None:
            try:
                df_shelves = _load_shelves(uploaded_shelves.getvalue(), uploaded_shelves.name)
            except Exception as e:
                st.error(f"Error al leer el archivo de charolas: {e}")

        if using_example:
            st.info("📂 Usando archivo de ejemplo (ningún archivo cargado).")

    # ── Selector de formato ───────────────────────────────────────────────
    st.subheader("2. Formato")

    if manual_mode:
        SEG = st.session_state.get("man_seg", "HRN")
        MUE = st.session_state.get("man_mue", "CF")
        PG  = st.session_state.get("man_pg",  "Refrescos")
        TAM = float(st.session_state.get("man_tam", 5.0))
        DIR = st.session_state.get("man_dir", "ID")
        formato_df = None
        st.caption(f"Formato manual: **{SEG} | {MUE} | {PG} | T={TAM} | {DIR}**")
    else:
        formato_df: pd.DataFrame | None = None
        if df_main is not None:
            formato_df = get_available_formats(df_main)

        if formato_df is not None and not formato_df.empty:
            fmt_options = formato_df.apply(
                lambda r: f"{r['SEGMENTO_ID']} | {r['MUEBLE_ID']} | {r['PLANOGRUPO']} | T={r['TAMAÑO']} | {r['DIRECCION_LEGO_ID']}  ({int(r['n_productos'])} prod.)",
                axis=1,
            ).tolist()

            selected_fmt_label = st.selectbox(
                "Formato a optimizar",
                fmt_options,
                key="fmt_select",
                on_change=_reset_results,
            )
            fmt_row = formato_df.iloc[fmt_options.index(selected_fmt_label)]
            SEG  = str(fmt_row["SEGMENTO_ID"])
            MUE  = str(fmt_row["MUEBLE_ID"])
            PG   = str(fmt_row["PLANOGRUPO"])
            TAM  = float(fmt_row["TAMAÑO"])
            DIR  = str(fmt_row["DIRECCION_LEGO_ID"])
        else:
            st.warning("No se detectaron formatos. Verifica el archivo.")
            SEG = MUE = PG = DIR = ""
            TAM = 0.0

    # ── Parámetros GRASP ──────────────────────────────────────────────────
    st.subheader("3. Parámetros GRASP")

    col1, col2 = st.columns(2)
    with col1:
        alpha       = st.slider("Alpha (RCL)", 0.0, 1.0, 0.2, 0.05,
                                help="0 = greedy puro | 1 = aleatorio puro")
        max_iter    = st.number_input("Iteraciones GRASP", 1, 200, 20, 5)
    with col2:
        local_rounds = st.number_input("Rondas búsqueda local", 0, 100, 20, 5)
        seed         = st.number_input("Semilla (seed)", 0, 9999, 42)

    col3, col4 = st.columns(2)
    with col3:
        lambda_hist = st.slider("Peso histórico (λ)", 0.0, 5.0, 1.0, 0.1)
    with col4:
        beta_vis    = st.slider("Peso visibilidad (β)", 0.0, 1.0, 0.10, 0.01)

    # ── Restricciones de productos ────────────────────────────────────────
    st.subheader("4. Frentes y variedad")

    col5, col6 = st.columns(2)
    with col5:
        min_frentes = st.number_input(
            "Frentes mínimos", 1, 10, 1,
            help="Número mínimo de frentes que debe tener cada producto en el planograma.",
        )
    with col6:
        max_frentes = st.number_input(
            "Frentes máximos", 1, 20, 4,
            help="Número máximo de frentes por producto. Sube este valor para llenar mejor las charolas.",
        )

    use_variedad = st.checkbox(
        "Limitar variedad de productos", value=False,
        help="Activa esto para incluir solo los N productos más relevantes.",
    )
    max_variedad = None
    if use_variedad:
        max_variedad = st.number_input("Máximo de productos distintos", 1, 500, 50)

    # ── Botón ─────────────────────────────────────────────────────────────
    st.divider()
    run_btn = st.button("🚀 Generar planograma", type="primary", use_container_width=True)


# ─── Panel principal ──────────────────────────────────────────────────────────

st.title("🛒 Planograma OXXO — Optimizador GRASP")

# ── Modo formulario manual: editores de tabla ─────────────────────────────────
_DEFAULT_SHELVES = pd.DataFrame({
    "CHAROLA":  [1,     2,     3,     4,     5    ],
    "Width":    [150.0, 150.0, 150.0, 150.0, 150.0],
    "Height":   [35.0,  35.0,  35.0,  35.0,  35.0 ],
    "X":        [0.0,   0.0,   0.0,   0.0,   0.0  ],
    "Y":        [0.0,   35.0,  70.0,  105.0, 140.0],
})

_DEFAULT_PRODUCTS = pd.DataFrame({
    "UPC_CVE":          ["001",        "002",        "003",        "004",        "005"       ],
    "ITEM_DESC":        ["Producto A", "Producto B", "Producto C", "Producto D", "Producto E"],
    "ANCHO":            [8.5,  7.0,  9.0,  6.5,  10.0],
    "NUM_FRENTES":      [1,    2,    1,    1,    1   ],
    "SEPARADOR":        [1.0,  1.0,  1.0,  1.0,  1.0 ],
    "ALTO":             [25.0, 20.0, 30.0, 22.0, 28.0],
    "CHAROLA":          [1,    1,    2,    2,    3   ],
    "UBICACION_BANDEJA":[1,    2,    1,    2,    1   ],
})

manual_shelves_df   = None
manual_products_df  = None

if manual_mode:
    st.markdown(
        "Define las **charolas** y **productos** directamente en las tablas de abajo, "
        "luego pulsa **Generar planograma** en el sidebar."
    )

    st.subheader("Charolas")
    st.caption("Agrega o elimina filas con los botones de la tabla. `Width` y `Height` en cm.")
    manual_shelves_df = st.data_editor(
        _DEFAULT_SHELVES,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_shelves",
        column_config={
            "CHAROLA": st.column_config.NumberColumn("Charola", min_value=1, step=1),
            "Width":   st.column_config.NumberColumn("Ancho (cm)", min_value=1.0),
            "Height":  st.column_config.NumberColumn("Alto (cm)",  min_value=1.0),
            "X":       st.column_config.NumberColumn("X base (cm)"),
            "Y":       st.column_config.NumberColumn("Y posición (cm)"),
        },
    )

    st.subheader("Productos")
    st.caption("Cada fila es un producto. `CHAROLA` y `UBICACION_BANDEJA` son el histórico (posición de referencia).")
    manual_products_df = st.data_editor(
        _DEFAULT_PRODUCTS,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_products",
        column_config={
            "UPC_CVE":           st.column_config.TextColumn("UPC / ID"),
            "ITEM_DESC":         st.column_config.TextColumn("Nombre"),
            "ANCHO":             st.column_config.NumberColumn("Ancho (cm)", min_value=0.1),
            "NUM_FRENTES":       st.column_config.NumberColumn("Frentes", min_value=1, step=1),
            "SEPARADOR":         st.column_config.NumberColumn("Separador (cm)", min_value=0.0),
            "ALTO":              st.column_config.NumberColumn("Alto (cm)", min_value=0.0),
            "CHAROLA":           st.column_config.NumberColumn("Charola hist.", min_value=1, step=1),
            "UBICACION_BANDEJA": st.column_config.NumberColumn("Posición hist.", min_value=1, step=1),
        },
    )

elif df_main is None:
    st.info("Sube un archivo o cambia a **Formulario manual** en el sidebar.")
    st.stop()
else:
    st.markdown(
        "Selecciona el formato en la barra lateral y pulsa **Generar planograma**."
    )
    # ── Vista previa de datos ────────────────────────────────────────────
    with st.expander("Vista previa del archivo cargado", expanded=False):
        fmt_type = "archivo único (combinado)" if is_single_file(df_main) else "dos archivos"
        st.caption(f"Formato detectado: **{fmt_type}** — {df_main.shape[0]:,} filas × {df_main.shape[1]} columnas")
        st.dataframe(df_main.head(10), use_container_width=True)

    # ── Diagnóstico del formato seleccionado ─────────────────────────────
    if formato_df is not None and not formato_df.empty and SEG:
        with st.expander("Diagnóstico del formato seleccionado", expanded=False):
            st.dataframe(formato_df, use_container_width=True)

# ── Editor de charolas del mueble ─────────────────────────────────────────────
# Visible para modo archivo único cuando hay formato seleccionado.
# En modo manual las charolas ya se editan en la tabla de arriba.
shelf_override_df: pd.DataFrame | None = None

if not manual_mode and df_main is not None and SEG:
    with st.expander("⚙️ Dimensiones del mueble (editable antes de optimizar)", expanded=False):
        st.caption(
            "Aquí puedes ajustar el **ancho** y **alto** de cada charola antes de correr el GRASP. "
            "Los valores vienen del archivo cargado; modifícalos si quieres probar otro tamaño de refrigerador."
        )

        # Obtener charolas del formato actual (sin construir toda la instancia)
        try:
            _filt = filter_by_format(df_main, SEG, MUE, PG, TAM, DIR)
            if not _filt.empty:
                _shelf_cols = [c for c in ["CHAROLA", "Width", "Height", "X", "Y"] if c in _filt.columns]
                _shelf_preview = (
                    _filt[_shelf_cols]
                    .groupby("CHAROLA").first()
                    .reset_index()
                    .sort_values(["Y", "X", "CHAROLA"])
                    .reset_index(drop=True)
                )
                _shelf_preview = _shelf_preview.rename(columns={
                    "Width":  "Ancho_cm",
                    "Height": "Alto_cm",
                })

                shelf_override_df = st.data_editor(
                    _shelf_preview,
                    num_rows="fixed",
                    use_container_width=True,
                    key=f"shelf_edit_{SEG}_{MUE}_{PG}_{TAM}_{DIR}",
                    column_config={
                        "CHAROLA":  st.column_config.NumberColumn("Charola", disabled=True),
                        "Ancho_cm": st.column_config.NumberColumn("Ancho (cm)", min_value=1.0, step=0.5),
                        "Alto_cm":  st.column_config.NumberColumn("Alto / clearance (cm)", min_value=1.0, step=0.5),
                        "X":        st.column_config.NumberColumn("X módulo (cm)", disabled=True),
                        "Y":        st.column_config.NumberColumn("Y posición (cm)", disabled=True),
                    },
                )
                # Ancho total del mueble = max(X_base + Ancho) — no la suma de todas las charolas
                if "X" in _shelf_preview.columns:
                    _total_w_mueble = (_shelf_preview["X"] + _shelf_preview["Ancho_cm"]).max()
                else:
                    _total_w_mueble = _shelf_preview["Ancho_cm"].max()
                st.caption(
                    f"**{len(_shelf_preview)} charolas** · "
                    f"Ancho del mueble: **{_total_w_mueble:.0f} cm** · "
                    f"Módulos únicos: **{_shelf_preview['X'].nunique() if 'X' in _shelf_preview.columns else '—'}**"
                    f"  —  Las columnas **Ancho** y **Alto** son editables; haz clic en una celda para modificar."
                )
        except Exception:
            st.info("Selecciona un formato válido para ver las charolas.")

# ─── Ejecución del GRASP ──────────────────────────────────────────────────────

if run_btn and SEG:
    _reset_results()

    # Construir instancia
    try:
        if manual_mode:
            if manual_shelves_df is None or manual_shelves_df.empty:
                st.error("La tabla de charolas está vacía.")
                st.stop()
            if manual_products_df is None or manual_products_df.empty:
                st.error("La tabla de productos está vacía.")
                st.stop()
            # Añadir columnas de formato para que el filtro pase todo
            _pf = manual_products_df.copy()
            _pf["SEGMENTO_ID"]       = SEG
            _pf["MUEBLE_ID"]         = MUE
            _pf["PLANOGRUPO"]        = PG
            _pf["TAMAÑO"]            = TAM
            _pf["DIRECCION_LEGO_ID"] = DIR
            if "ITEM_DESC" not in _pf.columns:
                _pf["ITEM_DESC"] = _pf["UPC_CVE"]
            _sf = manual_shelves_df.copy()
            _sf["MUEBLE_ID"]         = MUE
            _sf["PLANOGRUPO"]        = PG
            _sf["TAMAÑO_POST"]       = TAM
            _sf["DIRECCION_LEGO_ID"] = DIR
            products, shelves, unplaced, warning = build_instance_two_files(
                _pf, _sf, SEG, MUE, PG, TAM, DIR,
                min_frentes=int(min_frentes),
                max_frentes=int(max_frentes),
                max_variedad=int(max_variedad) if max_variedad else None,
            )
        elif single_mode or (df_shelves is None):
            products, shelves, unplaced, warning = build_instance_single(
                df_main, SEG, MUE, PG, TAM, DIR,
                min_frentes=int(min_frentes),
                max_frentes=int(max_frentes),
                max_variedad=int(max_variedad) if max_variedad else None,
            )
        else:
            products, shelves, unplaced, warning = build_instance_two_files(
                df_main, df_shelves, SEG, MUE, PG, TAM, DIR,
                min_frentes=int(min_frentes),
                max_frentes=int(max_frentes),
                max_variedad=int(max_variedad) if max_variedad else None,
            )
    except Exception as e:
        st.error(f"Error construyendo la instancia: {e}")
        st.stop()

    # Aplicar overrides de dimensiones de charola (si el usuario las editó)
    if shelf_override_df is not None and not shelf_override_df.empty and not manual_mode:
        from dataclasses import replace as _dc_replace
        _ov_map = {int(r["CHAROLA"]): r for _, r in shelf_override_df.iterrows()}
        shelves = [
            _dc_replace(
                s,
                width=float(_ov_map[s.charola]["Ancho_cm"]),
                height=float("inf"),          # el GRASP no rechaza por alto
                draw_height=float(_ov_map[s.charola]["Alto_cm"]),
            ) if s.charola in _ov_map else s
            for s in shelves
        ]


    if warning:
        total_w   = sum(p.ancho_ocupado for p in products)
        total_cap = sum(s.width for s in shelves)
        st.warning(warning)
        st.info(
            f"**Ancho total de productos:** {total_w:.1f} cm  |  "
            f"**Capacidad de charolas:** {total_cap:.1f} cm\n\n"
            "Para resolver esto puedes:\n"
            "- Reducir **Frentes máximos** en el sidebar (prueba con `1`).\n"
            "- Activar **Limitar variedad** y reducir el número de productos.\n\n"
            "El GRASP no se ejecutará hasta que la instancia sea factible."
        )
        st.stop()

    if not products:
        st.error("No hay productos válidos para el formato seleccionado.")
        st.stop()

    if not shelves:
        st.error("No hay charolas para el formato seleccionado.")
        st.stop()

    # Ejecutar GRASP
    solver = GRASPPlanograma(
        products=products,
        shelves=shelves,
        direction=DIR,
        segmento=SEG,
        mueble=MUE,
        planogrupo=PG,
        tamano=TAM,
        alpha=float(alpha),
        lambda_hist=float(lambda_hist),
        beta_visibility=float(beta_vis),
        random_seed=int(seed),
    )

    progress_bar = st.progress(0, text="Iniciando GRASP…")
    status_text  = st.empty()

    def _progress_cb(it: int, total: int, score: float, best: float):
        pct = int(it / total * 100)
        progress_bar.progress(pct, text=f"Iteración {it}/{total} — score={score:+.4f} | mejor={best:+.4f}")

    try:
        with st.spinner("Optimizando planograma…"):
            best_sol, best_score = solver.run(
                max_iter=int(max_iter),
                local_rounds=int(local_rounds),
                progress_cb=_progress_cb,
            )
    except RuntimeError as e:
        progress_bar.empty()
        st.error(f"El GRASP no pudo colocar todos los productos: {e}")
        st.info(
            "Esto ocurre cuando la capacidad de las charolas no alcanza para todos los productos. "
            "Prueba reducir **Frentes máximos** a `1` o activar **Limitar variedad**."
        )
        st.stop()
    except Exception as e:
        progress_bar.empty()
        st.error(f"Error inesperado en el GRASP: {traceback.format_exc()}")
        st.stop()

    progress_bar.progress(100, text="¡Optimización completada!")

    output_df = solver.decode(best_sol).sort_values(["CHAROLA", "UBICACION_BANDEJA"])
    diag_df   = build_diagnostics(output_df, shelves)
    fig       = plot_planograma(
        output_df, shelves,
        title=f"Planograma — {SEG} | {MUE} | {PG} | T={int(TAM)} | {DIR}",
    )

    st.session_state["output_df"]   = output_df
    st.session_state["diag_df"]     = diag_df
    st.session_state["fig"]         = fig
    st.session_state["score"]       = best_score
    st.session_state["unplaced_df"] = pd.DataFrame(unplaced) if unplaced else pd.DataFrame()
    st.session_state["shelves"]     = shelves
    st.session_state["fmt_tag"]     = fmt_tag(SEG, MUE, PG, TAM, DIR)

# ─── Resultados ───────────────────────────────────────────────────────────────

if "output_df" in st.session_state:
    output_df   = st.session_state["output_df"]
    diag_df     = st.session_state["diag_df"]
    fig         = st.session_state["fig"]
    score       = st.session_state["score"]
    unplaced_df = st.session_state.get("unplaced_df", pd.DataFrame())
    shelves_res = st.session_state.get("shelves", [])
    tag         = st.session_state.get("fmt_tag", "planograma")

    # ── Visualización del planograma ──────────────────────────────────────
    st.subheader("Planograma")

    with st.expander("⚙️ Opciones visuales", expanded=False):
        _vc1, _vc2, _vc3 = st.columns(3)
        with _vc1:
            vis_px_cm  = st.slider("Escala (px/cm)", 6.0, 24.0, 12.0, 0.5,
                                   key="vis_px_cm")
            vis_font   = st.slider("Tamaño fuente", 4.0, 12.0, 6.0, 0.5,
                                   key="vis_font")
        with _vc2:
            vis_labels   = st.checkbox("Mostrar etiquetas",      True,  key="vis_labels")
            vis_borders  = st.checkbox("Mostrar bordes",         True,  key="vis_borders")
            vis_dividers = st.checkbox("Divisores entre frentes", False, key="vis_dividers")
        with _vc3:
            vis_compact = st.checkbox("Modo compacto", False, key="vis_compact")
            vis_images  = st.checkbox("Cargar imágenes", True, key="vis_images")
            vis_dpi     = st.select_slider("DPI exportación", [100, 150, 200, 300], 150,
                                           key="vis_dpi")

    # Reconstruir título desde el DataFrame de resultados
    _seg  = output_df["SEGMENTO_ID"].iloc[0]       if "SEGMENTO_ID"       in output_df.columns else ""
    _mue  = output_df["MUEBLE_ID"].iloc[0]         if "MUEBLE_ID"         in output_df.columns else ""
    _pg   = output_df["PLANOGRUPO"].iloc[0]        if "PLANOGRUPO"        in output_df.columns else ""
    _tam  = output_df["TAMAÑO"].iloc[0]            if "TAMAÑO"            in output_df.columns else ""
    _dir  = output_df["DIRECCION_LEGO_ID"].iloc[0] if "DIRECCION_LEGO_ID" in output_df.columns else ""
    _vis_title = f"Planograma — {_seg} | {_mue} | {_pg} | T={_tam} | {_dir}".strip(" |")

    vis_fig = plot_planograma(
        output_df, shelves_res,
        title=_vis_title,
        px_per_cm=vis_px_cm,
        show_images=vis_images,
        show_labels=vis_labels,
        show_product_borders=vis_borders,
        show_vertical_dividers=vis_dividers,
        compact=vis_compact,
        font_size=vis_font,
        dpi=vis_dpi,
    )
    st.pyplot(vis_fig, use_container_width=True)

    # ── Métricas ──────────────────────────────────────────────────────────
    st.subheader("Métricas")

    total_productos  = len(output_df["UPC_CVE"].unique())
    total_colocados  = len(output_df)
    total_no_col     = len(unplaced_df) if not unplaced_df.empty else 0
    cap_total        = sum(s.width for s in shelves_res)
    ancho_col   = "ANCHO_NETO" if "ANCHO_NETO" in output_df.columns else "ANCHO_TOTAL"
    ancho_usado = output_df[ancho_col].sum()
    pct_ocupacion    = ancho_usado / cap_total * 100 if cap_total > 0 else 0
    holgura_min      = diag_df["HOLGURA"].min() if not diag_df.empty else 0.0

    col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
    col_a.metric("Productos únicos",   total_productos)
    col_b.metric("Colocados",          total_colocados)
    col_c.metric("No colocados",       total_no_col)
    col_d.metric("Ocupación",          f"{pct_ocupacion:.1f}%")
    col_e.metric("Holgura mínima",     f"{holgura_min:.2f} cm")
    col_f.metric("Score GRASP",        f"{score:+.4f}")

    # ── Tabla de diagnóstico ──────────────────────────────────────────────
    st.subheader("Diagnóstico por charola")
    st.dataframe(
        diag_df.style.applymap(
            lambda v: "background-color: #ffcccc" if v is False else "",
            subset=["ES_FACTIBLE"],
        ),
        use_container_width=True,
    )

    # ── Productos no colocados ────────────────────────────────────────────
    if not unplaced_df.empty:
        st.subheader("Productos no colocados")
        st.dataframe(unplaced_df, use_container_width=True)
    else:
        st.success("✅ Todos los productos fueron colocados.")

    # ── Descargas ─────────────────────────────────────────────────────────
    st.subheader("Descargas")
    col_dl1, col_dl2, col_dl3 = st.columns(3)

    with col_dl1:
        st.download_button(
            label="📥 CSV Planograma",
            data=csv_bytes(output_df),
            file_name=f"planograma_{tag}.csv",
            mime="text/csv",
        )

    with col_dl2:
        st.download_button(
            label="📥 CSV Diagnóstico",
            data=csv_bytes(diag_df),
            file_name=f"diagnostico_{tag}.csv",
            mime="text/csv",
        )

    with col_dl3:
        st.download_button(
            label="🖼️ PNG Planograma",
            data=planograma_to_bytes(vis_fig, dpi=vis_dpi),
            file_name=f"planograma_{tag}.png",
            mime="image/png",
        )

    # ── Tabla de resultados completa ──────────────────────────────────────
    with st.expander("Ver tabla de resultados completa", expanded=False):
        st.dataframe(output_df, use_container_width=True)


# ─── Visor de resultados previos ──────────────────────────────────────────────

st.divider()
with st.expander("📂 Visualizar planograma existente (cargar CSV)", expanded=False):
    st.caption(
        "Carga un CSV de planograma generado previamente (salida_grasp_*.csv). "
        "Opcionalmente sube también el CSV de diagnóstico para obtener los anchos reales de charola."
    )
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        viewer_plan_file = st.file_uploader(
            "CSV de planograma", type=["csv"], key="viewer_plan"
        )
    with col_v2:
        viewer_diag_file = st.file_uploader(
            "CSV de diagnóstico (opcional)", type=["csv"], key="viewer_diag"
        )

    if viewer_plan_file is not None:
        try:
            import io as _io
            from src.models import Shelf as _Shelf

            vdf = read_csv_safe(_io.BytesIO(viewer_plan_file.getvalue()))

            # Normalizar columna de nombre si no existe
            if "NAME" not in vdf.columns and "ITEM_DESC" in vdf.columns:
                vdf["NAME"] = vdf["ITEM_DESC"]
            elif "NAME" not in vdf.columns:
                vdf["NAME"] = vdf["UPC_CVE"].astype(str)

            # Cargar diagnóstico si se subió
            vdiag = None
            if viewer_diag_file is not None:
                vdiag = read_csv_safe(_io.BytesIO(viewer_diag_file.getvalue()))

            # ── Reconstruir charolas ──────────────────────────────────────
            charola_y     = vdf.groupby("CHAROLA")["Y"].first().sort_index()
            charola_x_fin = vdf.groupby("CHAROLA")["X_FIN_LOCAL"].max()

            if vdiag is not None and "ANCHO_CAPACIDAD" in vdiag.columns:
                charola_w = vdiag.set_index("CHAROLA")["ANCHO_CAPACIDAD"]
            else:
                charola_w = charola_x_fin  # aproximación con el último X

            y_sorted  = sorted(charola_y.values)
            y_spacing = {}
            for i, yv in enumerate(y_sorted):
                if i + 1 < len(y_sorted):
                    y_spacing[yv] = y_sorted[i + 1] - yv
                else:
                    prev = y_sorted[i - 1] if len(y_sorted) > 1 else yv
                    y_spacing[yv] = y_spacing.get(prev, 35.0)

            y_min   = min(charola_y.values)
            y_max   = max(charola_y.values)
            y_range = max(float(y_max - y_min), 1.0)

            vshelves = []
            for ch in sorted(charola_y.index):
                yv  = float(charola_y[ch])
                w   = float(charola_w.get(ch, charola_x_fin.get(ch, 150.0)))
                dh  = y_spacing.get(yv, 35.0)
                vshelves.append(_Shelf(
                    charola=int(ch),
                    width=w,
                    height=float("inf"),
                    draw_height=dh,
                    x_abs_base=0.0,
                    y=yv,
                    visibility=1.0 + (yv - y_min) / y_range,
                ))

            # ── Título del planograma ─────────────────────────────────────
            for col in ("SEGMENTO_ID", "MUEBLE_ID", "PLANOGRUPO", "TAMAÑO", "DIRECCION_LEGO_ID"):
                if col not in vdf.columns:
                    vdf[col] = ""
            vtitle = (
                f"{vdf['SEGMENTO_ID'].iloc[0]} | {vdf['MUEBLE_ID'].iloc[0]} | "
                f"{vdf['PLANOGRUPO'].iloc[0]} | T={vdf['TAMAÑO'].iloc[0]} | "
                f"{vdf['DIRECCION_LEGO_ID'].iloc[0]}"
            ).strip(" |")

            with st.expander("⚙️ Opciones visuales", expanded=False):
                _vvc1, _vvc2, _vvc3 = st.columns(3)
                with _vvc1:
                    vv_px_cm = st.slider("Escala (px/cm)", 6.0, 24.0, 12.0, 0.5,
                                         key="vv_px_cm")
                    vv_font  = st.slider("Tamaño fuente", 4.0, 12.0, 6.0, 0.5,
                                         key="vv_font")
                with _vvc2:
                    vv_labels   = st.checkbox("Mostrar etiquetas",       True,  key="vv_labels")
                    vv_borders  = st.checkbox("Mostrar bordes",          True,  key="vv_borders")
                    vv_dividers = st.checkbox("Divisores entre frentes", False, key="vv_dividers")
                with _vvc3:
                    vv_compact = st.checkbox("Modo compacto", False, key="vv_compact")
                    vv_images  = st.checkbox("Cargar imágenes", True, key="vv_images")
                    vv_dpi     = st.select_slider("DPI exportación", [100, 150, 200, 300], 150,
                                                  key="vv_dpi")

            vfig = plot_planograma(
                vdf, vshelves,
                title=f"Planograma — {vtitle}",
                px_per_cm=vv_px_cm,
                show_images=vv_images,
                show_labels=vv_labels,
                show_product_borders=vv_borders,
                show_vertical_dividers=vv_dividers,
                compact=vv_compact,
                font_size=vv_font,
                dpi=vv_dpi,
            )
            st.pyplot(vfig, use_container_width=True)

            # ── Métricas rápidas ──────────────────────────────────────────
            vcol_a, vcol_b, vcol_c = st.columns(3)
            vcol_a.metric("Charolas", len(vshelves))
            vcol_b.metric("Productos únicos", vdf["UPC_CVE"].nunique())
            vcol_c.metric("Total posiciones", len(vdf))

            if vdiag is not None:
                st.dataframe(vdiag, use_container_width=True)

            st.download_button(
                "🖼️ Descargar PNG",
                data=planograma_to_bytes(vfig, dpi=vv_dpi),
                file_name=f"vis_{viewer_plan_file.name.replace('.csv', '')}.png",
                mime="image/png",
            )

        except Exception as _e:
            st.error(f"Error al visualizar: {_e}")
