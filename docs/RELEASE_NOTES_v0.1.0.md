# ACAG-Repro v0.1.0

First experimental, reproducible version of a paper-inspired ACAG TSP hybrid.

- Implements TSPLIB EUC_2D parser, standard ACA baseline, permutation GA and a stagnation-triggered ACA→GA hybrid.
- Adds OX crossover, improving adjacent-swap mutation, candidate-list transition logic, symmetric bounded local pheromone and iteration-best global reinforcement.
- Provides 10 paired seeds × 3 algorithms × 2 TSPLIB instances at equal budgets of 600 evaluated tours per run.
- Includes raw CSV, JSON summaries, SVG convergence and route charts, plus automated tests.
- Fully documents ambiguities and deliberate engineering deviations from the article.

**Observed pilot means (lower is better):** eil51 ACA 458.9 / GA 995.6 / ACAG 455.5; berlin52 ACA 7916.1 / GA 17315.4 / ACAG 8028.8. These results **do not establish** superiority of ACAG over ACA.

This is an initial research release, not a validated reproduction of the original paper's claimed effect size.
