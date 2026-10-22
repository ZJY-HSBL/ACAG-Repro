# ACAG-Repro v0.3.0 — Counted 2-opt and elite-feedback ablations

Research-oriented development release; **no claim of confirmed superiority**.

## New implementation

- Adds charged stochastic 2-opt and optional elite-feedback to the GA stage while retaining paper-inspired OX + adjacent-swap by default.
- Adds ACA+2opt and ACA75-polish as essential non-GA controls. 2-opt and bidirectional elite feedback are **engineering/research extensions**, not claimed original paper operators.
- Audits *every* full-tour evaluation, including rejected local-search proposals; retains deterministic seed-level history.

## Exploratory experiment

- 12 fresh paired seeds (200–211), two TSPLIB benchmarks, eleven treatments, **264 runs**, each with 1,000 complete-tour objective calls.
- `eil51`: ACA **448.33**, ACA75-polish **445.92**, ACAG75-2opt **447.50** mean tour length.
- `berlin52`: ACA **7,890.75**, ACA75-polish **7,882.17**, ACAG75-2opt **7,856.00**.
- On `berlin52`, ACAG75-2opt vs ACA mean paired delta **−34.75**, unadjusted 95% bootstrap **[−82.17, +0.42]**; not statistically confirmed and many candidates were screened.
- GA-2opt improves the weak GA-adj baseline, but fails to overtake ACA; applying 2-opt on *each ant* reduces performance under the same cost budget.
- No performance generalization is claimed: both instances were involved in earlier development. Multiple-comparison Holm corrections in machine-readable summary.

## Evidence

- `results/ablation_v0.3.0.csv` — all 264 outcomes.
- `results/convergence_v0.3.0.csv` — mean incumbent by charged evaluation.
- `results/summary_v0.3.0.json` — paired differences, percentile bootstrap, randomization p and Holm corrections.
- `docs/figures/v0.3.0/` — ten generated SVG charts including zoomed gap, paired effects vs two baselines and convergence.
- 40 automated tests, CI replaying both v0.2.0 and v0.3.0 evidence, release created by CI only after checks.

## Next gate

Predefine one or two candidate mechanisms and run a genuinely out-of-development-instance, larger-seed confirmatory experiment with equal objective budgets, stronger reference solvers and observed CPU time. **This release is an ablation screening, not a paper-level validation.**
