# Combined Assignment — N-1 Secure Capacity on the Svedala Grid

> **Course pair:** N-1 Security Assessment + Cross-Corridor Capacity Analysis
> **Effort:** ~6–8 hours after working through both notebook series
> **Deliverable:** completed `assignment_starter.ipynb` + a short written discussion

---

## Scenario

You are a junior planning engineer at the Swedish TSO. The market operator has
submitted the proposed day-ahead dispatch for tomorrow's morning peak hour.
Two numbers are needed for the 09:00 capacity briefing:

1. **Total Transfer Capacity (TTC)** for the **`ZON_NORR` → `ZON_MITT`**
   corridor — the largest transfer the grid supports against the proposed
   dispatch as base case.
2. **N-1 Secure TTC** — the largest such transfer that is *also* secure under
   any single line or transformer outage. This is what gets published as
   **NTC** (TRM = 0 for this exercise).

You also need to identify the **binding contingency** at the N-1 limit and
propose a corrective action.

---

## Personalised snapshot — what makes your problem unique

Every student in the class receives **a different snapshot** of the Svedala
grid. The grid topology is identical (52 buses, 52 lines, 44 transformers, the
same 4 zones), but the dispatch and load are perturbed per student.

Three scenario families are used, distributed roughly evenly across the class:

| Scenario              | Hydro     | Thermal   | Loads     | Character                                |
|-----------------------|-----------|-----------|-----------|------------------------------------------|
| `wet_hydro_mild_winter` | × 1.00–1.05 | × 0.78–0.88 | × 1.00       | Heavy NORR exports, NORR→MITT stressed   |
| `cold_dry_winter`       | × 0.80–0.95 | × 1.00–1.10 | × 1.05–1.12  | High demand, more thermal, possibly tight |
| `dry_summer_low_load`   | × 0.70–0.90 | × 0.85–1.00 | × 0.85–0.95  | Both sources reduced, low load           |

Your **TTC numbers, your binding contingency, and your written discussion**
will therefore differ from your peers'. Two students with the same scenario
family will still get different numbers because the random factors within the
range are seeded by their respective student IDs.

> ⚠️ **Academic integrity.** Comparing numbers with classmates will produce
> *wrong* answers, not just suspicious ones. The teaching team has the answer
> key for every snapshot. Compare *methods* with classmates, never values.

---

## Setting

- **Grid:** Svedala (simplified) from `KTH-EPE/CIM_exportimport`. Topology and
  ratings are identical for everyone.
- **Zones:** `ZON_NORR` (source), `ZON_MITT` (sink).
- **Operating limits:** voltage band [0.92, 1.08] p.u., line and transformer
  loading ≤ 100 %. *(The simplified Svedala model lacks the shunt reactive
  compensation present in the real Nordic grid. The strict NTC band [0.95, 1.05]
  cannot be maintained under all perturbed scenarios; [0.92, 1.08] is the
  emergency operating band used throughout this assignment and is consistent with
  how the student snapshots were generated.)*
- **GSK:** Pmax-proportional, in both zones (`tools.gsk_pmax`).
- **Slack:** `HÄLLAN_G1` in `ZON_EXTERN` (no `ext_grid` in this model).

---

## Tasks

| # | Task                                | What you produce                                | Difficulty |
|---|-------------------------------------|-------------------------------------------------|------------|
| 0 | Setup — load your personalised snapshot | `STUDENT_ID` set, snapshot loaded               | (no TODO)  |
| 1 | Base case verification              | Pass / fail decision on the dispatch            | ★          |
| 2 | Pre-N-1 TTC                         | A scalar TTC value + the limiting element       | ★★         |
| 3 | N-1 verification of base case       | List of critical contingencies                  | ★★         |
| 4 | **N-1 secure capacity sweep**       | A function `n1_secure_sweep()`                  | ★★★★       |
| 5 | **Bisection on N-1 secure TTC**     | A function `bisect_n1_ttc()`                    | ★★★        |
| 6 | Capacity report                     | `report/` folder (JSON, CSV, Markdown, map)     | ★★         |
| 7 | Discussion                          | A markdown cell answering five questions        | ★★         |

### Task 4 — what makes it the core deliverable

The pre-N-1 sweep asks: *for which transfers does the base case remain feasible?*
The N-1 secure sweep asks: *for which transfers does the base case **and every
single contingency** remain feasible?* At every step:

1. Apply the dispatch shift on a fresh deep-copy of the base net.
2. Run the *base* power flow and confirm feasibility — if not, stop here.
3. For every credible contingency (in-service line/transformer): deep-copy the
   post-shift net, trip the element, run PF, check feasibility.
4. The transfer step is **N-1 secure** iff base is feasible *and* every
   contingency is feasible.

For Svedala this is *N_steps × ~95 contingencies* power flows. With a 50 MW
coarse step that's ~1500 PFs — about a minute.

### Task 5 — bisection

Once you have the coarse N-1 secure TTC, bisect to ±1 MW. Each midpoint probe
runs a full N-1 sweep — re-use Task 4's inner check, don't re-implement it.

