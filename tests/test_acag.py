import random
from pathlib import Path

import pytest

from acag import TSP, Solver, canonical, ox, adjacent_segment_improve, roulette

INSTANCE = Path(__file__).parents[1] / "data" / "eil51.tsp"


def test_parser_tsplib():
    t = TSP.from_tsplib(INSTANCE)
    assert t.n == 51
    assert t.length(tuple(range(t.n))) > 0
    assert t.distances[0][1] == t.distances[1][0]
    assert t.distances[0][0] == 0


def test_parser_rejects_unsupported(tmp_path):
    f = tmp_path / "bad.tsp"
    f.write_text("NAME: x\nTYPE: TSP\nDIMENSION: 3\nEDGE_WEIGHT_TYPE: GEO\nNODE_COORD_SECTION\n1 0 0\n2 1 1\n3 2 2\nEOF")
    with pytest.raises(ValueError, match="EUC_2D"):
        TSP.from_tsplib(f)


def test_ox_and_mutation_permutations():
    t = TSP.from_tsplib(INSTANCE)
    rng = random.Random(12)
    for _ in range(50):
        p1 = tuple(rng.sample(range(t.n), t.n))
        p2 = tuple(rng.sample(range(t.n), t.n))
        child = ox(p1, p2, rng)
        mutant = adjacent_segment_improve(t, child, rng)
        assert sorted(child) == list(range(t.n))
        assert sorted(mutant) == list(range(t.n))
        assert t.length(mutant) <= t.length(child)


def test_roulette_zero():
    assert roulette([0., 0., 0.], random.Random(0)) in range(3)


def test_canonical_rotation_reverse():
    assert canonical((2, 0, 1, 3)) == canonical((0, 2, 3, 1))


@pytest.mark.parametrize("algorithm", ["aca", "ga", "acag"])
def test_valid_budget_reproducible(algorithm):
    t = TSP.from_tsplib(INSTANCE)
    kwargs = dict(seed=123, budget=80, population=10, ant_max=2)
    a = Solver(t, **kwargs).run(algorithm)
    b = Solver(t, **kwargs).run(algorithm)
    assert a.as_dict() == b.as_dict()
    assert len(a.history) == 80
    assert a.evaluations == 80
    assert t.length(a.tour) == a.length
    assert all(x[1] >= y[1] for x, y in zip(a.history, a.history[1:]))


def test_forced_switch():
    t = TSP.from_tsplib(INSTANCE)
    result = Solver(t, seed=1, budget=90, population=10,
                    ant_max=1, min_ratio=.99).run("acag")
    assert result.switch_evaluation is not None
    assert 0 < result.switch_evaluation < result.evaluations


def test_bad_tour():
    t = TSP.from_tsplib(INSTANCE)
    with pytest.raises(ValueError):
        t.length(tuple([0]*t.n))
