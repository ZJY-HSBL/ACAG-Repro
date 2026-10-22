"""v0.2.0 preregistered switch-timing ablation with charged local-search queries.

No plotting/scientific dependencies. Figures, CSV and JSON are deterministic across
Python 3.10+ for the same source and data, without wall-clock timing claims.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acag import Solver, TSP  # noqa: E402

SPECS = (
    ("ACA", "aca", "never", "elite"),
    ("GA", "ga", "never", "elite"),
    ("ACAG-stagnation", "acag", "stagnation", "elite"),
    ("ACAG-25%", "acag", "fixed25", "elite"),
    ("ACAG-50%", "acag", "fixed50", "elite"),
    ("ACAG-75%", "acag", "fixed75", "elite"),
    ("ACAG-50%-random", "acag", "fixed50", "random"),
)
COLORS = ("#64748b", "#d97706", "#c026d3", "#e11d48", "#2563eb", "#059669", "#8b5cf6")
OPTIMA = {"eil51": 426, "berlin52": 7542}


def interval(pairs: list[int], bootstraps: int = 8000) -> tuple[float, float]:
    rng = random.Random(1829)
    n = len(pairs)
    samples = sorted(sum(pairs[rng.randrange(n)] for _ in range(n)) / n
                     for _ in range(bootstraps))
    return samples[int(.025 * bootstraps)], samples[int(.975 * bootstraps)]


def paired_randomization_p(pairs: list[int], samples: int = 8000) -> float:
    """Two-sided paired sign-flip Monte Carlo test, assuming exchangeability."""
    rng = random.Random(94107)
    observed = abs(sum(pairs))
    extreme = 0
    for _ in range(samples):
        score = abs(sum(x * (1 if rng.randrange(2) else -1) for x in pairs))
        extreme += score >= observed
    return (extreme + 1) / (samples + 1)


def svg_text(x: float, y: float, value: str, size: int = 14,
             weight: str = "normal", color: str = "#334155", anchor: str = "start") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-family="Arial, sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{escape(value)}</text>')


def canvas(body: str, title: str, subtitle: str, width: int = 1100,
           height: int = 600) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">\n'
            f'<rect width="{width}" height="{height}" fill="#f8fafc" rx="16"/>\n'
            f'{svg_text(48, 50, title, 25, "bold", "#0f172a")}\n'
            f'{svg_text(48, 79, subtitle, 13, color="#64748b")}\n'
            f'{body}\n</svg>\n')


def gap_figure(instance: str, stats: dict, n: int, budget: int) -> str:
    # GA is excluded from the zoomed bar comparison because its >170% gap
    # would visually suppress the scientifically relevant 4–9% ACA/ACAG range.
    labels = [spec[0] for spec in SPECS if spec[0] != 'GA']
    maximum = max(stats[a]["mean_gap_pct"] for a in labels) * 1.14
    scale = 650 / max(maximum, 1)
    body = ''
    for idx, label in enumerate(labels):
        e = stats[label]
        y = 135 + 62 * idx
        color = COLORS[[row[0] for row in SPECS].index(label)]
        body += svg_text(45, y+18, label, 15)
        body += f'<rect x="260" y="{y}" width="{e["mean_gap_pct"]*scale:.1f}" height="29" rx="4" fill="{color}"/>\n'
        body += svg_text(270+e["mean_gap_pct"]*scale, y+20,
                         f'{e["mean_gap_pct"]:.2f}%  (mean {e["mean"]:.1f})', 14, "bold")
    body += svg_text(260, 531, f'GA outside zoomed scale: {stats["GA"]["mean_gap_pct"]:.2f}% gap', 13, color="#d97706")
    body += svg_text(260, 559, 'Gap = (mean tour length / known optimum − 1) × 100%', 14)
    return canvas(body, f'{instance} | ACA vs ACAG (zoomed gap)',
                  f'{n} new paired seeds · {budget} charged tour evaluations per run')


def effect_figure(instance: str, comparisons: dict, n: int, budget: int) -> str:
    labels = [spec[0] for spec in SPECS if spec[0] != 'ACA']
    lo = min([0.0] + [comparisons[a]["bootstrap95"][0] for a in labels])
    hi = max([0.0] + [comparisons[a]["bootstrap95"][1] for a in labels])
    pad = max(10.0, (hi-lo)*.18)
    lo, hi = lo-pad, hi+pad
    def to_x(x: float) -> float:
        return 260+(x-lo)*720/(hi-lo)
    zero = to_x(0)
    body = (f'<line x1="{zero:.1f}" y1="108" x2="{zero:.1f}" y2="500" '
            f'stroke="#0f172a" stroke-dasharray="6,6" stroke-width="2"/>')
    for idx, a in enumerate(labels):
        y = 132+55*idx
        item = comparisons[a]
        x1, x2 = [to_x(v) for v in item["bootstrap95"]]
        x = to_x(item["mean_difference"])
        body += svg_text(45, y+5, a, 14)
        body += f'<path d="M{x1:.1f} {y} H{x2:.1f}" stroke="{COLORS[idx+1]}" stroke-width="5"/>\n'
        body += f'<circle cx="{x:.1f}" cy="{y}" r="7" fill="{COLORS[idx+1]}"/>\n'
        body += svg_text(1000, y+5, f'{item["mean_difference"]:+.1f}', 13, "bold")
    body += svg_text(260, 530, 'ACAG/GA − ACA (negative = improvement); paired bootstrap 95% intervals', 14)
    body += svg_text(260, 556, 'Exploratory; intervals are not multiplicity-adjusted', 13, color="#64748b")
    return canvas(body, f'{instance} | Paired effects against ACA',
                  f'{n} seeds · {budget} objective evaluations · each comparison uses identical seed IDs')


def convergence_figure(instance: str, curves: dict[str, list[float]],
                       n: int, budget: int) -> str:
    hi = max(v[0] for v in curves.values())
    lo = min(v[-1] for v in curves.values())
    padding = max(10, (hi-lo)*.08)
    hi, lo = hi+padding, lo-padding
    left, right, top, bottom = 92, 1042, 130, 485
    body = ''
    for k in range(5):
        y = top+(bottom-top)*k/4
        body += f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#e2e8f0"/>\n'
        body += svg_text(left-15, y+4, f'{hi+(lo-hi)*k/4:.0f}', 12, anchor='end')
    for idx, (label, *_rest) in enumerate(SPECS):
        values = curves[label]
        points = ' '.join(f'{left+(right-left)*i/max(1,len(values)-1):.1f},'
                          f'{top+(hi-value)/(hi-lo)*(bottom-top):.1f}'
                          for i, value in enumerate(values))
        body += f'<polyline points="{points}" fill="none" stroke="{COLORS[idx]}" stroke-width="2.7"/>\n'
        x = 50+idx%4*258
        y = 535+idx//4*26
        body += f'<rect x="{x}" y="{y-10}" width="20" height="5" fill="{COLORS[idx]}"/>\n'
        body += svg_text(x+26, y, label, 12)
    return canvas(body, f'{instance} | Mean best-so-far convergence',
                  f'{n} new paired seeds · x: charged evaluations (1 to {budget}); y: path length', 1100, 610)


def run_experiment(seed_start: int, seeds: int, budget: int, population: int,
                   output: Path) -> None:
    if seeds < 2 or budget < population or population < 2:
        raise ValueError('Require seeds >=2 and budget >= population >=2')
    output.mkdir(parents=True, exist_ok=True)
    figures = ROOT / 'docs' / 'figures' / 'v0.2.0'
    figures.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    summary: dict[str, dict] = {}
    checkpoints = sorted(set([1] + list(range(20, budget+1, 20)) + [budget]))
    trace_rows: list[dict] = []
    tests: list[tuple[str, str, float]] = []
    for file_name in ('eil51.tsp', 'berlin52.tsp'):
        tsp = TSP.from_tsplib(ROOT / 'data' / file_name)
        results: dict[str, dict[int, object]] = {spec[0]: {} for spec in SPECS}
        for seed in range(seed_start, seed_start+seeds):
            for label, alg, switch, transfer in SPECS:
                result = Solver(tsp, seed=seed, budget=budget, population=population,
                                switch_policy=switch, transfer_policy=transfer).run(alg)
                assert result.evaluations == budget and len(result.history) == budget
                results[label][seed] = result
                rows.append(dict(instance=tsp.name, seed=seed, treatment=label,
                                 best_length=result.length, evaluations=result.evaluations,
                                 switch_at=result.switch_evaluation or '',
                                 local_search_evaluations=result.local_search_evaluations))
        stats: dict = {}
        curves: dict = {}
        for label, *_ in SPECS:
            res = [results[label][seed] for seed in range(seed_start, seed_start+seeds)]
            vals = [r.length for r in res]
            stats[label] = dict(mean=statistics.mean(vals), sd=statistics.stdev(vals),
                                median=statistics.median(vals), best=min(vals),
                                mean_gap_pct=(statistics.mean(vals)/OPTIMA[tsp.name]-1)*100,
                                mean_local_search_evaluations=statistics.mean(
                                    r.local_search_evaluations for r in res),
                                mean_switch_evaluation=statistics.mean(
                                    [r.switch_evaluation for r in res if r.switch_evaluation is not None])
                                    if any(r.switch_evaluation is not None for r in res) else None)
            curves[label] = [statistics.mean(results[label][seed].history[k-1][1]
                              for seed in range(seed_start, seed_start+seeds))
                             for k in checkpoints]
        for label, trace in curves.items():
            for evaluation, mean_value in zip(checkpoints, trace):
                trace_rows.append(dict(instance=tsp.name, treatment=label,
                                       evaluation=evaluation, mean_best_so_far=mean_value))
        baseline = [results['ACA'][seed].length for seed in range(seed_start, seed_start+seeds)]
        effects = {}
        for label, *_ in SPECS[1:]:
            delta = [results[label][seed].length - baseline[i]
                     for i, seed in enumerate(range(seed_start, seed_start+seeds))]
            p = paired_randomization_p(delta)
            tests.append((tsp.name, label, p))
            effects[label] = dict(mean_difference=statistics.mean(delta),
                                  bootstrap95=interval(delta),
                                  wins=sum(x < 0 for x in delta),
                                  ties=sum(x == 0 for x in delta),
                                  losses=sum(x > 0 for x in delta),
                                  signflip_p=p)
        summary[tsp.name] = dict(known_optimum=OPTIMA[tsp.name], summary=stats,
                                 vs_aca=effects)
        (figures / f'{tsp.name}-gap.svg').write_text(
            gap_figure(tsp.name, stats, seeds, budget), encoding='utf-8')
        (figures / f'{tsp.name}-effects.svg').write_text(
            effect_figure(tsp.name, effects, seeds, budget), encoding='utf-8')
        (figures / f'{tsp.name}-convergence.svg').write_text(
            convergence_figure(tsp.name, curves, seeds, budget), encoding='utf-8')
    ordered = sorted(tests, key=lambda v: v[2])
    n = len(tests)
    holm = {}
    max_adjusted = 0.0
    for i, (instance, label, p) in enumerate(ordered):
        max_adjusted = max(max_adjusted, min(1.0, p*(n-i)))
        holm[(instance, label)] = max_adjusted
    for instance, label, _ in tests:
        summary[instance]['vs_aca'][label]['holm_signflip_p'] = holm[(instance, label)]
    metadata = dict(version='v0.2.0', protocol='exploratory post-v0.1.0 correction',
                    seed_start=seed_start, seed_count=seeds, budget=budget,
                    population=population, nearest_candidates=5,
                    switch_policies=['stagnation', '25%', '50%', '75%'],
                    baselines=['ACA', 'GA'],
                    budget_note='Every full tour objective call counts, including local search trials',
                    uncertainty_note='Unadjusted paired bootstrap intervals; Holm-corrected sign-flip MC p-values are exploratory',
                    tables=summary)
    def write_csv(name: str, data: list[dict]) -> None:
        with (output / name).open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(data)
    write_csv('ablation_v0.2.0.csv', rows)
    write_csv('convergence_v0.2.0.csv', trace_rows)
    (output / 'summary_v0.2.0.json').write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    for instance in summary:
        print(instance)
        for label, item in summary[instance]['summary'].items():
            print(f'  {label:19} mean={item["mean"]:.2f}  gap={item["mean_gap_pct"]:.2f}%')
        for label, effect in summary[instance]['vs_aca'].items():
            print(f'  Δ {label:19} {effect["mean_difference"]:+.2f}  '
                  f'CI[{effect["bootstrap95"][0]:+.1f},{effect["bootstrap95"][1]:+.1f}] '
                  f'Holm p={effect["holm_signflip_p"]:.4f}')


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--seed-start', type=int, default=100)
    p.add_argument('--seeds', type=int, default=30)
    p.add_argument('--budget', type=int, default=1000)
    p.add_argument('--population', type=int, default=20)
    p.add_argument('--out', type=Path, default=ROOT / 'results')
    args = p.parse_args()
    run_experiment(args.seed_start, args.seeds, args.budget, args.population, args.out)


if __name__ == '__main__':
    main()
