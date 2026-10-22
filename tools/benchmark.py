"""Reproduce paired-seed comparisons, CSV evidence and portable SVG figures.

No plotting dependencies: results figures are generated from experiment data as SVG.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acag import Solver, TSP  # noqa: E402

ALGORITHMS = ("aca", "ga", "acag")
PALETTE = {"aca": "#007f9f", "ga": "#df7b26", "acag": "#7259bd"}


def fmt(x: float) -> str:
    return f"{x:.2f}"


def polyline(values: list[float], top: float, bottom: float,
             w: int = 640, h: int = 280) -> str:
    n = len(values)
    return " ".join(f"{60 + i * w / max(n - 1, 1):.1f},"
                    f"{50 + (top - value) * h / max(top - bottom, 1):.1f}"
                    for i, value in enumerate(values))


def convergence_svg(instance: str, history: dict[str, list[list[int]]],
                    budget: int) -> str:
    means = {alg: [statistics.mean(run[k] for run in history[alg])
                   for k in range(budget)] for alg in ALGORITHMS}
    hi = math.ceil(max(v[0] for v in means.values()) / 100) * 100
    lo = math.floor(min(v[-1] for v in means.values()) / 100) * 100
    paths = "\n".join(
        f'<polyline fill="none" stroke="{PALETTE[alg]}" stroke-width="2.8" '
        f'points="{polyline(means[alg][::max(1, budget//60)] + [means[alg][-1]], hi, lo)}" />'
        for alg in ALGORITHMS)
    legend = "".join(f'<rect x="{450+95*k}" y="18" width="13" height="5" '
                     f'fill="{PALETTE[a]}"/><text x="{469+95*k}" y="24" '
                     f'font-size="12" fill="#31445a">{a.upper()}</text>'
                     for k, a in enumerate(ALGORITHMS))
    ticks = "".join(f'<text x="45" y="{55+k*70}" text-anchor="end" '
                    f'font-size="11" fill="#66778c">{int(hi+(lo-hi)*k/4)}</text>'
                    for k in range(5))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="780" height="410" viewBox="0 0 780 410" role="img" aria-label="Mean best tour length versus evaluated tours on {instance}">
<rect width="780" height="410" rx="14" fill="#f8fafc"/>
<text x="32" y="28" font-family="Arial,sans-serif" font-size="18" font-weight="bold" fill="#162a45">{instance} · Mean best-so-far cost</text>
{legend}
<g stroke="#dce5ee" stroke-width="1"><path d="M60 50H700 M60 120H700 M60 190H700 M60 260H700 M60 330H700"/></g>
<path d="M60 50V330H700" fill="none" stroke="#8e9faf" stroke-width="1.5"/>
<g font-family="Arial,sans-serif">{ticks}<text x="58" y="350" font-size="11" fill="#66778c">1</text>
<text x="686" y="350" font-size="11" fill="#66778c">{budget}</text>
<text x="315" y="382" fill="#41556e" font-size="13">Evaluated complete tours (equal budget)</text></g>
{paths}
</svg>'''


def route_svg(tsp: TSP, tour: tuple[int, ...], length: int) -> str:
    xs, ys = zip(*tsp.points)
    scale = min(690/max(max(xs)-min(xs), 1), 300/max(max(ys)-min(ys), 1))
    points = [(45+(x-min(xs))*scale, 65+(y-min(ys))*scale)
              for x, y in tsp.points]
    poly = " ".join(f"{points[i][0]:.1f},{points[i][1]:.1f}"
                    for i in list(tour)+[tour[0]])
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3"/>' for x,y in points)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="780" height="430" viewBox="0 0 780 430" role="img" aria-label="TSP tour for {tsp.name}, length {length}">
<rect width="780" height="430" rx="14" fill="#f8fafc"/>
<text x="32" y="28" font-family="Arial,sans-serif" font-size="18" font-weight="bold" fill="#162a45">{tsp.name} · ACAG example tour · length {length}</text>
<polyline points="{poly}" fill="none" stroke="#7155b9" stroke-width="2.2" stroke-linejoin="round"/>
<g fill="#167c94" stroke="white" stroke-width="1">{dots}</g>
<circle cx="{points[tour[0]][0]:.1f}" cy="{points[tour[0]][1]:.1f}" r="6" fill="#db5f30" stroke="white" stroke-width="1.5"/>
<text x="32" y="406" font-family="Arial,sans-serif" font-size="12" fill="#576d82">Illustrative stochastic run; no optimality claim.</text>
</svg>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--budget", type=int, default=600)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--ant-max", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    if args.seeds < 1 or args.budget < args.population:
        parser.error("Need seeds >=1 and budget >= population")
    args.out.mkdir(parents=True, exist_ok=True)
    figures = ROOT / "docs" / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    aggregate: dict[str, dict] = {}
    for filename in ("eil51.tsp", "berlin52.tsp"):
        tsp = TSP.from_tsplib(ROOT / "data" / filename)
        histories: dict[str, list[list[int]]] = {a: [] for a in ALGORITHMS}
        routes: dict[str, list[tuple[int, tuple[int, ...]]]] = {a: [] for a in ALGORITHMS}
        for seed in range(args.seeds):
            for alg in ALGORITHMS:
                result = Solver(tsp, seed=seed, budget=args.budget,
                                population=args.population,
                                ant_max=args.ant_max).run(alg)
                rows.append(dict(instance=tsp.name, seed=seed, algorithm=alg,
                                 best_length=result.length, evaluations=result.evaluations,
                                 switch_evaluation=result.switch_evaluation or ""))
                histories[alg].append([x[1] for x in result.history])
                routes[alg].append((result.length, result.tour))
        means = {a: statistics.mean(length for length, _ in routes[a])
                 for a in ALGORITHMS}
        aggregate[tsp.name] = dict(mean=means,
                                   min={a: min(length for length, _ in routes[a])
                                        for a in ALGORITHMS},
                                   n_seeds=args.seeds, budget=args.budget,
                                   paired_acag_minus_aca=[routes["acag"][i][0]-routes["aca"][i][0]
                                                          for i in range(args.seeds)],
                                   paired_acag_minus_ga=[routes["acag"][i][0]-routes["ga"][i][0]
                                                         for i in range(args.seeds)])
        (figures / f"{tsp.name}-convergence.svg").write_text(
            convergence_svg(tsp.name, histories, args.budget), encoding="utf-8")
        best = min(routes["acag"], key=lambda r: r[0])
        (figures / f"{tsp.name}-route.svg").write_text(
            route_svg(tsp, best[1], best[0]), encoding="utf-8")
        print(tsp.name, json.dumps(aggregate[tsp.name]))
    with (args.out / "benchmark_v0.1.0.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.out / "summary_v0.1.0.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
