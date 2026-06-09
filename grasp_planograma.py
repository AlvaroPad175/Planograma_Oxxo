"""
GRASP funcional para planogramas OXXO.

Entradas esperadas:
- Productos históricos: CSV tipo oxxo_1.csv
- Charolas/espacios: XLSX tipo Caso de estudio TEC.xlsx

Salida:
- CSV con UPC_CVE, CHAROLA, UBICACION_BANDEJA, X_LOCAL, X_ABS, Y, NUM_FRENTES

Este primer prototipo usa las variables disponibles en los archivos subidos:
- Respeta formato: SEGMENTO_ID + MUEBLE_ID + PLANOGRUPO + TAMAÑO + DIRECCION_LEGO_ID
- Respeta capacidad de ancho por charola.
- Calcula coordenadas x,y considerando DIRECCION_LEGO_ID.
- Optimiza cercanía al acomodo histórico y una visibilidad simple por altura.
- Deja ganchos para peso, demanda, ganancia, rotación, promo e interacciones cuando esos datos existan.
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd


# -----------------------------
# Utilidades de lectura/limpieza
# -----------------------------

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columnas frecuentes, incluyendo BOM/encoding raro."""
    rename = {}
    for c in df.columns:
        c2 = str(c).replace("\ufeff", "").replace("ï»¿", "").strip()
        c2 = c2.replace("TAMAÃ\x91O_POST", "TAMAÑO_POST")
        c2 = c2.replace("TAMAÃ‘O_POST", "TAMAÑO_POST")
        c2 = c2.replace("TAMANO_POST", "TAMAÑO_POST")
        c2 = c2.replace("TAMAÑO_POST", "TAMAÑO_POST")
        c2 = c2.replace("TAMANO", "TAMAÑO")
        rename[c] = c2
    return df.rename(columns=rename)


