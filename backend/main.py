"""
backend/main.py — FastAPI backend para el Optimizador de Planogramas OXXO.

Endpoints:
  GET  /health
  GET  /api/example-formats
  POST /api/upload
  POST /api/shelves
  POST /api/optimize          → {task_id}
  GET  /api/progress/{id}     → SSE stream
  GET  /api/result/{id}       → JSON completo
  GET  /api/result/{id}/csv
  GET  /api/result/{id}/diag-csv
"""
from __future__ import annotations

import asyncio
import io
import json
import queue
import sys
import threading
import traceback
import uuid
from dataclasses import replace as _dc_replace
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_loader import (
    build_instance_single,
    filter_by_format,
    get_available_formats,
    load_dataframe,
)
from src.export import build_diagnostics, csv_bytes
from src.grasp_solver import GRASPPlanograma
from src.models import Shelf
from src.utils import fmt_tag

from .schemas import (
    DiagRow,
    FormatOption,
    Metrics,
    OptimizeRequest,
    OptimizeResult,
    ProductAssignment,
    ShelfInfo,
    UnplacedProduct,
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Planograma OXXO — API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory stores ──────────────────────────────────────────────────────────

_uploads: Dict[str, Dict[str, Any]] = {}  # file_id → {df, filename}
_tasks: Dict[str, Dict[str, Any]] = {}    # task_id → {queue, result, done}

EXAMPLE_PATH = Path(__file__).parent.parent / "data" / "ejemplo_planograma.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_format_list(fmt_df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in fmt_df.iterrows():
        rows.append({
            "key":   f"{r['SEGMENTO_ID']}|{r['MUEBLE_ID']}|{r['PLANOGRUPO']}|{r['TAMAÑO']}|{r['DIRECCION_LEGO_ID']}",
            "label": f"{r['SEGMENTO_ID']} | {r['MUEBLE_ID']} | {r['PLANOGRUPO']} | T={r['TAMAÑO']} | {r['DIRECCION_LEGO_ID']} ({int(r['n_productos'])} prod.)",
            "seg":   str(r["SEGMENTO_ID"]),
            "mue":   str(r["MUEBLE_ID"]),
            "pg":    str(r["PLANOGRUPO"]),
            "tam":   float(r["TAMAÑO"]),
            "dir":   str(r["DIRECCION_LEGO_ID"]),
            "n":     int(r["n_productos"]),
        })
    return rows


def _register_file(df: pd.DataFrame, filename: str) -> tuple[str, list]:
    file_id = str(uuid.uuid4())
    _uploads[file_id] = {"df": df, "filename": filename}
    fmt_df = get_available_formats(df)
    return file_id, _to_format_list(fmt_df)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/example-formats")
def example_formats():
    if not EXAMPLE_PATH.exists():
        raise HTTPException(404, "Archivo de ejemplo no encontrado.")
    df = load_dataframe(str(EXAMPLE_PATH), EXAMPLE_PATH.name)
    file_id, formats = _register_file(df, EXAMPLE_PATH.name)
    return {"file_id": file_id, "filename": EXAMPLE_PATH.name, "formats": formats}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    try:
        df = load_dataframe(io.BytesIO(content), file.filename or "upload.csv")
    except Exception as e:
        raise HTTPException(400, f"Error al leer el archivo: {e}")
    file_id, formats = _register_file(df, file.filename or "upload.csv")
    return {"file_id": file_id, "filename": file.filename, "formats": formats}


@app.post("/api/shelves")
def get_shelves(body: dict):
    file_id = body.get("file_id")
    if file_id not in _uploads:
        raise HTTPException(404, "Archivo no encontrado. Vuelve a cargar.")
    df = _uploads[file_id]["df"]
    seg, mue, pg = body["seg"], body["mue"], body["pg"]
    tam, dir_ = float(body["tam"]), body["dir"]

    filt = filter_by_format(df, seg, mue, pg, tam, dir_)
    if filt.empty:
        raise HTTPException(404, "No hay charolas para ese formato.")

    has_width  = "Width"  in filt.columns
    has_height = "Height" in filt.columns
    has_x      = "X"      in filt.columns

    # Detectar si Height está en unidades visuales (< 5 cm)
    height_is_visual = has_height and float(filt["Height"].max()) < 5.0

    # Calcular Y-spacings para derivar clearance cuando Height es visual
    y_vals  = sorted(filt["Y"].unique()) if "Y" in filt.columns else [0.0]
    y_gaps: dict = {}
    for i, yv in enumerate(y_vals):
        if i + 1 < len(y_vals):
            y_gaps[yv] = y_vals[i + 1] - yv
        else:
            y_gaps[yv] = y_gaps.get(y_vals[i - 1], 42.0) if len(y_vals) > 1 else 42.0

    charola_grps = filt.groupby("CHAROLA")
    rows = []
    for ch, grp in charola_grps:
        row: dict = {"CHAROLA": ch}
        y_val = float(grp["Y"].iloc[0]) if "Y" in grp.columns else 0.0
        row["Y"] = y_val

        if has_width:
            row["Ancho_cm"] = float(grp["Width"].iloc[0])
        elif "X_FIN_LOCAL" in grp.columns:
            row["Ancho_cm"] = float(grp["X_FIN_LOCAL"].max())
        elif "ANCHO_TOTAL" in grp.columns:
            row["Ancho_cm"] = float(grp["ANCHO_TOTAL"].sum())
        else:
            row["Ancho_cm"] = 55.0

        if height_is_visual:
            # Mostrar el clearance real derivado del gap Y en lugar del valor visual (2.5)
            row["Alto_cm"] = round(y_gaps.get(y_val, 42.0), 1)
        elif has_height:
            row["Alto_cm"] = float(grp["Height"].iloc[0])
        elif "ALTO" in grp.columns:
            row["Alto_cm"] = float(grp["ALTO"].max())
        else:
            row["Alto_cm"] = 30.0

        if has_x:
            row["X"] = float(grp["X"].iloc[0])
        elif "X_ABS" in grp.columns and "X_LOCAL" in grp.columns:
            row["X"] = float(grp["X_ABS"].iloc[0]) - float(grp["X_LOCAL"].iloc[0])
        else:
            row["X"] = 0.0

        rows.append(row)

    preview = (
        pd.DataFrame(rows)
        .sort_values(["Y", "X", "CHAROLA"])
        .reset_index(drop=True)
    )

    total_w  = float((preview["X"] + preview["Ancho_cm"]).max())
    capacity = float(preview["Ancho_cm"].sum())
    max_feas = _max_feasible_frentes(df, seg, mue, pg, tam, dir_, None, capacity)
    return {
        "shelves":              preview.to_dict(orient="records"),
        "total_width":          total_w,
        "n_modules":            int(preview["X"].nunique()),
        "total_capacity":       capacity,
        "max_feasible_frentes": max_feas,
    }


@app.post("/api/optimize")
def start_optimize(req: OptimizeRequest):
    if req.file_id not in _uploads:
        raise HTTPException(404, "Archivo no encontrado. Vuelve a cargar.")

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"queue": queue.Queue(), "result": None, "done": False}

    t = threading.Thread(target=_run_grasp, args=(task_id, req), daemon=True)
    t.start()
    return {"task_id": task_id}


