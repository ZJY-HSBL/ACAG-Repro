"""Reproducible, budget-aware ACA, GA and ACAG for symmetric TSPLIB EUC_2D TSP.

The core operators follow Sheng, Xu & Xu (2022). Underspecified policies are
recorded in README; this is not a claim of bit-exact reproduction.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TSP:
    name: str
    points: tuple[tuple[float, float], ...]
    distances: tuple[tuple[int, ...], ...]

    @classmethod
    def from_tsplib(cls, path: str | Path) -> TSP:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        meta: dict[str, str] = {}
        coords: dict[int, tuple[float, float]] = {}
        section = False
        for raw in lines:
            line = raw.strip()
            if not line or line == "EOF":
                continue
            if line == "NODE_COORD_SECTION":
                section = True
                continue
            if section:
                parts = line.split()
                if len(parts) != 3:
                    raise ValueError(f"Malformed coordinate: {line}")
                index = int(parts[0])
                if index in coords:
                    raise ValueError("Duplicate node ID")
                coords[index] = (float(parts[1]), float(parts[2]))
            elif ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip().upper()] = value.strip()
            else:
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    meta[parts[0].upper()] = parts[1]
        if meta.get("TYPE", "TSP") != "TSP" or meta.get("EDGE_WEIGHT_TYPE") != "EUC_2D":
            raise ValueError("Only symmetric TSPLIB EUC_2D TSP is supported")
        n = int(meta.get("DIMENSION", 0))
        if n < 3 or set(coords) != set(range(1, n + 1)):
            raise ValueError("City IDs must be 1..DIMENSION and dimension >= 3")
        points = tuple(coords[i] for i in range(1, n + 1))
        # TSPLIB nint(x) = floor(x + .5), not Python's banker's round.
        dist = tuple(tuple(0 if i == j else math.floor(
            math.hypot(points[i][0] - points[j][0],
                       points[i][1] - points[j][1]) + 0.5)
            for j in range(n)) for i in range(n))
        return cls(meta.get("NAME", Path(path).stem), points, dist)

    @property
    def n(self) -> int:
        return len(self.points)

    def length(self, tour: tuple[int, ...] | list[int]) -> int:
        if len(tour) != self.n or set(tour) != set(range(self.n)):
            raise ValueError("Tour must be a permutation of all cities")
        return sum(self.distances[tour[i]][tour[(i+1) % self.n]]
                   for i in range(self.n))


@dataclass
class Result:
    algorithm: str
    seed: int
    length: int
    tour: tuple[int, ...]
    evaluations: int
    history: list[tuple[int, int]]
    switch_evaluation: int | None = None
    local_search_evaluations: int = 0

    def as_dict(self) -> dict:
        return dict(algorithm=self.algorithm, seed=self.seed, length=self.length,
                    tour=[x + 1 for x in self.tour], evaluations=self.evaluations,
                    history=self.history, switch_evaluation=self.switch_evaluation,
                    local_search_evaluations=self.local_search_evaluations)


def canonical(tour: tuple[int, ...]) -> tuple[int, ...]:
    """Remove equivalent rotation and orientation of a symmetric TSP tour."""
    index = tour.index(0)
    rotated = tour[index:] + tour[:index]
    reversed_tour = (0,) + tuple(reversed(rotated[1:]))
    return min(rotated, reversed_tour)


def roulette(weights: list[float], rng: random.Random) -> int:
    if any(not math.isfinite(x) or x < 0 for x in weights):
        raise ValueError("Weights must be finite nonnegative numbers")
    total = sum(weights)
    if total <= 0:
        return rng.randrange(len(weights))
    threshold = rng.random() * total
    acc = 0.0
    for i, weight in enumerate(weights):
        acc += weight
        if threshold < acc:
            return i
    return len(weights) - 1


def ox(parent1: tuple[int, ...], parent2: tuple[int, ...],
       rng: random.Random) -> tuple[int, ...]:
    """Davis order crossover (OX), preserving a section of parent1."""
    n = len(parent1)
    a, b = sorted(rng.sample(range(n), 2))
    child: list[int | None] = [None] * n
    child[a:b+1] = parent1[a:b+1]
    used = set(parent1[a:b+1])
    remaining = [parent2[(b+1+i) % n] for i in range(n)
                 if parent2[(b+1+i) % n] not in used]
    for j, gene in enumerate(remaining):
        child[(b + 1 + j) % n] = gene
    out = tuple(child)
    assert len(set(out)) == n and None not in out
    return out  # type: ignore[return-value]


def adjacent_segment_improve(tsp: TSP, parent: tuple[int, ...],
                             rng: random.Random) -> tuple[int, ...]:
    """Paper section 4.2: accept improving adjacent swaps in a random segment."""
    a, b = sorted(rng.sample(range(tsp.n), 2))
    trial = list(parent)
    length = tsp.length(trial)
    for i in range(a, b):
        trial[i], trial[i+1] = trial[i+1], trial[i]
        candidate = tsp.length(trial)
        if candidate < length:
            length = candidate
        else:
            trial[i], trial[i+1] = trial[i+1], trial[i]
    return tuple(trial)


class Solver:
    """All algorithms are capped by the same number of evaluated full tours."""

    def __init__(self, tsp: TSP, seed: int = 0, budget: int = 600,
                 population: int = 20, candidates: int = 5,
                 q0: float = .8, beta: float = 3., rho: float = .15,
                 q: float = 1000., q1: float = 1., q2: float = 5.,
                 pc: float = .8, pm: float = .3, ant_max: int = 8,
                 min_ratio: float = .01, switch_policy: str = "stagnation",
                 transfer_policy: str = "elite", mutation_policy: str = "adjacent",
                 two_opt_trials: int = 8, elite_polish_rate: float = 0.):
        if budget < population or population < 2 or tsp.n < 3:
            raise ValueError("Need budget >= population >= 2 and >=3 cities")
        if not (0 <= q0 <= 1 and 0 < rho < 1 and 0 <= pc <= 1
                and 0 <= pm <= 1 and q > 0 and q1 >= 0 and q2 >= 0
                and beta >= 0 and ant_max >= 1 and 0 <= min_ratio < 1):
            raise ValueError("Invalid algorithm parameter")
        self.tsp = tsp
        self.rng = random.Random(seed)
        self.seed = seed
        self.budget = budget
        self.population = population
        self.candidates = max(1, min(candidates, tsp.n - 1))
        self.q0, self.beta, self.rho = q0, beta, rho
        self.q, self.q1, self.q2 = q, q1, q2
        self.pc, self.pm = pc, pm
        if switch_policy not in ("stagnation", "fixed25", "fixed50", "fixed75", "never"):
            raise ValueError("Unsupported switch policy")
        if transfer_policy not in ("elite", "random"):
            raise ValueError("Unsupported transfer policy")
        self.ant_max, self.min_ratio = ant_max, min_ratio
        self.switch_policy, self.transfer_policy = switch_policy, transfer_policy
        if mutation_policy not in ("adjacent", "2opt"):
            raise ValueError("Unsupported mutation operator")
        if not isinstance(two_opt_trials, int) or two_opt_trials < 1:
            raise ValueError("two_opt_trials must be a positive integer")
        if not 0 <= elite_polish_rate <= 1:
            raise ValueError("elite_polish_rate must be between 0 and 1")
        self.mutation_policy, self.two_opt_trials = mutation_policy, two_opt_trials
        self.elite_polish_rate = elite_polish_rate
        self.local_search_evaluations = 0
        self.best = math.inf
        self.tour: tuple[int, ...] = ()
        self.evals = 0
        self.history: list[tuple[int, int]] = []
        self.pheromone = [[1.0 for _ in range(tsp.n)] for _ in range(tsp.n)]
        self.tau0 = 1.0
        self.near = [[j for j in sorted(range(tsp.n),
                            key=lambda j: (tsp.distances[i][j], j)) if j != i]
                     for i in range(tsp.n)]
        self.archive: dict[tuple[int, ...], int] = {}

    def evaluate(self, tour: tuple[int, ...]) -> int:
        if self.evals >= self.budget:
            raise RuntimeError("Function evaluation budget exceeded")
        value = self.tsp.length(tour)
        self.evals += 1
        if value < self.best:
            self.best, self.tour = value, tour
        self.history.append((self.evals, int(self.best)))
        return value

    def _ant(self) -> tuple[int, ...]:
        rng, n = self.rng, self.tsp.n
        start = rng.randrange(n)
        visited = {start}
        tour = [start]
        while len(tour) < n:
            i = tour[-1]
            options = [j for j in self.near[i][:self.candidates]
                       if j not in visited]
            if not options:
                # Fallback follows paper section 4.1: nearest unvisited city.
                options = [next(j for j in self.near[i] if j not in visited)]
            weights = [max(self.pheromone[i][j], 1e-12) *
                       (1 / max(self.tsp.distances[i][j], 1e-12)) ** self.beta
                       for j in options]
            if rng.random() < self.q0:
                j = options[max(range(len(options)), key=lambda k: weights[k])]
            else:
                j = options[roulette(weights, rng)]
            visited.add(j)
            tour.append(j)
            # Local update: eq. (6), bounded to keep probabilistic weights valid.
            old = self.pheromone[i][j]
            delta = (self.q1 if old < self.tau0 else -self.q2) / max(
                self.tsp.distances[i][j], 1e-12)
            new = max(1e-12, (1-self.rho)*old + delta)
            self.pheromone[i][j] = self.pheromone[j][i] = new
        return tuple(tour)

    def _two_opt_search(self, start: tuple[int, ...], score: int,
                        trials: int | None = None) -> tuple[tuple[int, ...], int]:
        """Budget-charged stochastic 2-opt; each candidate is a complete tour.

        The complete reversed permutation is evaluated through evaluate(), and
        not by a free four-edge delta oracle. Failed proposals are charged too.
        """
        best_tour, best_score = start, score
        for _ in range(self.two_opt_trials if trials is None else trials):
            if self.evals >= self.budget:
                break
            a, b = sorted(self.rng.sample(range(self.tsp.n), 2))
            if b - a < 2 or b - a == self.tsp.n - 1:
                # Still evaluate a legitimate 2-opt proposal rather than
                # consuming RNG draws without counting a function call.
                a, b = 0, self.tsp.n - 2
            candidate = (best_tour[:a] + tuple(reversed(best_tour[a:b+1]))
                         + best_tour[b+1:])
            candidate_score = self.evaluate(candidate)
            self.local_search_evaluations += 1
            if candidate_score < best_score:
                best_tour, best_score = candidate, candidate_score
        return best_tour, best_score

    def _ants_generation(self, count: int, improve_ants: bool = False) -> bool:
        old_best = self.best
        best_round: tuple[int, ...] | None = None
        round_value = math.inf
        for _ in range(count):
            if self.evals >= self.budget:
                break
            path = self._ant()
            value = self.evaluate(path)
            if improve_ants:
                path, value = self._two_opt_search(path, value)
            key = canonical(path)
            self.archive[key] = min(value, self.archive.get(key, math.inf))
            if value < round_value:
                best_round, round_value = path, value
        # Global pheromone update: evaporation, then cycle-best deposit, eq. (7).
        self.pheromone = [[max(1e-12, v*(1-self.rho)) for v in row]
                          for row in self.pheromone]
        assert best_round is not None
        for i in range(self.tsp.n):
            a, b = best_round[i], best_round[(i+1) % self.tsp.n]
            self.pheromone[a][b] += self.q / max(round_value, 1)
            self.pheromone[b][a] = self.pheromone[a][b]
        if old_best == math.inf:
            return True
        return self.best < old_best * (1 - self.min_ratio)

    def _population_from_archive(self) -> tuple[list[tuple[int, ...]], list[int]]:
        """Archive solutions were already charged during ACA; never evaluate free tours."""
        ranked = sorted(self.archive, key=lambda p: (self.archive[p], p))
        if not ranked:
            raise RuntimeError("Cannot transfer from an empty ACA archive")
        members = ranked[:self.population]
        # Duplicates of already evaluated tours are allowed only if there are
        # fewer distinct archived tours than members. No unevaluated filler.
        while len(members) < self.population:
            members.append(ranked[len(members) % len(ranked)])
        return members, [self.archive[p] for p in members]

    def _ga_step(self, members: list[tuple[int, ...]],
                 scores: list[int]) -> tuple[tuple[int, ...], int]:
        """Charge every evaluated complete tour, including local-search trials."""
        weights = [1 / max(f, 1) for f in scores]
        p1 = members[roulette(weights, self.rng)]
        p2 = members[roulette(weights, self.rng)]
        child = ox(p1, p2, self.rng) if self.rng.random() < self.pc else p1
        score = self.evaluate(child)
        if self.rng.random() >= self.pm or self.evals >= self.budget:
            return child, score
        if self.mutation_policy == "2opt":
            return self._two_opt_search(child, score)
        a, b = sorted(self.rng.sample(range(self.tsp.n), 2))
        trial = list(child)
        for i in range(a, b):
            if self.evals >= self.budget:
                break
            trial[i], trial[i + 1] = trial[i + 1], trial[i]
            candidate_score = self.evaluate(tuple(trial))
            self.local_search_evaluations += 1
            if candidate_score < score:
                score = candidate_score
            else:
                trial[i], trial[i + 1] = trial[i + 1], trial[i]
        return tuple(trial), score

    def run(self, algorithm: str = "acag") -> Result:
        if algorithm not in ("aca", "ga", "acag", "aca_2opt", "aca_polish"):
            raise ValueError("Choose aca, ga, acag, aca_2opt or aca_polish")
        switch: int | None = None
        if algorithm == "ga":
            population = [tuple(self.rng.sample(range(self.tsp.n), self.tsp.n))
                          for _ in range(min(self.population, self.budget))]
            scores = [self.evaluate(p) for p in population]
        else:
            stalled = 0
            thresholds = {"fixed25": .25, "fixed50": .50, "fixed75": .75}
            while self.evals < self.budget:
                count = min(self.population, self.budget - self.evals)
                improved = self._ants_generation(count, improve_ants=algorithm == "aca_2opt")
                stalled = 0 if improved else stalled + 1
                policy = self.switch_policy
                trigger = (stalled >= self.ant_max if policy == "stagnation"
                           else self.evals >= math.ceil(self.budget * thresholds[policy])
                           if policy in thresholds else False)
                if algorithm in ("acag", "aca_polish") and trigger and self.evals < self.budget:
                    switch = self.evals
                    break
            if algorithm in ("aca", "aca_2opt") or switch is None:
                return self._result(algorithm, switch)
            if algorithm == "aca_polish":
                while self.evals < self.budget:
                    self._two_opt_search(self.tour, int(self.best), trials=1)
                return self._result(algorithm, switch)
            if self.transfer_policy == "elite":
                population, scores = self._population_from_archive()
            else:
                population = [tuple(self.rng.sample(range(self.tsp.n), self.tsp.n))
                              for _ in range(min(self.population, self.budget-self.evals))]
                scores = [self.evaluate(p) for p in population]
        while self.evals < self.budget:
            if (algorithm == "acag" and self.elite_polish_rate > 0 and
                    self.rng.random() < self.elite_polish_rate):
                old_best = self.best
                improved_tour, improved_value = self._two_opt_search(
                    self.tour, int(self.best), trials=1)
                if improved_value < old_best:
                    # Bidirectional transfer: evaluated GA-stage elite 2-opt
                    # refinement flows back into the evolving GA population.
                    worst_idx = max(range(len(scores)), key=lambda i: scores[i])
                    population[worst_idx], scores[worst_idx] = improved_tour, improved_value
                continue
            child, score = self._ga_step(population, scores)
            # Elitist survivor selection; stable ties plus canonical uniqueness.
            combined = list(zip(population + [child], scores + [score]))
            combined.sort(key=lambda x: x[1])
            survivors: list[tuple[tuple[int, ...], int]] = []
            unique: set[tuple[int, ...]] = set()
            for candidate, candidate_score in combined:
                key = canonical(candidate)
                if key not in unique:
                    survivors.append((candidate, candidate_score))
                    unique.add(key)
                if len(survivors) >= self.population:
                    break
            # For <population distinct tours preserve duplicates already scored.
            if len(survivors) < self.population:
                for entry in combined:
                    if len(survivors) >= self.population:
                        break
                    survivors.append(entry)
            population = [p for p, _ in survivors]
            scores = [f for _, f in survivors]
        return self._result(algorithm, switch)

    def _result(self, name: str, switch: int | None) -> Result:
        return Result(name, self.seed, int(self.best), self.tour,
                      self.evals, self.history, switch,
                      self.local_search_evaluations)


def main() -> None:
    p = argparse.ArgumentParser(description="Paper-inspired ACA/GA/ACAG TSP solver")
    p.add_argument("instance", type=Path, help="TSPLIB EUC_2D .tsp file")
    p.add_argument("--algorithm", choices=("aca", "ga", "acag", "aca_2opt", "aca_polish"), default="acag")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--budget", type=int, default=600)
    p.add_argument("--population", type=int, default=20)
    p.add_argument("--ant-max", type=int, default=8)
    p.add_argument("--switch-policy", choices=("stagnation", "fixed25",
                   "fixed50", "fixed75", "never"), default="stagnation")
    p.add_argument("--transfer-policy", choices=("elite", "random"), default="elite")
    p.add_argument("--mutation-policy", choices=("adjacent", "2opt"), default="adjacent")
    p.add_argument("--two-opt-trials", type=int, default=8)
    p.add_argument("--elite-polish-rate", type=float, default=0.)
    p.add_argument("--out", type=Path, help="Optional JSON output file")
    args = p.parse_args()
    tsp = TSP.from_tsplib(args.instance)
    result = Solver(tsp, seed=args.seed, budget=args.budget,
                    population=args.population, ant_max=args.ant_max,
                    switch_policy=args.switch_policy,
                    transfer_policy=args.transfer_policy,
                    mutation_policy=args.mutation_policy,
                    two_opt_trials=args.two_opt_trials,
                    elite_polish_rate=args.elite_polish_rate).run(args.algorithm)
    data = json.dumps(dict(instance=tsp.name, **result.as_dict()), indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data + "\n", encoding="utf-8")
    print(data)


if __name__ == "__main__":
    main()
