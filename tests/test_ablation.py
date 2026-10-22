"""Accounting, switch mechanics, and reproducibility regression tests."""
from pathlib import Path

import pytest

from acag import Solver, TSP
from tools.ablation_v02 import interval, paired_randomization_p

TSP_FILE = Path(__file__).resolve().parents[1] / 'data' / 'eil51.tsp'


@pytest.mark.parametrize('algorithm,switch,transfer', [
    ('aca', 'never', 'elite'), ('ga', 'never', 'elite'),
    ('acag', 'stagnation', 'elite'), ('acag', 'fixed25', 'elite'),
    ('acag', 'fixed50', 'elite'), ('acag', 'fixed75', 'elite'),
    ('acag', 'fixed50', 'random'), ('acag', 'never', 'elite'),
])
def test_every_objective_call_charged(monkeypatch, algorithm, switch, transfer):
    original = TSP.length
    calls = []

    def counted(self, tour):
        calls.append(1)
        return original(self, tour)

    monkeypatch.setattr(TSP, 'length', counted)
    tsp = TSP.from_tsplib(TSP_FILE)
    res = Solver(tsp, budget=200, population=10, seed=213,
                 ant_max=2, switch_policy=switch,
                 transfer_policy=transfer).run(algorithm)
    assert res.evaluations == len(calls) == 200
    assert len(res.history) == 200
    assert tsp.n == len(res.tour)
    assert all(res.history[i][1] <= res.history[i-1][1]
               for i in range(1, len(res.history)))


def test_fixed_switch_exact_population_boundary():
    tsp = TSP.from_tsplib(TSP_FILE)
    for policy, threshold in [('fixed25', 100), ('fixed50', 200), ('fixed75', 300)]:
        res = Solver(tsp, seed=9, budget=400, population=20,
                     switch_policy=policy).run('acag')
        assert res.switch_evaluation == threshold


def test_no_switch_matches_aca():
    tsp = TSP.from_tsplib(TSP_FILE)
    aca = Solver(tsp, budget=300, seed=94, population=20).run('aca')
    no_switch = Solver(tsp, budget=300, seed=94, population=20,
                       switch_policy='never').run('acag')
    assert aca.length == no_switch.length
    assert aca.tour == no_switch.tour
    assert aca.history == no_switch.history
    assert no_switch.switch_evaluation is None


def test_legacy_mutation_is_not_called_in_budgeted_ga(monkeypatch):
    import acag
    tsp = TSP.from_tsplib(TSP_FILE)

    def forbidden(*args, **kwargs):
        raise AssertionError('Uncharged mutation was called')

    monkeypatch.setattr(acag, 'adjacent_segment_improve', forbidden)
    result = Solver(tsp, budget=250, seed=7, population=10,
                    pm=1.0).run('ga')
    assert result.local_search_evaluations > 0
    assert result.evaluations == 250


def test_small_unaligned_budget():
    tsp = TSP.from_tsplib(TSP_FILE)
    result = Solver(tsp, budget=133, population=12, seed=99,
                    switch_policy='fixed50').run('acag')
    assert result.evaluations == 133
    assert result.switch_evaluation == 72


@pytest.mark.parametrize('key,value', [('switch_policy', 'adaptive'),
                                       ('transfer_policy', 'unknown')])
def test_invalid_treatment(key, value):
    tsp = TSP.from_tsplib(TSP_FILE)
    with pytest.raises(ValueError):
        Solver(tsp, **{key: value})


def test_ci_statistics_reproducible():
    samples = [1, 3, -2, 4, 0, 5]
    assert interval(samples) == interval(samples)
    assert paired_randomization_p(samples) == paired_randomization_p(samples)
    assert interval(samples)[0] <= interval(samples)[1]
