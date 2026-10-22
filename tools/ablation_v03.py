"""v0.3.0 exploratory budget-controlled 2-opt vs adjacent mutation study.

Scientific scope: no claim of new-instance generalization. Reproducible seed IDs
are deliberately disjoint from v0.2.0. Full-tour objective calls always charged.
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
from tools.ablation_v02 import canvas, interval, paired_randomization_p, svg_text  # noqa: E402

OPTIMA = {"eil51": 426, "berlin52": 7542}
SPECS = (
    ("ACA", "aca", "never", "adjacent", .3, 0.),
    ("ACA+2opt", "aca_2opt", "never", "2opt", .3, 0.),
    ("ACA75-polish", "aca_polish", "fixed75", "2opt", .3, 0.),
    ("GA-adj", "ga", "never", "adjacent", .3, 0.),
    ("GA-2opt", "ga", "never", "2opt", .3, 0.),
    ("ACAG50-adj", "acag", "fixed50", "adjacent", .3, 0.),
    ("ACAG50-2opt", "acag", "fixed50", "2opt", .3, 0.),
    ("ACAG75-2opt", "acag", "fixed75", "2opt", .3, 0.),
    ("ACAG-stall-2opt", "acag", "stagnation", "2opt", .3, 0.),
    ("ACAG50-elite2opt", "acag", "fixed50", "2opt", .3, .5),
    ("ACAG75-elite2opt", "acag", "fixed75", "2opt", .3, .5),
)
COLORS = ["#64748b", "#b45309", "#ca8a04", "#94a3b8", "#a855f7", "#dc2626", "#2563eb", "#059669", "#7c3aed", "#0891b2", "#16a34a"]


def holm(pvals: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(pvals, key=lambda x: x[1])
    corrected: dict[str, float] = {}
    maximum = 0.0
    for i, (label, p) in enumerate(ordered):
        maximum = max(maximum, min(1.0, p * (len(ordered) - i)))
        corrected[label] = maximum
    return corrected


def draw_means(instance: str, stats: dict[str, dict], budget: int, n: int) -> str:
    vmax = max(stats[x[0]]["mean"] for x in SPECS)
    body = ''
    for i, (name, *_rest) in enumerate(SPECS):
        y = 122 + i*45
        w = 570*stats[name]["mean"]/vmax
        body += svg_text(36, y+18, name, 16)
        body += f'<rect x="245" y="{y}" width="{w:.1f}" height="28" rx="4" fill="{COLORS[i]}"/>\n'
        body += svg_text(252+w, y+20, f'{stats[name]["mean"]:.1f}', 15, "bold")
    return canvas(body, f'{instance} | Mean tour length by method',
                  f'{n} independent paired seeds · {budget} charged full-tour evaluations · lower is better',
                  1100, 715)


def draw_zoom(instance: str, stats: dict[str,dict], budget: int, n: int) -> str:
    names = [row[0] for row in SPECS if row[0] not in ('GA-adj','GA-2opt')]
    xmax=max(stats[x]['mean_gap_pct'] for x in names)*1.12
    body=''
    for idx,name in enumerate(names):
        y=124+idx*51
        gap=stats[name]['mean_gap_pct']
        width=600*gap/xmax
        col=COLORS[[row[0] for row in SPECS].index(name)]
        body+=svg_text(36,y+19,name,15)
        body+=f'<rect x="265" y="{y}" width="{width:.1f}" height="29" rx="3" fill="{col}"/>\n'
        body+=svg_text(276+width,y+19,f'{gap:.2f}%',14,"bold")
    body+=svg_text(265,652,'Gap = 100 × (mean best length / TSPLIB known optimum − 1)',14)
    body+=svg_text(265,677,'GA variants excluded from zoom; see unzoomed means chart.',13,color='#64748b')
    return canvas(body,f'{instance} | Zoomed optimality gap',
                 f'{n} exploratory seeds · {budget} objective calls · lower is better',1100,720)


def draw_effects(instance: str, effects: dict, budget: int, n: int, baseline: str) -> str:
    labels = [row[0] for row in SPECS if row[0] != baseline]
    lo = min(0, *(effects[name]["bootstrap95"][0] for name in labels))
    hi = max(0, *(effects[name]["bootstrap95"][1] for name in labels))
    pad = max(10.0, (hi-lo)*.09)
    lo, hi = lo-pad, hi+pad
    def conv(x):return 270+(x-lo)*650/(hi-lo)
    xzero=conv(0)
    body=f'<line x1="{xzero:.2f}" x2="{xzero:.2f}" y1="116" y2="575" stroke="#0f172a" stroke-width="2" stroke-dasharray="6,5"/>\n'
    for i, label in enumerate(labels):
        y=131+i*42
        stat=effects[label]
        color=COLORS[[c[0] for c in SPECS].index(label)]
        x1,x2=map(conv,stat['bootstrap95'])
        xm=conv(stat['mean_difference'])
        body+=svg_text(28,y+5,label,14)
        body+=f'<path d="M{x1:.2f} {y} H{x2:.2f}" stroke="{color}" stroke-width="5"/>\n'
        body+=f'<circle cx="{xm:.2f}" cy="{y}" r="7" fill="{color}"/>\n'
        body+=svg_text(944,y+5,f'{stat["mean_difference"]:+.1f}',13,"bold")
    body+=svg_text(50,605,f'Difference = treatment − {baseline} (negative is better). Paired percentile bootstrap CI.',13)
    body+=svg_text(50,629,'Exploratory comparisons; unadjusted 95% intervals, Holm-adjusted tests in JSON.',12,color='#64748b')
    return canvas(body,f'{instance} | Paired performance vs {baseline}',
                  f'{n} new seeds · {budget} evaluations per run',1100,665)


def draw_convergence(instance: str, curves: dict[str,list[float]], checkpoints:list[int],
                     budget:int,n:int) -> str:
    selected=["ACA","ACA75-polish","ACAG50-adj","ACAG50-2opt","ACAG75-elite2opt"]
    vmax=max(max(curves[label]) for label in selected)
    vmin=min(min(curves[label]) for label in selected)
    pad=max(8.,(vmax-vmin)*.1)
    hi,lo=vmax+pad,vmin-pad
    left,right,top,bottom=92,1050,130,490
    body=''
    for i in range(5):
        y=top+(bottom-top)*i/4
        body+=f'<path d="M{left} {y:.2f} H{right}" stroke="#cbd5e1"/>\n'
        body+=svg_text(76,y+4,f'{hi+(lo-hi)*i/4:.0f}',12,anchor="end")
    for label in selected:
        j=[row[0] for row in SPECS].index(label)
        points=' '.join(f'{left+(right-left)*(x-1)/max(1,budget-1):.2f},'
                        f'{bottom-(v-lo)*(bottom-top)/(hi-lo):.2f}'
                        for x,v in zip(checkpoints,curves[label]))
        body+=f'<polyline points="{points}" stroke="{COLORS[j]}" stroke-width="3" fill="none"/>\n'
        y=531+selected.index(label)*25
        body+=f'<rect x="80" y="{y-11}" width="25" height="5" fill="{COLORS[j]}"/>\n'
        body+=svg_text(117,y,label,13)
    return canvas(body,f'{instance} | Budget-aligned convergence',
                  f'{n} fresh seeds · x axis: exact charged tour evaluations 1–{budget}; y: mean best-so-far',
                  1100,695)


def run(seed_start:int=200,seeds:int=12,budget:int=1000,population:int=20,
        two_opt_trials:int=8, root:Path=ROOT, print_report:bool=True)->dict:
    if seeds<2 or population<2 or budget<population or two_opt_trials<1:
        raise ValueError('Require seeds >= 2, budget >= population >=2, trials >= 1')
    results_dir=root/'results'; fig_dir=root/'docs'/'figures'/'v0.3.0'
    results_dir.mkdir(parents=True,exist_ok=True)
    fig_dir.mkdir(parents=True,exist_ok=True)
    rows=[]; curves_rows=[]; report={"metadata":{"seed_start":seed_start,"seeds":seeds,"budget":budget,
        "population":population,"two_opt_trials":two_opt_trials,"instances":["eil51","berlin52"],
        "evaluation_unit":"one complete TSP tour objective call including rejected LS proposals",
        "status":"exploratory, not holdout generalization"},"instances":{}}
    checkpoints=sorted(set([1]+list(range(20,budget+1,20))+[budget]))
    pvals=[]
    for file in ('eil51.tsp','berlin52.tsp'):
        tsp=TSP.from_tsplib(root/'data'/file)
        by_label={label:{} for label,*_ in SPECS}
        for seed in range(seed_start,seed_start+seeds):
            for label,algorithm,switch,mutation,pm,elite_rate in SPECS:
                solver=Solver(tsp,seed=seed,budget=budget,population=population,
                              switch_policy=switch,mutation_policy=mutation,pm=pm,
                              two_opt_trials=two_opt_trials,elite_polish_rate=elite_rate)
                res=solver.run(algorithm)
                if res.evaluations!=budget or len(res.history)!=budget:
                    raise AssertionError(f'Budget/accounting failure: {label} {seed}')
                if tsp.length(res.tour)!=res.length:
                    raise AssertionError('Final tour length mismatch')
                by_label[label][seed]=res
                rows.append({"instance":tsp.name,"seed":seed,"treatment":label,
                             "best_length":res.length,"gap_pct":round(100*(res.length/OPTIMA[tsp.name]-1),6),
                             "evaluations":res.evaluations,"switch_at":res.switch_evaluation or '',
                             "local_search_evaluations":res.local_search_evaluations})
        stats={};curves={};effects_aca={};effects_aca2={}
        for label,*_ in SPECS:
            rs=[by_label[label][seed] for seed in range(seed_start,seed_start+seeds)]
            ls=[r.length for r in rs]
            stats[label]={"mean":statistics.mean(ls),"median":statistics.median(ls),
                          "sd":statistics.stdev(ls),"min":min(ls),"max":max(ls),
                          "mean_gap_pct":100*(statistics.mean(ls)/OPTIMA[tsp.name]-1),
                          "mean_local_search_evaluations":statistics.mean(r.local_search_evaluations for r in rs),
                          "mean_switch_evaluation":statistics.mean([r.switch_evaluation for r in rs if r.switch_evaluation is not None])
                          if any(r.switch_evaluation is not None for r in rs) else None}
            curves[label]=[statistics.mean(r.history[k-1][1] for r in rs) for k in checkpoints]
            for k,mean in zip(checkpoints,curves[label]):
                curves_rows.append({"instance":tsp.name,"treatment":label,"evaluation":k,"mean_best_so_far":mean})
        for baseline, dest in [("ACA",effects_aca),("ACA+2opt",effects_aca2)]:
            for label,*_ in SPECS:
                if label==baseline:continue
                deltas=[by_label[label][seed].length-by_label[baseline][seed].length
                        for seed in range(seed_start,seed_start+seeds)]
                p=paired_randomization_p(deltas)
                dest[label]={"mean_difference":statistics.mean(deltas),"bootstrap95":interval(deltas),
                             "wins":sum(x<0 for x in deltas),"ties":sum(x==0 for x in deltas),
                             "losses":sum(x>0 for x in deltas),"randomization_p":p}
                pvals.append((f'{tsp.name}/{baseline}/{label}',p))
        report['instances'][tsp.name]={"known_optimum":OPTIMA[tsp.name],"statistics":stats,
                        "effects_vs_ACA":effects_aca,"effects_vs_ACA+2opt":effects_aca2}
        (fig_dir/f'{tsp.name}-means.svg').write_text(draw_means(tsp.name,stats,budget,seeds),encoding='utf8')
        (fig_dir/f'{tsp.name}-zoom-gap.svg').write_text(draw_zoom(tsp.name,stats,budget,seeds),encoding='utf8')
        (fig_dir/f'{tsp.name}-effects-vs-aca.svg').write_text(draw_effects(tsp.name,effects_aca,budget,seeds,'ACA'),encoding='utf8')
        (fig_dir/f'{tsp.name}-effects-vs-aca-2opt.svg').write_text(draw_effects(tsp.name,effects_aca2,budget,seeds,'ACA+2opt'),encoding='utf8')
        (fig_dir/f'{tsp.name}-convergence.svg').write_text(draw_convergence(tsp.name,curves,checkpoints,budget,seeds),encoding='utf8')
        if print_report:
            print(tsp.name,':',' | '.join(f'{label} {stats[label]["mean"]:.2f}' for label,*_ in SPECS),flush=True)
    adjusted=holm(pvals)
    for name, data in report['instances'].items():
        for baseline, key in [('ACA','effects_vs_ACA'),('ACA+2opt','effects_vs_ACA+2opt')]:
            for label, v in data[key].items():
                v['holm_p_all_comparisons']=adjusted[f'{name}/{baseline}/{label}']
    with (results_dir/'ablation_v0.3.0.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (results_dir/'convergence_v0.3.0.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(curves_rows[0]));writer.writeheader();writer.writerows(curves_rows)
    (results_dir/'summary_v0.3.0.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    return report

if __name__ == '__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--seed-start',type=int,default=200)
    a.add_argument('--seeds',type=int,default=12)
    a.add_argument('--budget',type=int,default=1000)
    a.add_argument('--population',type=int,default=20)
    a.add_argument('--two-opt-trials',type=int,default=8)
    args=a.parse_args()
    run(**vars(args))
