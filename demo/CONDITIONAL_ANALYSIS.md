# Conditional analysis: does aggregation matter more when the judges disagree?

Written 26 Aug 2026. Code: `conditional_analysis.py`. All numbers below
are written to `conditional_analysis.json` by that script; nothing here
is computed by hand.

## The question

The supervisor's framing: *does aggregation matter more when the ethical
judges disagree strongly?* The dissertation's headline says the four
rules pick different actions on 11.2% of dilemmas. This analysis asks
whether those dilemmas are randomly scattered, or concentrated exactly
where the three moral frameworks genuinely conflict. If the latter, the
headline strengthens from "rules disagree sometimes" to "rules disagree
precisely where moral uncertainty is real, which is when an aggregation
rule is supposed to earn its keep."

## Step 1: measure judge disagreement, per dilemma

Two independent measures, computed from the 16 responses of each
dilemma. Two are used because "the judges disagree" can mean two
different things, and a result that holds under both is robust.

### Measure A: ranking conflict (`D_rank`)

Do the judges *order* the sixteen responses differently? For each pair
of judges $(j, k)$ among (utilitarian, deontological, ubuntu), compute
Kendall's $\tau_b$ between their sixteen scores:

$$
\tau_b(j,k) = \frac{C - D}{\sqrt{(C + D + T_j)(C + D + T_k)}}
$$

where $C$ and $D$ count concordant and discordant response pairs and
$T_j, T_k$ count pairs tied under one judge only. $\tau_b = 1$ means
identical orderings, $0$ unrelated, $-1$ reversed. Kendall's tau is
invariant under monotone transforms, so raw 0-10 scores and z-scores
give identical values.

The dilemma's ranking disagreement is

$$
D_{\text{rank}} = 1 - \tfrac{1}{3}\left[\tau_b(u,d) + \tau_b(u,b) + \tau_b(d,b)\right]
$$

which is $0$ when all three judges rank identically, $1$ when their
orderings are unrelated, and up to $2$ when they are reversed.
Observed range in the corpus: $0.11$ to $1.34$.

Edge case: if a judge gives all sixteen responses the same score it has
no ordering, and any pair involving it is skipped; $D_{\text{rank}}$
averages the remaining pairs. Nine dilemmas had no comparable pair at
all and are excluded from the `D_rank` analyses (their slugs are listed in
the JSON). They are retained in the `D_spread` analyses.

### Measure B: level conflict (`D_spread`)

Do the judges assign *different values* to the same response, whatever
the ordering? For response $i$ with z-scores
$z_i^{(u)}, z_i^{(d)}, z_i^{(b)}$, the per-response spread is the
population standard deviation

$$
s_i = \sqrt{\tfrac{1}{3}\sum_{j} \left(z_i^{(j)} - \bar{z}_i\right)^2}
$$

and the dilemma's level disagreement is the mean over its sixteen
responses:

$$
D_{\text{spread}} = \tfrac{1}{16}\sum_{i=1}^{16} s_i .
$$

z-scores rather than raw scores are used so that one judge's leniency
does not masquerade as disagreement. Observed range: $0.08$ to
$1.32$.

The two measures capture genuinely different things: their Spearman
correlation across the 500 dilemmas is only $0.40$.

## Step 2: measure rule divergence, per dilemma

Both outcomes are the paper's own definitions, read directly from the
pipeline's records (`aggregation_results/*.json`), each computed for all
four rules and again for the three uncertainty rules (EC, Maximin,
Nash) alone:

- **Response-level divergence**: no single response lies in every
  rule's winner set (the bottom two rows of Table tab:two-levels;
  161/500 for all four rules).
- **Action-level divergence**: no recommendation label lies in every
  rule's label set (the bottom row; 56/500 for all four rules).

## Step 3: association

Three complementary statistics per (measure, outcome) pair:

1. **Quartile table.** Sort dilemmas by the disagreement measure, split
   into four equal-count bins, report the divergence rate in each.
2. **Mann-Whitney U** (one-sided): is the disagreement measure higher on
   divergent dilemmas than agreeing ones? Reported with the
   rank-biserial effect size $r = 2U/(n_1 n_0) - 1$.
3. **Spearman correlation** between the disagreement measure and the
   binary outcome.

## Results

