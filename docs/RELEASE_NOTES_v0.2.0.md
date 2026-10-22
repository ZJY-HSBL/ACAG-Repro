# ACAG-Repro v0.2.0 — Counted-budget switch-timing ablations

This release corrects a **substantive evaluation-accounting flaw** in the earlier exploratory v0.1.0 GA stage: every internal adjacent-swap candidate objective evaluation now consumes an evaluation budget unit. The old data are retained for historical traceability and are not directly comparable.

## New scientific evidence

- **420 fresh optimization runs:** 2 TSPLIB instances (`eil51`, `berlin52`) × 30 new paired seed IDs (`100–129`) × 7 algorithm settings.
- **Identical allocation:** 1,000 objective calls per run, including GA initialization, genetic offspring, and mutation trials.
- **Switch-policy ablations:** pure ACA, pure GA, stagnation-triggered ACAG, fixed 25%/50%/75% switches, and a 50%-switch with randomized instead of ACA-archive population transfer.
- **Result:** ACA retained the lowest mean tour length in both datasets (eil51 **451.37**, berlin52 **7,857.17**). ACAG with a 75%-budget switch came closest (eil51 **455.03**, berlin52 **7,892.90**). This is negative evidence under this implementation; no new superiority claim is made.
- Archive transfer was beneficial relative to random transfer at the same fixed 50% switch; stronger GA search is an open research issue.

## Reproducibility, visuals and CI

- `results/ablation_v0.2.0.csv`: 420 seed-level records, switch times, local-search evaluation counts.
- `results/convergence_v0.2.0.csv`: mean incumbent trajectories at regular charged-evaluation checkpoints.
- `results/summary_v0.2.0.json`: descriptive statistics, paired bootstrap 95% intervals, two-sided paired sign-flip Monte Carlo tests and Holm correction across 12 comparisons.
- Six new **data-derived SVG charts** under `docs/figures/v0.2.0/`: zoomed gaps, paired effects, and convergence for both problems.
- New accounting/switch tests in `tests/test_ablation.py` in addition to historical regression tests.
- The reproducibility workflow reruns the experiments, verifies unchanged evidence, then publishes this release (once).

**Research status:** still an exploratory paper-inspired reproduction, not a strict replication of the original article. New operators and external TSPLIB holdouts belong to later releases.

The legacy `tools/benchmark.py` command has been removed from `main` because rerunning it with v0.2's budget accounting would overwrite the archived v0.1 results with scientifically incomparable data. The v0.1.0 tag preserves the original generator.
