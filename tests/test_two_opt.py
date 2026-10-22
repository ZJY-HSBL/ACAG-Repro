"""v0.3.0 mutation, tail polishing, archive-feedback and accounting regressions."""
from pathlib import Path

import pytest

from acag import Solver, TSP
from tools.ablation_v03 import SPECS, holm

TSP_PATH = Path(__file__).resolve().parents[1] / 'data' / 'eil51.tsp'


@pytest.mark.parametrize('algorithm,switch,mutation,rate', [
    ('aca_2opt', 'never', '2opt', 0.),
    ('aca_polish', 'fixed75', '2opt', 0.),
    ('aca_polish', 'fixed50', '2opt', 0.),
    ('acag', 'fixed50', '2opt', .5),
    ('acag', 'fixed75', '2opt', .5),
    ('acag', 'stagnation', '2opt', 0.),
    ('ga', 'never', '2opt', 0.),
])
def test_full_tour_accounting(monkeypatch, algorithm, switch, mutation, rate):
    tsp = TSP.from_tsplib(TSP_PATH)
    original = TSP.length
    counted = []

    def audit(self, tour):
        counted.append(tuple(tour))
        return original(self, tour)

    monkeypatch.setattr(TSP, 'length', audit)
    res = Solver(tsp, seed=357, population=12, budget=187,
                 switch_policy=switch, mutation_policy=mutation,
                 elite_polish_rate=rate, pm=1.0).run(algorithm)
    assert len(counted) == res.evaluations == len(res.history) == 187
    if algorithm != 'acag' or res.switch_evaluation is not None:
        assert res.local_search_evaluations > 0
    assert res.length == original(tsp, res.tour)
    assert all(len(t) == tsp.n and len(set(t)) == tsp.n for t in counted)


def test_polish_switch_and_reproducibility():
    tsp = TSP.from_tsplib(TSP_PATH)
    run = lambda: Solver(tsp, seed=78, population=12, budget=188,
                         mutation_policy='2opt', switch_policy='fixed75').run('aca_polish')
    x, y = run(), run()
    assert x.as_dict() == y.as_dict()
    assert x.switch_evaluation == 144  # 12-ants-per-generation boundary
    assert x.local_search_evaluations == 44


def test_legacy_default_unchanged():
    tsp = TSP.from_tsplib(TSP_PATH)
    a = Solver(tsp, seed=49, population=15, budget=150,
               switch_policy='fixed50').run('acag')
    b = Solver(tsp, seed=49, population=15, budget=150,
               switch_policy='fixed50', mutation_policy='adjacent',
               elite_polish_rate=0).run('acag')
    assert a.as_dict() == b.as_dict()


@pytest.mark.parametrize('keyword,value', [
    ('mutation_policy', 'genetic'),
    ('two_opt_trials', 0),
    ('two_opt_trials', 1.5),
    ('elite_polish_rate', 1.2),
    ('elite_polish_rate', -.1),
])
def test_reject_invalid_params(keyword, value):
    with pytest.raises(ValueError):
        Solver(TSP.from_tsplib(TSP_PATH), **{keyword: value})


def test_predeclared_specs_are_unique_and_holm_monotone():
    assert len({row[0] for row in SPECS}) == len(SPECS)
    assert len(SPECS) == 11
    adjusted = holm([('a', .001), ('b', .012), ('c', .99)])
    assert 0 <= adjusted['a'] <= adjusted['b'] <= adjusted['c'] <= 1