### Ranking conflict (`D_rank`), all four rules

| Quartile | `D_rank` range | Action divergence | Response divergence |
|---|---|---|---|
| Q1 (agree most) | 0.11 - 0.56 | 6% | 24% |
| Q2 | 0.57 - 0.79 | 7% | 25% |
| Q3 | 0.80 - 0.97 | 7% | 29% |
| Q4 (disagree most) | 0.97 - 1.34 | **27%** | **53%** |

Action-level divergence is flat near 6-7% across the first three
quartiles and quadruples in the fourth. **33 of the 56 action-divergent
dilemmas (59%) sit in the top quartile.** Mean $D_{\text{rank}}$ is
0.96 on divergent dilemmas versus 0.74 on agreeing ones
(Mann-Whitney $p = 7.8 \times 10^{-9}$, rank-biserial 0.46).
Response-level shows the same pattern (24% to 53%,
$p = 8.0 \times 10^{-9}$).

Note what the Q4 boundary means. $D_{\text{rank}} \geq 0.97$ is mean
pairwise $\tau_b \leq 0.03$, i.e. the three judges' orderings are
essentially uncorrelated or opposed. The rules stop agreeing almost
exactly where the frameworks stop sharing an ordering.

### Level conflict (`D_spread`), all four rules

| Quartile | `D_spread` range | Action divergence | Response divergence |
|---|---|---|---|
| Q1 | 0.08 - 0.33 | 2% | 19% |
| Q2 | 0.33 - 0.54 | 8% | 33% |
| Q3 | 0.54 - 0.77 | 16% | 36% |
| Q4 | 0.77 - 1.32 | **19%** | **41%** |

Under the level measure the rise is monotone rather than
threshold-shaped, from 2% to 19% action divergence
($p = 6.4 \times 10^{-8}$, rank-biserial 0.43). A dose-response
pattern under one measure and a threshold pattern under the other, with
the two measures only moderately correlated, is stronger evidence than
either alone.

### The three uncertainty rules alone (EC, Maximin, Nash)

| Measure | Q1 | Q2 | Q3 | Q4 | MW p |
|---|---|---|---|---|---|
| `D_rank`, action | 3% | 4% | 4% | 9% | 0.005 |
| `D_rank`, response | 20% | 16% | 18% | 34% | 0.0003 |
| `D_spread`, action | 2% | 3% | 8% | 7% | 0.001 |
| `D_spread`, response | 16% | 22% | 21% | 26% | 0.014 |

The same gradient holds among the uncertainty rules alone, at lower
absolute levels, consistent with the paper's finding that most
action-level disagreement involves the utilitarian baseline. Even
between rules built to handle moral uncertainty, disagreement roughly
triples from the calmest to the most contested quartile.

## Reading

The answer to the supervisor's question is yes, and strongly. Rule
divergence is not noise scattered over the corpus. It concentrates where
the frameworks genuinely conflict, under either notion of conflict, at
every level of divergence, with and without the baseline. On the
quarter of dilemmas where the judges' orderings essentially decouple,
the choice of aggregation rule changes the recommended action more than
one time in four, versus about one in fifteen elsewhere.

This is the right shape for the dissertation's argument. If divergence
had been flat in judge disagreement, the 11.2% would look like an
artefact of scoring noise. Instead the machinery behaves as the theory
says it should: when the theories agree there is little for an
aggregation rule to do, and when they conflict the rule's identity
starts to decide the outcome.

## Limitations

- Correlation, not causation. High-disagreement dilemmas may differ in
  other ways (e.g. more heterogeneous candidate pools) that also make
  divergence easier.
- Ties interact with `D_rank`. A judge who ties heavily contributes
  weak tau values; tau-b corrects for ties, but nine all-tied dilemmas
  drop out of the `D_rank` analyses entirely.
- Action-level outcomes inherit the unvalidated recommendation labels;
  the response-level results do not, and they show the same pattern,
  which limits how much the label caveat can bite.
- Quartile boundaries are conventions. The Mann-Whitney and Spearman
  statistics do not depend on them and agree with the binned view.

## Files

- `conditional_analysis.py` computes everything.
- `conditional_analysis.json` holds every number in this document plus
  the full quartile tables for all eight (measure, outcome) pairs.