def read_csv_safe(path: str | Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return clean_columns(pd.read_csv(path, encoding=enc))
        except UnicodeDecodeError:
            continue
    return clean_columns(pd.read_csv(path))


def read_shelves(path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    df = clean_columns(df)
    required = ["PLANOGRUPO", "MUEBLE_ID", "TAMAÑO_POST", "DIRECCION_LEGO_ID", "CHAROLA", "Width", "Height", "X", "Y"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en archivo de charolas: {missing}")
    return df


def read_products(path: str | Path) -> pd.DataFrame:
    df = read_csv_safe(path)
    required = ["SEGMENTO_ID", "MUEBLE_ID", "PLANOGRUPO", "TAMAÑO", "DIRECCION_LEGO_ID", "UPC_CVE", "NUM_FRENTES", "CHAROLA", "UBICACION_BANDEJA", "ANCHO"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas en archivo de productos: {missing}")
    return df


# -----------------------------
# Estructuras
# -----------------------------

@dataclass(frozen=True)
class Product:
    id: int
    upc: str
    ancho: float
    num_frentes: float
    width_total: float
    hist_charola: int
    hist_pos: int
    alto: Optional[float] = None
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
    height: float
    x_abs_base: float
    y: float
    wmax: float = float("inf")
    visibility: float = 1.0


Solution = Dict[int, List[int]]  # charola -> lista de product.id en orden


class GRASPPlanograma:
    def __init__(
        self,
        products: List[Product],
        shelves: List[Shelf],
        direction: str,
        alpha: float = 0.2,
        lambda_hist: float = 1.0,
        beta_visibility: float = 0.10,
        sep_default: float = 0.0,
        random_seed: int = 42,
    ):
        self.products = {p.id: p for p in products}
        self.shelves = {s.charola: s for s in shelves}
        self.charolas = sorted(self.shelves)
        self.direction = direction.upper().strip()
        self.alpha = alpha
        self.lambda_hist = lambda_hist
        self.beta_visibility = beta_visibility
        self.sep_default = sep_default
        self.rng = random.Random(random_seed)

    # ---------- Decodificador ----------
    def used_width(self, sol: Solution, c: int) -> float:
        return sum(self.products[i].width_total + self.sep_default for i in sol.get(c, []))

    def can_fit_at_end(self, sol: Solution, product_id: int, c: int) -> bool:
        p = self.products[product_id]
        s = self.shelves[c]
        if p.alto is not None and p.alto > s.height:
            return False
        return self.used_width(sol, c) + p.width_total + self.sep_default <= s.width + 1e-9

    def decode(self, sol: Solution) -> pd.DataFrame:
        rows = []
        for c in self.charolas:
            shelf = self.shelves[c]
            cursor = 0.0
            for pos, pid in enumerate(sol.get(c, []), start=1):
                p = self.products[pid]
                w = p.width_total
                if self.direction == "ID":
                    x_local = cursor
                else:  # DI: derecha -> izquierda
                    x_local = shelf.width - cursor - w
                x_abs = shelf.x_abs_base + x_local
                rows.append({
                    "UPC_CVE": p.upc,
                    "PRODUCT_ID_INTERNAL": pid,
                    "CHAROLA": c,
                    "UBICACION_BANDEJA": pos,
                    "X_LOCAL": round(x_local, 4),
                    "X_ABS": round(x_abs, 4),
                    "X_FIN_LOCAL": round(x_local + w, 4),
                    "Y": shelf.y,
                    "NUM_FRENTES": p.num_frentes,
                    "ANCHO": p.ancho,
                    "ANCHO_TOTAL": round(w, 4),
                    "HIST_CHAROLA": p.hist_charola,
                    "HIST_UBICACION_BANDEJA": p.hist_pos,
                    "DIRECTION": self.direction,
                })
                cursor += w + self.sep_default
        return pd.DataFrame(rows)

    # ---------- Factibilidad y objetivo ----------
    def feasible(self, sol: Solution) -> bool:
        assigned = [pid for c in self.charolas for pid in sol.get(c, [])]
        if len(assigned) != len(set(assigned)):
            return False
        if set(assigned) != set(self.products):
            return False
        for c in self.charolas:
            if self.used_width(sol, c) > self.shelves[c].width + 1e-9:
                return False
        return True

    def objective(self, sol: Solution) -> float:
        """Maximiza score. Con datos actuales: visibilidad - distancia histórica."""
        decoded = self.decode(sol)
        if decoded.empty:
            return -1e18
        score = 0.0
        # Mapa rápido de posición actual
        pos_now = decoded.set_index("PRODUCT_ID_INTERNAL")[["CHAROLA", "UBICACION_BANDEJA", "X_LOCAL"]].to_dict("index")
        for pid, p in self.products.items():
            c = int(pos_now[pid]["CHAROLA"])
            pos = int(pos_now[pid]["UBICACION_BANDEJA"])
            shelf = self.shelves[c]
            ventas_proxy = p.demanda * p.ganancia * p.rotacion * p.estacional * (1.0 + p.promo)
            score += self.beta_visibility * ventas_proxy * shelf.visibility
            # Penalización por cambiar charola y orden dentro de charola.
            score -= self.lambda_hist * (abs(c - p.hist_charola) + 0.15 * abs(pos - p.hist_pos))
        return score

    def incremental_score_append(self, sol: Solution, pid: int, c: int) -> float:
        """Score greedy para colocar pid al final de charola c."""
        p = self.products[pid]
        pos = len(sol.get(c, [])) + 1
        shelf = self.shelves[c]
        ventas_proxy = p.demanda * p.ganancia * p.rotacion * p.estacional * (1.0 + p.promo)
        score = self.beta_visibility * ventas_proxy * shelf.visibility
        score -= self.lambda_hist * (abs(c - p.hist_charola) + 0.15 * abs(pos - p.hist_pos))
        # Pequeño bono por dejarlo cerca de su charola histórica si cabe ahí.
        if c == p.hist_charola:
            score += 0.5
        return score

    # ---------- Construcción GRASP ----------
    def construct(self) -> Solution:
        sol: Solution = {c: [] for c in self.charolas}
        # Orden base histórico para arrancar cercano al planograma real.
        unassigned = sorted(self.products, key=lambda pid: (self.products[pid].hist_charola, self.products[pid].hist_pos))

        while unassigned:
            # Para evitar que productos anchos queden imposibles al final,
            # tomamos primero los de mayor ancho total. La aleatoriedad queda
            # en la selección de charola mediante RCL.
            unassigned.sort(
                key=lambda pid: (
                    -self.products[pid].width_total,
                    self.products[pid].hist_charola,
                    self.products[pid].hist_pos,
                )
            )
            pid_actual = unassigned[0]
            candidates: List[Tuple[int, int, float]] = []
            for c in self.charolas:
                if self.can_fit_at_end(sol, pid_actual, c):
                    candidates.append((pid_actual, c, self.incremental_score_append(sol, pid_actual, c)))

            if not candidates:
                raise RuntimeError(
                    f"No hay charola factible para producto {pid_actual} "
                    f"(w={self.products[pid_actual].width_total:.2f}). "
                    "Revisa ancho total, separadores o número de frentes."
                )

            g_values = [g for _, _, g in candidates]
            g_max, g_min = max(g_values), min(g_values)
            threshold = g_max - self.alpha * (g_max - g_min)
            rcl = [(pid, c, g) for pid, c, g in candidates if g >= threshold]
            pid, c, _ = self.rng.choice(rcl)
            sol[c].append(pid)
            unassigned.remove(pid)
        return sol

    # ---------- Búsqueda local ----------
    def local_search(self, sol: Solution, max_rounds: int = 30, sample_moves: int = 250) -> Solution:
        best = {c: list(v) for c, v in sol.items()}
        best_score = self.objective(best)
        product_ids = list(self.products.keys())

        for _ in range(max_rounds):
            improved = False
            best_neighbor = None
            best_neighbor_score = best_score

            for _m in range(sample_moves):
                move_type = self.rng.choice(["swap", "relocate"])
                candidate = {c: list(v) for c, v in best.items()}

                if move_type == "swap":
                    i, j = self.rng.sample(product_ids, 2)
                    ci, pi = self.find_product(candidate, i)
                    cj, pj = self.find_product(candidate, j)
                    candidate[ci][pi], candidate[cj][pj] = candidate[cj][pj], candidate[ci][pi]
                else:
                    i = self.rng.choice(product_ids)
                    ci, pi = self.find_product(candidate, i)
                    candidate[ci].pop(pi)
                    # Insertar en charola destino y posición aleatoria
                    c_dest = self.rng.choice(self.charolas)
                    insert_pos = self.rng.randint(0, len(candidate[c_dest]))
                    candidate[c_dest].insert(insert_pos, i)

                if not self.feasible(candidate):
                    continue
                score = self.objective(candidate)
                if score > best_neighbor_score + 1e-9:
                    best_neighbor_score = score
                    best_neighbor = candidate

            if best_neighbor is not None:
                best = best_neighbor
                best_score = best_neighbor_score
                improved = True

            if not improved:
                break
        return best

    def find_product(self, sol: Solution, pid: int) -> Tuple[int, int]:
        for c, items in sol.items():
            if pid in items:
                return c, items.index(pid)
        raise KeyError(pid)

    # ---------- Algoritmo principal ----------
    def run(self, max_iter: int = 50, local_rounds: int = 20) -> Tuple[Solution, float]:
        best_sol = None
        best_score = -math.inf
        for _ in range(max_iter):
            sol = self.construct()
            sol = self.local_search(sol, max_rounds=local_rounds)
            score = self.objective(sol)
            if self.feasible(sol) and score > best_score:
                best_sol, best_score = sol, score
        if best_sol is None:
            raise RuntimeError("No se encontró solución factible.")
        return best_sol, best_score


# -----------------------------
# Preparación de datos por formato
# -----------------------------

def build_instance(
    products_csv: str | Path,
    shelves_xlsx: str | Path,
    segmento: str,
    mueble: str,
    planogrupo: str,
    tamano: float,
    direccion: str,
) -> Tuple[List[Product], List[Shelf]]:
    prod_df = read_products(products_csv)
    shelf_df = read_shelves(shelves_xlsx)

    pf = prod_df[
        (prod_df["SEGMENTO_ID"].astype(str) == str(segmento))
        & (prod_df["MUEBLE_ID"].astype(str) == str(mueble))
        & (prod_df["PLANOGRUPO"].astype(str) == str(planogrupo))
        & (prod_df["TAMAÑO"].astype(float) == float(tamano))
        & (prod_df["DIRECCION_LEGO_ID"].astype(str) == str(direccion))
    ].copy()

    sf = shelf_df[
        (shelf_df["MUEBLE_ID"].astype(str) == str(mueble))
        & (shelf_df["PLANOGRUPO"].astype(str) == str(planogrupo))
        & (shelf_df["TAMAÑO_POST"].astype(float) == float(tamano))
        & (shelf_df["DIRECCION_LEGO_ID"].astype(str) == str(direccion))
    ].copy()

    if pf.empty:
        raise ValueError("No hay productos para ese formato.")
    if sf.empty:
        raise ValueError("No hay charolas para ese formato.")

    # Visibilidad proxy: más cerca de la altura media alta => más visible.
    y_min, y_max = sf["Y"].min(), sf["Y"].max()
    y_range = max(y_max - y_min, 1.0)

    shelves: List[Shelf] = []
    for _, r in sf.sort_values("CHAROLA").iterrows():
        y_norm = (float(r["Y"]) - y_min) / y_range
        visibility = 1.0 + y_norm  # simple y reemplazable por un mapa real
        shelves.append(Shelf(
            charola=int(r["CHAROLA"]),
            width=float(r["Width"]),
            height=float(r["Height"]),
            x_abs_base=float(r.get("X", 0.0)),
            y=float(r.get("Y", 0.0)),
            visibility=visibility,
        ))

    products: List[Product] = []
    for idx, r in pf.reset_index(drop=True).iterrows():
        ancho = float(r["ANCHO"])
        frentes = float(r["NUM_FRENTES"])
        products.append(Product(
            id=idx,
            upc=str(r["UPC_CVE"]),
            ancho=ancho,
            num_frentes=frentes,
            width_total=ancho * frentes,
            hist_charola=int(r["CHAROLA"]),
            hist_pos=int(r["UBICACION_BANDEJA"]),
            grupo=str(r.get("PLANOGRUPO", "")),
            categoria=str(r.get("categoria_producto", "")),
        ))

    total_width = sum(p.width_total for p in products)
    total_capacity = sum(s.width for s in shelves)
    if total_width > total_capacity + 1e-9:
        raise ValueError(f"Instancia no factible por ancho: productos={total_width:.2f} cm, capacidad={total_capacity:.2f} cm")

    return products, shelves


def main():
    parser = argparse.ArgumentParser(description="GRASP para planogramas OXXO")
    parser.add_argument("--products", default="/mnt/data/oxxo_1.csv")
    parser.add_argument("--shelves", default="/mnt/data/Caso de estudio TEC.xlsx")
    parser.add_argument("--segmento", default="HRN")
    parser.add_argument("--mueble", default="CF")
    parser.add_argument("--planogrupo", default="Refrescos")
    parser.add_argument("--tamano", type=float, default=5.0)
    parser.add_argument("--direccion", default="ID", choices=["ID", "DI"])
    parser.add_argument("--max_iter", type=int, default=10)
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="/mnt/data/salida_grasp_planograma.csv")
    args = parser.parse_args()

    products, shelves = build_instance(
        args.products, args.shelves, args.segmento, args.mueble,
        args.planogrupo, args.tamano, args.direccion
    )
    solver = GRASPPlanograma(
        products, shelves, args.direccion,
        alpha=args.alpha, random_seed=args.seed,
        lambda_hist=1.0, beta_visibility=0.10,
    )
    best_sol, best_score = solver.run(max_iter=args.max_iter, local_rounds=4)
    output = solver.decode(best_sol).sort_values(["CHAROLA", "UBICACION_BANDEJA"])

    # Diagnóstico por charola
    used = output.groupby("CHAROLA")["ANCHO_TOTAL"].sum().rename("ANCHO_USADO")
    capacity = pd.Series({s.charola: s.width for s in shelves}, name="ANCHO_CAPACIDAD")
    diag = pd.concat([used, capacity], axis=1)
    diag["HOLGURA"] = diag["ANCHO_CAPACIDAD"] - diag["ANCHO_USADO"]

    out_path = Path(args.out)
    output.to_csv(out_path, index=False, encoding="utf-8-sig")
    diag_path = out_path.with_name(out_path.stem + "_diagnostico.csv")
    diag.to_csv(diag_path, encoding="utf-8-sig")

    print(f"Score final: {best_score:.4f}")
    print(f"Productos acomodados: {len(output)}")
    print(f"Charolas usadas: {(diag['ANCHO_USADO'] > 0).sum()} / {len(diag)}")
    print(f"Mínima holgura por charola: {diag['HOLGURA'].min():.4f} cm")
    print(f"Salida: {out_path}")
    print(f"Diagnóstico: {diag_path}")


if __name__ == "__main__":
    main()