@app.get("/api/progress/{task_id}")
async def progress_stream(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, "Tarea no encontrada.")

    async def generate():
        while True:
            task = _tasks[task_id]
            try:
                while True:
                    msg = task["queue"].get_nowait()
                    yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                pass
            if task["done"]:
                # drain any remaining messages
                try:
                    while True:
                        msg = task["queue"].get_nowait()
                        yield f"data: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    pass
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/result/{task_id}")
def get_result(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Tarea no encontrada.")
    if not task["done"]:
        raise HTTPException(202, "Optimización en progreso.")
    if task.get("error"):
        raise HTTPException(500, task["error"])
    return task["result"]


@app.get("/api/result/{task_id}/csv")
def download_csv(task_id: str):
    task = _tasks.get(task_id)
    if not task or not task.get("csv_bytes"):
        raise HTTPException(404)
    tag = task.get("tag", "planograma")
    return Response(
        content=task["csv_bytes"],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="planograma_{tag}.csv"'},
    )


@app.get("/api/result/{task_id}/diag-csv")
def download_diag(task_id: str):
    task = _tasks.get(task_id)
    if not task or not task.get("diag_bytes"):
        raise HTTPException(404)
    tag = task.get("tag", "planograma")
    return Response(
        content=task["diag_bytes"],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="diagnostico_{tag}.csv"'},
    )


# ── GRASP worker ──────────────────────────────────────────────────────────────

def _max_feasible_frentes(df, seg, mue, pg, tam, dir_, max_variedad, capacity) -> int:
    """Encuentra el mayor max_frentes tal que suma(ancho_ocupado) <= capacity."""
    for mf in range(10, 0, -1):
        prods, _, _, _ = build_instance_single(
            df, seg, mue, pg, tam, dir_,
            min_frentes=1, max_frentes=mf, max_variedad=max_variedad,
        )
        if sum(p.ancho_ocupado for p in prods) <= capacity + 1e-9:
            return mf
    return 1


def _run_grasp(task_id: str, req: OptimizeRequest):
    task = _tasks[task_id]
    push = task["queue"].put

    try:
        df  = _uploads[req.file_id]["df"]
        seg = req.seg
        mue = req.mue
        pg  = req.pg
        tam = req.tam
        dir_ = req.dir

        push({"type": "status", "text": "Construyendo instancia…"})

        products, shelves, unplaced, warning = build_instance_single(
            df, seg, mue, pg, tam, dir_,
            min_frentes=req.min_frentes,
            max_frentes=req.max_frentes,
            max_variedad=req.max_variedad,
        )

        # Apply shelf overrides — lista autoritativa: modifica existentes, crea nuevas, excluye eliminadas
        if req.shelf_overrides:
            ov_map = {o.CHAROLA: o for o in req.shelf_overrides}
            data_map = {s.charola: s for s in shelves}
            rebuilt = []
            for ch in sorted(ov_map.keys()):
                ov = ov_map[ch]
                if ch in data_map:
                    rebuilt.append(_dc_replace(
                        data_map[ch],
                        width=ov.Ancho_cm,
                        height=float("inf"),
                        draw_height=ov.Alto_cm,
                        clearance=ov.Alto_cm,
                    ))
                else:
                    rebuilt.append(Shelf(
                        charola=ch,
                        width=ov.Ancho_cm,
                        height=float("inf"),
                        draw_height=ov.Alto_cm,
                        x_abs_base=ov.X,
                        y=ov.Y,
                        visibility=1.0,
                        clearance=ov.Alto_cm,
                    ))
            shelves = rebuilt

        if not products:
            push({"type": "error", "text": "No hay productos válidos para este formato."})
            task["done"] = True
            return
        if not shelves:
            push({"type": "error", "text": "No hay charolas para este formato."})
            task["done"] = True
            return

        # Verificar factibilidad ANTES de correr el GRASP
        total_ancho = sum(p.ancho_ocupado for p in products)
        total_cap   = sum(s.width for s in shelves)
        if total_ancho > total_cap + 1e-9:
            # Calcular max frentes factible
            max_feasible = _max_feasible_frentes(df, seg, mue, pg, tam, dir_, req.max_variedad, total_cap)
            push({
                "type": "infeasible",
                "total_ancho": round(total_ancho, 1),
                "total_cap":   round(total_cap, 1),
                "deficit":     round(total_ancho - total_cap, 1),
                "max_frentes_sugerido": max_feasible,
                "text": (
                    f"La instancia no es factible: {total_ancho:.0f} cm de productos "
                    f"> {total_cap:.0f} cm de capacidad (déficit {total_ancho-total_cap:.0f} cm). "
                    f"Reduce 'Frentes máximos' a {max_feasible} o menos, "
                    f"o limita la variedad de productos."
                ),
            })
            task["done"] = True
            return

        push({"type": "status", "text": f"Ejecutando GRASP ({req.max_iter} iteraciones)…"})

        solver = GRASPPlanograma(
            products=products, shelves=shelves,
            direction=dir_, segmento=seg, mueble=mue,
            planogrupo=pg, tamano=tam,
            alpha=req.alpha,
            lambda_hist=req.lambda_hist,
            beta_visibility=req.beta_vis,
            random_seed=req.seed,
        )

        def cb(it, total, score, best):
            push({"type": "progress", "it": it, "total": total,
                  "score": round(score, 4), "best": round(best, 4)})

        best_sol, best_score = solver.run(
            max_iter=req.max_iter,
            local_rounds=req.local_rounds,
            progress_cb=cb,
        )

        push({"type": "status", "text": "Procesando resultados…"})

        output_df = solver.decode(best_sol).sort_values(["CHAROLA", "UBICACION_BANDEJA"])
        diag_df   = build_diagnostics(output_df, shelves)
        tag       = fmt_tag(seg, mue, pg, tam, dir_)

        # Build assignments list (includes hist_charola / hist_pos for comparison tab)
        assignments = []
        for _, row in output_df.iterrows():
            assignments.append({
                "upc":          str(row["UPC_CVE"]),
                "name":         next(
                    (str(v).strip() for v in (row.get("NAME"), row.get("ITEM_DESC"))
                     if v is not None and str(v).strip().lower() not in ("nan", "")),
                    str(row["UPC_CVE"])
                ),
                "charola":      int(row["CHAROLA"]),
                "x_abs":        float(row["X_ABS"]),
                "x_local":      float(row["X_LOCAL"]),
                "ancho":        float(row["ANCHO"]),
                "num_frentes":  int(row["NUM_FRENTES"]),
                "width_total":  float(row["ANCHO_TOTAL"]),
                "alto":         float(row.get("ALTO") or 0),
                "planogrupo":   str(row.get("PLANOGRUPO") or pg),
                "ubicacion":    int(row["UBICACION_BANDEJA"]),
                "sep_aplicado": float(row.get("SEP_APLICADO") or 0),
                "hist_charola": int(row.get("HIST_CHAROLA") or 0),
                "hist_pos":     int(row.get("HIST_UBICACION_BANDEJA") or 0),
            })

        # Build shelves list
        shelves_out = [
            {
                "charola":     s.charola,
                "x_abs_base":  s.x_abs_base,
                "y":           s.y,
                "width":       s.width,
                "draw_height": s.draw_height,
                "visibility":  s.visibility,
            }
            for s in shelves
        ]

        # Metrics
        cap_total  = sum(s.width for s in shelves)
        ancho_col  = "ANCHO_NETO" if "ANCHO_NETO" in output_df.columns else "ANCHO_TOTAL"
        used       = float(output_df[ancho_col].sum())
        pct_occ    = used / cap_total * 100 if cap_total > 0 else 0
        holgura    = float(diag_df["HOLGURA"].mean()) if not diag_df.empty else 0.0

        n_in_hist  = int((output_df["CHAROLA"] == output_df["HIST_CHAROLA"]).sum()) \
                     if "HIST_CHAROLA" in output_df.columns else 0
        total_pl   = len(output_df)
        hist_fid   = round(n_in_hist / total_pl * 100, 1) if total_pl > 0 else 0.0

        metrics = {
            "score":                   round(best_score, 4),
            "total_products":          len(output_df["UPC_CVE"].unique()),
            "placed":                  total_pl,
            "unplaced":                len(unplaced),
            "occupancy_pct":           round(pct_occ, 1),
            "min_slack":               round(holgura, 2),
            "total_capacity":          round(cap_total, 1),
            "used_capacity":           round(used, 1),
            "hist_fidelity":           hist_fid,
            "products_in_hist_charola": n_in_hist,
        }

        # Diagnostics
        diag_rows = [
            {
                "charola":     int(r["CHAROLA"]),
                "n_productos": int(r["NUM_PRODUCTOS"]),
                "ancho_usado": float(r["ANCHO_USADO"]),
                "capacidad":   float(r["ANCHO_CAPACIDAD"]),
                "holgura":     float(r["HOLGURA"]),
                "es_factible": bool(r["ES_FACTIBLE"]),
            }
            for _, r in diag_df.iterrows()
        ]

        # Unplaced
        unplaced_out = [
            {"upc": str(u["UPC_CVE"]), "name": str(u.get("ITEM_DESC", u["UPC_CVE"])), "reason": str(u["RAZON"])}
            for u in unplaced
        ]

        result = {
            "task_id":     task_id,
            "assignments": assignments,
            "shelves":     shelves_out,
            "metrics":     metrics,
            "diagnostics": diag_rows,
            "unplaced":    unplaced_out,
            "tag":         tag,
        }

        task["result"]    = result
        task["csv_bytes"] = csv_bytes(output_df)
        task["diag_bytes"] = csv_bytes(diag_df)
        task["tag"]       = tag

        push({"type": "done", "result": result})

    except RuntimeError as e:
        push({"type": "error", "text": str(e)})
        task["error"] = str(e)
    except Exception:
        msg = traceback.format_exc()
        push({"type": "error", "text": msg})
        task["error"] = msg
    finally:
        task["done"] = True