---

## Deliverables

A zip containing:

1. The completed `assignment_starter.ipynb` (renamed
   `assignment_<your_name>_<student_id>.ipynb`), all cells executed.
2. The auto-generated `report/` folder.
3. *No need* to include `tools.py`, `data/`, or your snapshot file — the teaching
   team has them.

---

## Grading rubric (suggested)

| Component                                    | Weight | What is assessed |
|----------------------------------------------|-------:|------------------|
| Task 4 — N-1 secure sweep correctness        |  30 %  | Returns the right value (cross-checked against the answer key); restores state cleanly; handles non-convergence |
| Task 5 — Bisection correctness               |  15 %  | Converges; correct bracket; resolution achieved |
| Tasks 1–3 — Building blocks                  |  15 %  | Correct base case verification, TTC, contingency list |
| Task 6 — Report                              |  10 %  | Files exist; capacity table is right; map shows binding element |
| Task 7 — Discussion                          |  20 %  | Five questions answered with insight, not just numbers |
| Code quality                                 |  10 %  | Reusable functions, comments, no copy-paste from tutorials |

### Optional bonus tasks (+10 %)

- **B1.** Replace the brute-force inner loop with `multiprocessing` /
  `concurrent.futures`. Report the speed-up.
- **B2.** Propose and *quantify* a corrective re-dispatch that recovers, say,
  half the gap between TTC and N-1 secure TTC.
- **B3.** Re-run with `ZON_MITT` → `ZON_SYDVÄST` (the SE3-SE4 boundary) and
  compare. Which corridor binds the system harder *for your scenario*?

---

## Hints

- Read `tools.py` first. Everything you need from the tutorial notebooks is
  there *except* the contingency loop and the capacity sweep.
- For Task 4, a clean signature is:
  ```python
  def n1_secure_sweep(base_net, gsk_a, gsk_b, line_dir, trafo_dir,
                      contingencies, step_mw=50.0, max_delta_mw=2500.0,
                      v_min=0.95, v_max=1.05,
                      line_limit=100.0, trafo_limit=100.0):
      ...
      return pd.DataFrame(rows)
  ```
- Use `copy.deepcopy(net)` liberally. Mutating the base net silently corrupts
  later iterations — the most common bug in this assignment.

Good luck.

---

## TEACHER QUICKSTART (do not distribute this section to students)

The two scripts you'll use, in order:

### Step 1 — generate the class snapshots

```bash
# from the n1_capacity_assignment/ folder
python3 generate_student_snapshots.py --count 50 --out student_snapshots/
```

Or with a roster:

```bash
python3 generate_student_snapshots.py --roster roster.csv --out student_snapshots/
```

`roster.csv` must have a `student_id` column. Output:

```
student_snapshots/
    svedala_student_01.json
    svedala_student_02.json
    ...
    MANIFEST.csv         ← scenario assignments + a few sanity numbers
```

The script verifies each snapshot converges. Snapshots that fail are retried
with a 50 % shrunk perturbation up to 4 times. If a snapshot still fails, an
error row is logged in the manifest — investigate before distributing.

**Verification step (recommended).** Open one snapshot in a notebook and
confirm:
```python
import pandapower as pp
net = pp.from_json("student_snapshots/svedala_student_01.json")
pp.runpp(net)
print(net.res_line.loading_percent.max())   # should be < 100 %
```

### Step 2 — generate the answer key

```bash
python3 generate_answer_key.py --snapshots student_snapshots/ --out answer_key.csv
```

This runs the full pre-N-1 + N-1 secure analysis on every snapshot. Roughly
**1 minute per student** serial; use `--workers 4` to parallelise. Output:

```csv
student_id,scenario,base_feasible,n_base_violations,base_flow_norr_mitt_mw,
TTC_pre_n1_delta_mw,TTC_pre_n1_flow_mw,TTC_pre_n1_limiting,TTC_pre_n1_limiting_name,
n_base_critical_contingencies,
TTC_n1_delta_mw,TTC_n1_flow_mw,TTC_n1_limiting,TTC_n1_limiting_name,
runtime_seconds
```

Tolerance for grading: ±10 MW on `TTC_n1_flow_mw` is comfortable (their bisect
tolerance is ±1 MW, but they may use a different GSK or step size).

### Step 3 — distribute

Hand each student their `svedala_student_<id>.json`. The student places it in
`student_snapshots/` next to the assignment notebook and sets `STUDENT_ID`.
Everything else is identical for everyone.

### What if a snapshot turns out to be infeasible at the base case?

The current scenario ranges are tuned to give converging, *interesting*
snapshots, but the simplified Svedala model has no OPF or tap optimisation —
some perturbations may produce small base-case violations (a 102 % loaded
line, a 0.948 p.u. voltage). That's a **feature** for grading: the assignment
explicitly tells students to investigate base-case violations in Task 7,
distinguishing them from violations caused by transfer increases. If you want
all students to start from a clean base, narrow the scenario ranges in
`generate_student_snapshots.py` (variable `SCENARIOS`).
