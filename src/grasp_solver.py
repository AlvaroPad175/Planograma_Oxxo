"""
grasp_solver.py — Algoritmo GRASP para optimización de planogramas OXXO.

Implementación directa del notebook planograma_grasp.ipynb con los FIX 1-7
documentados. Los únicos cambios respecto al notebook son:
  - run() acepta un callback opcional para reportar progreso.
  - decode() incluye la columna NAME (nombre del producto).
  - Los print() de depuración se eliminan; los mensajes se retornan.
"""
from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from .models import Product, Shelf, Solution


class GRASPPlanograma:

    def __init__(
        self,
        products: List[Product],
        shelves: List[Shelf],
        direction: str,
        segmento: str = "",
        mueble: str = "",
        planogrupo: str = "",
        tamano: float = 0.0,
        alpha: float = 0.2,
        lambda_hist: float = 1.0,
        beta_visibility: float = 0.10,
        random_seed: int = 42,
    ):
        self.products   = {p.id: p for p in products}
        self.shelves    = {s.charola: s for s in shelves}
        self.charolas   = sorted(self.shelves)
        self.direction  = direction.upper().strip()
        self.segmento   = segmento
        self.mueble     = mueble
        self.planogrupo = planogrupo
        self.tamano     = tamano

        self.alpha           = alpha
        self.lambda_hist     = lambda_hist
        self.beta_visibility = beta_visibility
        self.rng = random.Random(random_seed)

        # Cache: altura máxima de producto (para normalizar penalización de tamaño)
        self._max_alto = max(
            (p.alto for p in products if p.alto is not None), default=1.0
        ) or 1.0

    # ── Helpers de ancho ─────────────────────────────────────────────────────

    def used_width(self, sol: Solution, c: int) -> float:
        """
        Ancho real usado en la charola c.

        Regla: separador va ENTRE productos, no después del último.
            used = Σ(width_total_i) + Σ(sep_i  para todo i excepto el último)
                 = Σ(ancho_ocupado_i) - sep_del_último
        """
        pids = sol.get(c, [])
        if not pids:
            return 0.0
        total = sum(self.products[pid].ancho_ocupado for pid in pids)
        return total - self.products[pids[-1]].separador

    def can_fit_at_end(self, sol: Solution, pid: int, c: int) -> bool:
        """
        ¿Cabe el producto pid al final de la charola c?

        Al agregar el producto, el separador del último producto actual se aplica
        (pasa a ser intermedio), y el nuevo producto es el nuevo último (sin sep).

            nuevo_ancho = used_width(actual) + sep_del_último_actual + width_total_nuevo
        """
        p = self.products[pid]
        s = self.shelves[c]
        # FIX 1: restricción de altura solo si alto está definido
        if p.alto is not None and p.alto > s.height:
            return False
        existing = sol.get(c, [])
        current  = self.used_width(sol, c)          # ancho real sin sep final
        last_sep = (
            self.products[existing[-1]].separador if existing else 0.0
        )
        return current + last_sep + p.width_total <= s.width + 1e-9

    # ── Decodificador ────────────────────────────────────────────────────────

    def decode(self, sol: Solution) -> pd.DataFrame:
        """
        Convierte la solución a DataFrame.

        Columnas de ancho:
          ANCHO_TOTAL   = ANCHO × NUM_FRENTES  (ancho visual del producto)
          SEPARADOR     = separador configurado para este producto
          SEP_APLICADO  = separador que se aplica después de este producto;
                          0 para el último producto de cada charola.
          ANCHO_NETO    = ANCHO_TOTAL + SEP_APLICADO  (espacio real consumido)
        """
        rows = []
        for c in self.charolas:
            shelf  = self.shelves[c]
            cursor = 0.0
            products_on_shelf = sol.get(c, [])
            n = len(products_on_shelf)
            for i, pid in enumerate(products_on_shelf, start=1):
                p = self.products[pid]
                w = p.width_total
                is_last     = (i == n)
                sep_aplicado = 0.0 if is_last else p.separador

                if self.direction == "ID":
                    x_local = cursor
                else:
                    x_local = shelf.width - cursor - w
                x_abs = shelf.x_abs_base + x_local

                rows.append({
                    "SEGMENTO_ID":            self.segmento,
                    "MUEBLE_ID":              self.mueble,
                    "PLANOGRUPO":             self.planogrupo,
                    "TAMAÑO":                 self.tamano,
                    "DIRECCION_LEGO_ID":      self.direction,
                    "UPC_CVE":                p.upc,
                    "NAME":                   p.name,
                    "CHAROLA":                c,
                    "UBICACION_BANDEJA":      i,
                    "X_LOCAL":                round(x_local, 4),
                    "X_ABS":                  round(x_abs, 4),
                    "X_FIN_LOCAL":            round(x_local + w, 4),
                    "Y":                      shelf.y,
                    "NUM_FRENTES":            p.num_frentes,
                    "ANCHO":                  p.ancho,
                    "ANCHO_TOTAL":            round(w, 4),
                    "ALTO":                   float(p.alto) if p.alto is not None else 0.0,
                    "SEPARADOR":              p.separador,
                    "SEP_APLICADO":           round(sep_aplicado, 4),
                    "ANCHO_NETO":             round(w + sep_aplicado, 4),
                    "HIST_CHAROLA":           p.hist_charola,
                    "HIST_UBICACION_BANDEJA": p.hist_pos,
                })
                cursor += w + sep_aplicado
        return pd.DataFrame(rows)

    # ── Factibilidad ─────────────────────────────────────────────────────────

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

    # ── Función objetivo ─────────────────────────────────────────────────────

    def objective(self, sol: Solution) -> float:
        position_map: Dict[int, Tuple[int, int]] = {}
        for c, pids in sol.items():
            for pos, pid in enumerate(pids, start=1):
                position_map[pid] = (c, pos)

        score = 0.0
        for pid, p in self.products.items():
            c, pos = position_map.get(pid, (p.hist_charola, p.hist_pos))
            shelf  = self.shelves.get(c, self.shelves[self.charolas[0]])
            vx     = p.demanda * p.ganancia * p.rotacion * p.estacional * (1.0 + p.promo)
            score += self.beta_visibility * vx * shelf.visibility
            charola_dist = abs(c - p.hist_charola)
            pos_dist     = abs(pos - p.hist_pos)
            if charola_dist == 0:
                score += self.lambda_hist * 2.0
                score -= self.lambda_hist * 0.25 * pos_dist
            else:
                score -= self.lambda_hist * (charola_dist + 0.25 * pos_dist)
            score -= self.lambda_hist * self._size_shelf_penalty(p, shelf)
        return score

    def _size_shelf_penalty(self, p, shelf) -> float:
        """Penalización cuando un producto alto va a una charola con poco clearance."""
        if p.alto is None or shelf.clearance >= self._max_alto:
            return 0.0
        # height_ratio: 0=producto muy pequeño, 1=más alto del dataset
        height_ratio = p.alto / self._max_alto
        # excess: fracción en que el producto excede el clearance de la charola
        excess = max(0.0, (p.alto - shelf.clearance) / self._max_alto)
        # También premiamos cuando el producto es grande y la charola es generosa
        fit_bonus = height_ratio * max(0.0, (shelf.clearance - p.alto) / self._max_alto)
        return excess - 0.3 * fit_bonus  # penaliza exceso, premia buen ajuste

    def incremental_score(self, pid: int, c: int, pos: int) -> float:
        p     = self.products[pid]
        shelf = self.shelves[c]
        vx    = p.demanda * p.ganancia * p.rotacion * p.estacional * (1.0 + p.promo)
        s     = self.beta_visibility * vx * shelf.visibility
        charola_dist = abs(c - p.hist_charola)
        pos_dist     = abs(pos - p.hist_pos)
        if charola_dist == 0:
            s += self.lambda_hist * 2.0
            s -= self.lambda_hist * 0.25 * pos_dist
        else:
            s -= self.lambda_hist * (charola_dist + 0.25 * pos_dist)
        # Penalización suave: botellas altas en charolas con poco clearance
        s -= self.lambda_hist * self._size_shelf_penalty(p, shelf)
        return s

    # ── Índice inverso O(1) ──────────────────────────────────────────────────

    def _build_inv(self, sol: Solution) -> Dict[int, Tuple[int, int]]:
        # FIX 7: {pid: (charola, posición_en_lista)}
        return {pid: (c, i) for c, lst in sol.items() for i, pid in enumerate(lst)}

    # ── Construcción GRASP ───────────────────────────────────────────────────

    def construct(self) -> Solution:
        sol: Solution = {c: [] for c in self.charolas}

        # Orden de construcción — tres criterios en cascada:
        #   1. Tier de altura (descendente): los más restringidos primero.
        #      Se agrupa en 3 buckets para no romper el histórico en exceso:
        #        0 = solo cabe en charolas muy bajas (alto > umbral_bajo)
        #        1 = no cabe en charolas altas   (alto > umbral_alto)
        #        2 = cabe en cualquier charola
        #   2. Ancho (descendente): dentro del tier, los más anchos primero
        #      → principio FFD (First-Fit Decreasing) para reducir fragmentación.
        #   3. Posición histórica: preserva el orden dentro de cada charola.
        clearances = sorted({s.height for s in self.shelves.values()})
        thresh_low  = clearances[len(clearances) // 2]   # percentil medio
        thresh_high = clearances[-1]                      # clearance máximo

        def _tier(pid: int) -> int:
            a = self.products[pid].alto or 0
            if a > thresh_low:
                return 0   # solo cabe abajo
            if a > clearances[0]:
                return 1   # no cabe en el nivel más restrictivo
            return 2

        priority = sorted(
            self.products.keys(),
            key=lambda pid: (
                _tier(pid),
                -self.products[pid].ancho_ocupado,
                self.products[pid].hist_charola,
                self.products[pid].hist_pos,
            ),
        )
        unassigned: set = set(priority)

        while unassigned:
            pid_actual = next(p for p in priority if p in unassigned)
            p = self.products[pid_actual]

            # Paso conservador: si la charola histórica tiene espacio, úsala siempre.
            # Alpha no aplica aquí — la construcción histórica es determinística.
            hist_c = p.hist_charola
            if hist_c in self.shelves and self.can_fit_at_end(sol, pid_actual, hist_c):
                sol[hist_c].append(pid_actual)
                unassigned.discard(pid_actual)
                continue

            # Charola histórica llena o inexistente → RCL sobre las demás charolas
            candidates = [
                (pid_actual, c, self.incremental_score(pid_actual, c, len(sol[c]) + 1))
                for c in self.charolas
                if self.can_fit_at_end(sol, pid_actual, c)
            ]

            if not candidates:
                raise RuntimeError(
                    f"Sin charola factible para producto {pid_actual} "
                    f"(ancho_ocupado={p.ancho_ocupado:.2f} cm). "
                    "Revisa anchos, separadores o capacidad."
                )

            g_vals = [g for _, _, g in candidates]
            g_max, g_min = max(g_vals), min(g_vals)
            threshold = g_max - self.alpha * (g_max - g_min)
            rcl = [(pid, c, g) for pid, c, g in candidates if g >= threshold]
            pid, c, _ = self.rng.choice(rcl)
            sol[c].append(pid)
            unassigned.discard(pid)

        return sol

    # ── Búsqueda local ───────────────────────────────────────────────────────

    def local_search(
        self, sol: Solution, max_rounds: int = 30, sample_moves: int = 250
    ) -> Solution:
        best       = {c: list(v) for c, v in sol.items()}
        best_score = self.objective(best)
        pids       = list(self.products.keys())

        for _ in range(max_rounds):
            improved       = False
            best_neighbor  = None
            best_nbr_score = best_score

            inv = self._build_inv(best)

            for _ in range(sample_moves):
                # swap     — intercambia dos productos entre charolas
                # relocate — mueve un producto a una charola aleatoria
                # restore  — regresa un producto desplazado a su charola histórica
                # reorder  — reordena una charola por posición histórica
                move = self.rng.choice(["swap", "relocate", "restore", "reorder"])
                cand = {c: list(v) for c, v in best.items()}

                if move == "swap":
                    i, j   = self.rng.sample(pids, 2)
                    ci, pi = inv[i]
                    cj, pj = inv[j]
                    cand[ci][pi], cand[cj][pj] = cand[cj][pj], cand[ci][pi]

                elif move == "relocate":
                    i      = self.rng.choice(pids)
                    ci, pi = inv[i]
                    cand[ci].pop(pi)
                    c_dest = self.rng.choice(self.charolas)
                    ins    = self.rng.randint(0, len(cand[c_dest]))
                    cand[c_dest].insert(ins, i)

                elif move == "restore":
                    # Regresa un producto desplazado a su charola histórica
                    displaced = [
                        pid for pid in pids
                        if inv[pid][0] != self.products[pid].hist_charola
                        and self.products[pid].hist_charola in self.shelves
                    ]
                    if not displaced:
                        continue
                    i      = self.rng.choice(displaced)
                    ci, pi = inv[i]
                    target = self.products[i].hist_charola
                    cand[ci].pop(pi)
                    ideal  = max(0, min(self.products[i].hist_pos - 1, len(cand[target])))
                    cand[target].insert(ideal, i)

                elif move == "reorder":
                    # Reordena productos de una charola por su posición histórica
                    c_target = self.rng.choice(self.charolas)
                    if len(cand[c_target]) < 2:
                        continue
                    cand[c_target].sort(key=lambda pid: self.products[pid].hist_pos)

                if not self.feasible(cand):
                    continue
                score = self.objective(cand)
                if score > best_nbr_score + 1e-9:
                    best_nbr_score = score
                    best_neighbor  = cand

            if best_neighbor is not None:
                best       = best_neighbor
                best_score = best_nbr_score
                improved   = True

            if not improved:
                break

        return best

    # ── Loop principal ───────────────────────────────────────────────────────

    def run(
        self,
        max_iter: int = 20,
        local_rounds: int = 20,
        progress_cb: Optional[Callable[[int, int, float, float], None]] = None,
    ) -> Tuple[Solution, float]:
        """
        Ejecuta el GRASP.

        Args:
            max_iter:    Número de iteraciones GRASP.
            local_rounds: Rondas de búsqueda local por iteración.
            progress_cb: Callback opcional(iter, max_iter, score, best_score).

        Returns:
            (best_solution, best_score)
        """
        best_sol   = None
        best_score = -math.inf

        for it in range(1, max_iter + 1):
            sol   = self.construct()
            sol   = self.local_search(sol, max_rounds=local_rounds)
            score = self.objective(sol)

            if self.feasible(sol) and score > best_score:
                best_sol, best_score = sol, score

            if progress_cb is not None:
                progress_cb(it, max_iter, score, best_score)

        if best_sol is None:
            raise RuntimeError("No se encontró ninguna solución factible.")

        return best_sol, best_score
