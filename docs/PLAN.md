# FDA regulatory co-pilot plan

This plan turns `docs/BRIEF.md` into 16 small PRs. The first users are the author and the employers who read the repo. Every regulatory finding the product shows must cite stored regulation text that a verifier has checked. Evals come before the agents, so each later PR is measured against a recorded baseline.

PR order is P01 through P16. P07 and P08 can be built while P03 to P06 are in progress.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`, read from the installed pstack plugin. The work is sequenced and the operator reviews before landing, so owners stop at stack-ready. The operator lands every PR.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

The operator scaled live verification down on 2026-10-16 because `control-ui` is not installed. Each PR's live block runs the eval suite plus one scripted end-to-end check, not ten swarm lanes. `check-plan.mjs` still expects ten lanes, so it reports one lane problem per PR. Those problems are expected.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] Read these at program start. Re-read them at every tick.
  - [ ] `git show origin/main:docs/PLAN.md`
  - [ ] `git show origin/main:docs/BRIEF.md`
  - [ ] The installed `poteto-mode/playbooks/autopilot-stack.md` and `poteto-mode/playbooks/autopilot-full.md`.
  - [ ] The installed `poteto-mode/playbooks/opening-a-pr.md`.
  - [ ] The installed `principle-prove-it-works/SKILL.md` and `principle-sequence-verifiable-units/SKILL.md`.
- [ ] On the operator's go, arm the audit tick as `/loop 1h` with the tick prompt below. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk. Audit the operation against it and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a short status message to the operator in chat only when the audit found a tracked change that no earlier status message reported, such as a PR opened, a code-ready head, a round launched or closed, a verdict, a merge, a stuck agent and the action taken, a blocker added or cleared, or a decision only the operator can make. Name every such change and nothing else. Do not repeat a table, the merged list, or an unchanged blocker. If the audit found none, end the turn with no reply text. Either way, log this tick's row in your decision trail. The row names the items reported, or none."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR as a `poteto-agent` subagent with `isolation` set to `worktree`. Give it the PR's GitHub issue body as its brief.
- [ ] Follow this dependency graph. Base dependent work on the parent branch, because the execution playbook stacks.
  - [ ] P01 is first and branches from `main`.
  - [ ] P02 after P01.
  - [ ] P03 after P02. P04 after P03. P05 after P04. P06 after P05.
  - [ ] P07 after P02. P08 after P02. Both can run in parallel with P03 to P06.
  - [ ] P09 after P06, P07, and P08.
  - [ ] P10 after P09. P11 after P10. P12 after P11.
  - [ ] P13 after P12. P14 after P12. P15 after P13.
  - [ ] P16 after P14 and P15.
- [ ] Hold the file boundaries. Each PR touches only the paths in its **Files** block and its issue's SCOPE field.
- [ ] Hold the review gate. P12, P13, P14, and P15 change an interaction. They wait for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Use `gh` for every PR operation. Never require `gt`.
- [ ] Open the PR ready, never draft, per **Opening a PR**, with `gh pr create --base <parent-branch>`. A stack child targets its parent branch.
- [ ] Run `uv run ruff check`, `uv run mypy src`, and `uv run pytest` once before the PR-facing push. Push with hooks on.
- [ ] Run `/simplify` before each commit, in place of `/deslop`, which is not installed. Run `/no-comments` before review.
- [ ] Triage every review comment on its merits. Fix it, or dismiss it with a concrete reason.
- [ ] Rebase onto current trunk before the code-ready report. Rebase again only at merge prep or on a conflict with trunk.
- [ ] Link the PR to its issue with `Closes #<issue>` in the PR body.

### Verdict and merge, for every PR

- [ ] A fresh verifier subagent on the `swarm workers` model checks out the code-ready head SHA. It runs the PR's unit, live, and perf boxes and returns each command's output. A rebase or a minor fix gets a single verifier run at the new head.
- [ ] Run `/code-review` at the head SHA. Send its confirmed findings back to the owner.
- [ ] Clean only when every unit, live, and perf box passes with its saved evidence. A new head gets a fresh verdict, unless its patch-id is unchanged.
- [ ] Append each clean PR to the stack in dependency order with `gh pr edit <pr> --base <parent-branch>`. The operator lands the stack bottom-up.

### Boot recipe, for every live check

Each live check runs on the operator's machine at the PR head.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Copy `.env.example` to `.env` and fill `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, and `LANGSMITH_API_KEY` from the operator's keychain.
- [ ] Run `docker compose up -d --wait` and `uv sync`. Wait for `GET /health` to return `200`.
- [ ] Run the PR's eval and end-to-end commands. Use only the API, the CLI, and the scripts the PR names.
- [ ] Save every log, report, and screenshot under `/tmp/verify-<pr-id>/` and return the paths with the report.

## Scaffold the repo, the local stack, and CI (P01)

**Depends on.** None.

**Files.**

- [ ] Create `pyproject.toml` with `uv`, `ruff`, `mypy`, `pytest`, `fastapi`, `langgraph`, `anthropic`, and `voyageai`.
- [ ] Create `src/fda_copilot/api/app.py`.
- [ ] Create `docker-compose.yml` with a `pgvector/pgvector` Postgres service and the API service.
- [ ] Create `.env.example`, `.github/workflows/ci.yml`, and `scripts/e2e/p01.sh`.

**Build.**

- [ ] Add a FastAPI app with `GET /health` that returns `{"status": "ok", "db": "ok"}` after a `SELECT 1` against Postgres.
- [ ] Add a CI workflow that runs lint, typecheck, and tests on every pull request.

**You see.**

- [ ] `curl localhost:8000/health` prints `{"status":"ok","db":"ok"}`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/api/test_health.py` asserts the response body equals `{"status": "ok", "db": "ok"}`. Run `uv run pytest tests/api`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. No eval exists yet. Record that fact in the PR body. Save `eval-none.txt`. Pass when the file states that P05 adds the first eval.
- [ ] End to end. Run `scripts/e2e/p01.sh`, which brings the stack up from a clean `docker compose down -v` and calls `/health`. Save `p01-e2e.log`. Pass when the log ends with `HEALTH OK`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Seconds from `docker compose up -d --wait` to a `200` from `/health`, and CI wall time.
- [ ] Probe. Run `scripts/e2e/p01.sh` three times and read the CI run duration with `gh run view`.
- [ ] Baseline. Trunk has no stack. Record the three head timings.
- [ ] Rule. Fail if the median start time exceeds 60 seconds or CI takes more than 5 minutes.

**Review gate.** None. P01 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P01 to the stack and the operator lands it.

## Define the core regulatory types and the finding state machine (P02)

**Depends on.** P01.

**Files.**

- [ ] Create `src/fda_copilot/domain/models.py`.
- [ ] Create `src/fda_copilot/domain/finding_status.py`.
- [ ] Create `tests/domain/test_finding_status.py`.

**Build.**

- [ ] Add Pydantic models `RegSection`, `DocSection`, `Citation`, and `Finding` with the fields in `docs/BRIEF.md`. `Finding.citations` rejects an empty list.
- [ ] Add `Domain` as an enum of `IND`, `IDE`, `GLP`, and `GCP`.
- [ ] Add `FindingStatus` as an enum and a single `transition(status, event)` function backed by a transition table. Allowed moves are `proposed` to `verified` or `discarded`, and `verified` to `accepted` or `rejected`. Every other move raises `IllegalTransition`.

**You see.**

- [ ] `uv run python -c "from fda_copilot.domain.finding_status import *; print(transition(FindingStatus.proposed, 'verify'))"` prints `FindingStatus.verified`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/domain/test_finding_status.py` covers every allowed move and asserts `IllegalTransition` for `proposed` to `accepted`. Run `uv run pytest tests/domain`.
- [ ] `tests/domain/test_models.py` asserts that a `Finding` with `citations=[]` fails validation.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. No eval exists yet. Save `eval-none.txt`. Pass when the file states that P05 adds the first eval.
- [ ] End to end. Run `scripts/e2e/p02.py`, which builds one `Finding` and walks it from `proposed` to `accepted`, then tries `accepted` to `proposed`. Save `p02-e2e.log`. Pass when the log shows three allowed moves followed by `IllegalTransition`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `uv run pytest tests/domain`.
- [ ] Probe. Run it three times at head.
- [ ] Baseline. Trunk has no domain tests. Record the head timings.
- [ ] Rule. Fail if the median exceeds 5 seconds.

**Review gate.** None. P02 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P02 to the stack and the operator lands it.

## Ingest 21 CFR Parts 50, 56, 58, 312, and 812 at the paragraph level (P03)

**Depends on.** P02.

**Files.**

- [ ] Create `src/fda_copilot/corpus/ecfr.py`.
- [ ] Create `src/fda_copilot/corpus/store.py` and `migrations/001_reg_sections.sql`.
- [ ] Create `tests/corpus/fixtures/part50_section25.xml`, `tests/corpus/fixtures/part312_section32.xml`, and `tests/corpus/test_ecfr.py`.

**Build.**

- [ ] Fetch each part from `https://www.ecfr.gov/api/versioner/v1/full/<date>/title-21.xml?part=<n>` with an `Accept-Encoding: gzip` header.
- [ ] Parse each `<P>` element into one `RegSection` whose citation joins the section number and the paragraph markers, for example `21 CFR 50.25(a)(1)`.
  - [ ] Track the marker stack, because a bare `(2)` belongs to whichever lettered paragraph came last. `312.32` has both `(c)(2)` and `(d)(2)`.
  - [ ] Split a combined lead marker such as `(c)(1)` into two levels.
- [ ] Add a fixture test that asserts `21 CFR 312.32(c)(2)` and `21 CFR 312.32(d)(2)` are distinct rows.
- [ ] Upsert rows keyed by `(citation, effective_date)`, so a second run writes nothing.
- [ ] Add the CLI command `fda-copilot ingest cfr`.

**You see.**

- [ ] `fda-copilot ingest cfr` prints a row count per part and `0 changed` on a second run.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/corpus/test_ecfr.py` parses the saved 50.25 fixture and asserts the citation `21 CFR 50.25(a)(1)` and the first 40 characters of its text. Run `uv run pytest tests/corpus`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. No eval exists yet. Save `eval-none.txt`. Pass when the file states that P05 adds the first eval.
- [ ] End to end. Run `scripts/e2e/p03.sh`, which ingests all five parts twice and queries `21 CFR 312.32(c)(1)`. Save `p03-e2e.log`. Pass when the second run reports `0 changed` and the query returns text that contains `IND safety report`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of a cold ingest of all five parts, and the row count per part.
- [ ] Probe. Run `time fda-copilot ingest cfr` on an empty database.
- [ ] Baseline. Trunk has no corpus. Record the head time and counts.
- [ ] Rule. Fail if the cold ingest exceeds 3 minutes or any part stores fewer than 20 rows.

**Review gate.** None. P03 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P03 to the stack and the operator lands it.

## Ingest ICH guidelines and the core FDA guidance documents (P04)

**Depends on.** P03.

**Files.**

- [ ] Create `src/fda_copilot/corpus/guidance.py` and `corpus/guidance_sources.yaml`.
- [ ] Create `tests/corpus/test_guidance.py`.

**Build.**

- [ ] List ICH E6(R3), ICH M3(R2), and at most eight FDA guidance PDFs in `guidance_sources.yaml`, each with its URL, title, and issue date.
- [ ] Chunk each PDF by its numbered headings into `RegSection` rows with `source` set to `ich` or `fda_guidance` and a citation such as `ICH E6(R3) 3.10.1`.
- [ ] Reuse the P03 upsert, so a second run writes nothing.

**You see.**

- [ ] `fda-copilot ingest guidance` prints a row count per document and `0 changed` on a second run.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/corpus/test_guidance.py` chunks a two-page fixture PDF and asserts the exact list of citations it produces. Run `uv run pytest tests/corpus`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. No eval exists yet. Save `eval-none.txt`. Pass when the file states that P05 adds the first eval.
- [ ] End to end. Run `scripts/e2e/p04.sh`, which ingests every listed document twice and prints five random citations with their first line. Save `p04-e2e.log`. Pass when the second run reports `0 changed` and each printed line matches the source PDF.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of a cold guidance ingest.
- [ ] Probe. Run `time fda-copilot ingest guidance` on a database that holds only the P03 rows.
- [ ] Baseline. Trunk has no guidance ingest. Record the head time.
- [ ] Rule. Fail if the cold ingest exceeds 5 minutes.

**Review gate.** None. P04 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P04 to the stack and the operator lands it.

## Build the retrieval eval set and a keyword-search baseline (P05)

**Depends on.** P04.

**Files.**

- [ ] Create `evals/retrieval/questions.jsonl` with at least 50 rows.
- [ ] Create `src/fda_copilot/retrieval/keyword.py` and `evals/retrieval/run.py`.
- [ ] Create `evals/baselines.json` and add an eval job to `.github/workflows/ci.yml`.

**Build.**

- [ ] Write each question with the citations that answer it and the domain it belongs to. Cover all four domains and Parts 50 and 56.
- [ ] Add a `Retriever` protocol and a Postgres full-text implementation of it.
- [ ] Add `evals/retrieval/run.py`, which prints recall at 5 overall and per domain and compares it with `evals/baselines.json`.
- [ ] Make CI fail when recall at 5 drops below the stored baseline.

**You see.**

- [ ] `uv run python evals/retrieval/run.py --retriever keyword` prints a table of recall at 5 per domain.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/evals/test_recall.py` scores three hand-built results and asserts recall at 5 equals `0.6667`. Run `uv run pytest tests/evals`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run `evals/retrieval/run.py --retriever keyword`. Save `retrieval-keyword.json`. Pass when the run completes, writes the baseline, and every question resolves to stored citations.
- [ ] End to end. Run `scripts/e2e/p05.sh`, which lowers the stored baseline by hand and confirms the CI check fails, then restores it. Save `p05-e2e.log`. Pass when the log shows one failing check and one passing check.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of a full retrieval eval run.
- [ ] Probe. Run `time uv run python evals/retrieval/run.py --retriever keyword` three times.
- [ ] Baseline. Trunk has no eval. Record the head timings and the recall at 5 value.
- [ ] Rule. Fail if the median run exceeds 60 seconds.

**Review gate.** None. P05 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P05 to the stack and the operator lands it.

## Add hybrid retrieval and pick the embedding model by eval (P06)

**Depends on.** P05.

**Files.**

- [ ] Create `src/fda_copilot/retrieval/hybrid.py` and `migrations/002_embeddings.sql`.
- [ ] Create `src/fda_copilot/corpus/embed.py`.
- [ ] Edit `evals/baselines.json`.

**Build.**

- [ ] Embed every `RegSection` with Voyage AI and store the vectors in a pgvector column. Skip rows whose text hash is unchanged.
- [ ] Implement `HybridRetriever`, which fuses keyword and vector results with reciprocal rank fusion and can filter by `Domain`.
- [ ] Run the retrieval eval with `voyage-4` and `voyage-law-2`. Keep the model with the higher recall at 5 and record both scores in the PR body.

**You see.**

- [ ] `evals/retrieval/run.py --retriever hybrid` prints a recall at 5 above the P05 baseline.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/retrieval/test_fusion.py` fuses two fixed ranked lists and asserts the exact fused order. Run `uv run pytest tests/retrieval`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run the retrieval eval for `keyword` and for `hybrid` with each candidate model. Save `retrieval-compare.json`. Pass when hybrid recall at 5 beats keyword recall at 5 overall and in every domain.
- [ ] End to end. Run `scripts/e2e/p06.sh`, which embeds the corpus twice and runs one query per domain. Save `p06-e2e.log`. Pass when the second embed run reports `0 embedded` and each query's top result has the expected domain.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Recall at 5, p95 query latency, and the one-time embedding cost in dollars.
- [ ] Probe. Run keyword and hybrid evals interleaved, three times each, and read the Voyage usage from the embed log.
- [ ] Baseline. Record the P05 keyword recall at 5 and latency first.
- [ ] Rule. Fail if hybrid recall at 5 is not higher than keyword recall at 5, or if p95 query latency exceeds 300 milliseconds.

**Review gate.** None. P06 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P06 to the stack and the operator lands it.

## Build the planted-violation eval set and its scorer (P07)

**Depends on.** P02.

**Files.**

- [ ] Create `evals/review/protocols/` with at least 12 synthetic protocols, three per domain.
- [ ] Create `evals/review/gold.jsonl`, with one row per planted violation.
- [ ] Create `evals/review/score.py` and `tests/evals/test_review_score.py`.

**Build.**

- [ ] Write each protocol as a `.docx` with two to five planted violations. Record each violation's section, domain, and correct citation in `gold.jsonl`.
- [ ] Mark one third of the protocols as held out in `gold.jsonl`. Held-out protocols are never used for prompt tuning.
- [ ] Score a list of `Finding` records against the gold set for recall, precision, citation accuracy, and exact-quote faithfulness.
- [ ] Add a `NullReviewer` that returns no findings, as the baseline.

**You see.**

- [ ] `uv run python evals/review/score.py --reviewer null` prints recall `0.00` and lists every planted violation as missed.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/evals/test_review_score.py` scores two hand-built findings against a three-row gold set and asserts recall `0.6667`, precision `1.0`, and citation accuracy `0.5`. Run `uv run pytest tests/evals`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run the scorer with the null reviewer on the full set. Save `review-null.json`. Pass when recall is `0.00` and the planted-violation count equals the row count of `gold.jsonl`.
- [ ] End to end. Run `scripts/e2e/p07.py`, which feeds the gold findings back in as if a reviewer found them. Save `p07-e2e.log`. Pass when recall, precision, and citation accuracy all equal `1.00`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of a full scorer run.
- [ ] Probe. Run `time uv run python evals/review/score.py --reviewer null` three times.
- [ ] Baseline. Trunk has no scorer. Record the head timings.
- [ ] Rule. Fail if the median exceeds 10 seconds.

**Review gate.** None. P07 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P07 to the stack and the operator lands it.

## Parse uploaded documents into sections with character spans (P08)

**Depends on.** P02.

**Files.**

- [ ] Create `src/fda_copilot/documents/parse.py`.
- [ ] Create `tests/documents/fixtures/` with one `.docx` and one `.pdf`.
- [ ] Create `tests/documents/test_parse.py`.

**Build.**

- [ ] Parse `.docx` headings and `.pdf` outline or font-size headings into `DocSection` records with a heading, text, and character span.
- [ ] Reject other file types with `UnsupportedDocument`.

**You see.**

- [ ] `fda-copilot parse <file>` prints one line per section with its heading and span.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/documents/test_parse.py` parses each fixture and asserts the exact list of headings and that each span slices back to its section text. Run `uv run pytest tests/documents`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Parse every P07 protocol. Save `parse-protocols.json`. Pass when every gold violation's section heading appears among the parsed sections.
- [ ] End to end. Run `scripts/e2e/p08.sh` on one real ClinicalTrials.gov protocol PDF. Save `p08-e2e.log`. Pass when the log lists at least 10 sections and the spans cover the document text with no overlap.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Parse time for a 30-page or longer protocol PDF.
- [ ] Probe. Run `time fda-copilot parse <file>` three times.
- [ ] Baseline. Trunk has no parser. Record the head timings.
- [ ] Rule. Fail if the median exceeds 5 seconds.

**Review gate.** None. P08 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P08 to the stack and the operator lands it.

## Review informed consent end to end with one specialist and the verifier (P09)

**Depends on.** P06, P07, and P08.

**Files.**

- [ ] Create `src/fda_copilot/agents/graph.py`, `src/fda_copilot/agents/specialist.py`, and `src/fda_copilot/agents/verifier.py`.
- [ ] Create `src/fda_copilot/agents/prompts/consent.md`.
- [ ] Create `tests/agents/test_verifier.py`.

**Build.**

- [ ] Build a LangGraph graph with parse, consent specialist, verifier, and an `interrupt()` node, in that order.
- [ ] The specialist runs on `claude-sonnet-5-5`, retrieves only Part 50 and Part 56 rows, and returns structured `Finding` records.
- [ ] The verifier runs on `claude-opus-5-5`. It first checks mechanically that each quote matches the stored `RegSection` text exactly, then asks the model whether the quote supports the finding. Failing findings move to `discarded`.
- [ ] Add the CLI command `fda-copilot review <file> --domain GCP`, which prints verified findings and stops at the interrupt.
- [ ] Send traces to LangSmith.

**You see.**

- [ ] Running the review on a consent protocol from P07 prints findings that each cite a `21 CFR 50.25` paragraph.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/agents/test_verifier.py` gives the verifier one finding with an exact quote and one with an altered quote, with the model call stubbed. It asserts `verified` and `discarded`. Run `uv run pytest tests/agents`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run `evals/review/score.py --reviewer graph --domain GCP` on the consent protocols. Save `review-consent.json`. Pass when recall is higher than the null baseline and faithfulness is `1.00`.
- [ ] End to end. Run `scripts/e2e/p09.sh` on one consent protocol. Save `p09-e2e.log` and the LangSmith trace URL. Pass when the graph stops at the interrupt and every printed finding has status `verified`.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Dollars and wall time per consent review, from `response.usage` and the trace.
- [ ] Probe. Review three consent protocols and sum the token usage per run.
- [ ] Baseline. Trunk has no reviewer. Record the head cost and time per protocol.
- [ ] Rule. Fail if any review costs more than $0.25 or takes more than 90 seconds.

**Review gate.** None. P09 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P09 to the stack and the operator lands it.

## Route sections to four parallel specialists (P10)

**Depends on.** P09.

**Files.**

- [ ] Create `src/fda_copilot/agents/router.py`.
- [ ] Create `src/fda_copilot/agents/prompts/ind.md`, `ide.md`, `glp.md`, and `gcp.md`.
- [ ] Edit `src/fda_copilot/agents/graph.py`.
- [ ] Create `tests/agents/test_router.py`.

**Build.**

- [ ] Add a router on `claude-haiku-5-5` that tags each `DocSection` with one or more domains.
- [ ] Fan tagged sections out to the four specialists with LangGraph's `Send` API, so they run in parallel.
- [ ] Register specialists in one table keyed by `Domain`, so adding a domain adds a row instead of a branch.

**You see.**

- [ ] `fda-copilot review <file>` on a mixed protocol prints findings from more than one domain.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/agents/test_router.py` runs the graph with stubbed models and asserts that one section tagged `IND` and `GCP` reaches exactly those two specialists. Run `uv run pytest tests/agents`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run `evals/review/score.py --reviewer graph` on the full development set and on the held-out set. Save `review-full.json`. Pass when held-out recall is at least `0.80`, held-out citation accuracy is at least `0.90`, and faithfulness is `1.00`.
- [ ] End to end. Run `scripts/e2e/p10.sh` on one real ClinicalTrials.gov protocol. Save `p10-e2e.log` and the trace URL. Pass when the trace shows the four specialists running in parallel and the graph stops at the interrupt.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Dollars and wall time per full protocol review.
- [ ] Probe. Review the same three protocols at P09 head with `--domain GCP` and at P10 head with all domains, interleaved.
- [ ] Baseline. Record the P09 single-domain cost and time first.
- [ ] Rule. Fail if a full review of a 30-page protocol costs more than $1 or takes more than 3 minutes.

**Review gate.** None. P10 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P10 to the stack and the operator lands it.

## Expose reviews and accept or reject decisions through the API (P11)

**Depends on.** P10.

**Files.**

- [ ] Create `src/fda_copilot/api/reviews.py`.
- [ ] Create `src/fda_copilot/documents/apply_fix.py`.
- [ ] Edit `src/fda_copilot/agents/graph.py` to use the LangGraph Postgres checkpointer.
- [ ] Create `tests/api/test_reviews.py`.

**Build.**

- [ ] Add `POST /reviews` to upload a document and start a review, and `GET /reviews/{id}/events` to stream findings as server-sent events.
- [ ] Add `POST /reviews/{id}/findings/{finding_id}` with `accept` or `reject`. It resumes the interrupted graph with that decision.
- [ ] Apply accepted fixes to a copy of the `.docx`. Serve it at `GET /reviews/{id}/document`.
- [ ] Store graph state in Postgres, so a review survives an API restart.

**You see.**

- [ ] A `curl` session uploads a protocol, streams findings, accepts one, and downloads a `.docx` that contains the fix.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/api/test_reviews.py` runs the full flow with stubbed models and asserts the accepted fix text appears in the returned document. Run `uv run pytest tests/api`.
- [ ] `tests/documents/test_apply_fix.py` applies one fix to a fixture and asserts the exact resulting paragraph.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Rerun the full review eval through the API instead of the CLI. Save `review-api.json`. Pass when every score matches `review-full.json` from P10 within `0.02`.
- [ ] End to end. Run `scripts/e2e/p11.sh`, which uploads a protocol, accepts one finding, restarts the API container, rejects another, and downloads the document. Save `p11-e2e.log` and `p11-output.docx`. Pass when both decisions are recorded after the restart and the document contains only the accepted fix.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Latency from a decision request to the graph's next event.
- [ ] Probe. Time 20 accept and reject calls with `scripts/e2e/p11.sh --timing`.
- [ ] Baseline. Trunk has no API for decisions. Record the head p50 and p95.
- [ ] Rule. Fail if p95 exceeds 500 milliseconds, not counting model time.

**Review gate.** None. P11 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P11 to the stack and the operator lands it.

## Build the document review UI with inline findings (P12)

**Depends on.** P11.

**Files.**

- [ ] Create `web/` as a Next.js app.
- [ ] Create `web/app/reviews/[id]/page.tsx` and `web/components/FindingCard.tsx`.
- [ ] Create `web/e2e/review.spec.ts` with Playwright.
- [ ] Edit `docker-compose.yml` to add the web service.

**Build.**

- [ ] Show the document with each finding highlighted at its span. A side panel lists findings with severity, the issue, the quoted citation, and the proposed fix.
- [ ] Add accept and reject buttons that call the P11 endpoint and update the card.
- [ ] Label every page as a drafting aid that needs review by a qualified person.

**You see.**

- [ ] Uploading a protocol at `localhost:3000` shows highlighted spans and finding cards as they stream in.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `web/components/FindingCard.test.tsx` renders a fixed finding and asserts the citation text and both buttons. Run `npm test --prefix web`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run the full review eval and confirm that this PR leaves the scores unchanged. Save `review-p12.json`. Pass when every score matches P11 within `0.02`.
- [ ] End to end. Run `npx playwright test web/e2e/review.spec.ts`, which uploads a protocol, accepts one finding, rejects one, and downloads the document. Save `p12-review.png` and the Playwright trace. Pass when the downloaded document contains only the accepted fix.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Seconds from upload to the first visible finding card.
- [ ] Probe. Measure it in the Playwright spec over three runs.
- [ ] Baseline. Trunk has no UI. Record the head timings.
- [ ] Rule. Fail if the median exceeds 30 seconds.

**Review gate.** The operator reviews before merge.

- [ ] Copy the Playwright screenshots into `docs/media/p12-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of a review with one accept and one reject. Save it as `docs/media/p12-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P12 to the stack and the operator lands it.

## Add the cited chat sidebar (P13)

**Depends on.** P12.

**Files.**

- [ ] Create `src/fda_copilot/agents/chat.py` and `src/fda_copilot/api/chat.py`.
- [ ] Create `web/components/ChatSidebar.tsx`.
- [ ] Create `evals/chat/run.py` and `web/e2e/chat.spec.ts`.

**Build.**

- [ ] Answer questions with hybrid retrieval and `claude-sonnet-5-5`. Every answer cites `RegSection` rows, and the P09 verifier's quote check runs on each citation.
- [ ] When the user has a review open, include the selected document section as context.
- [ ] Reuse the P05 questions as the chat eval and score citation accuracy and exact-quote faithfulness.

**You see.**

- [ ] Asking "When must a sponsor submit a 7-day IND safety report?" returns an answer that cites `21 CFR 312.32(c)(2)`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/agents/test_chat.py` runs chat with stubbed retrieval and a stubbed model and asserts that an answer citing an unstored citation is rejected. Run `uv run pytest tests/agents`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run `evals/chat/run.py`. Save `chat.json`. Pass when citation accuracy is at least `0.90` and faithfulness is `1.00`.
- [ ] End to end. Run `npx playwright test web/e2e/chat.spec.ts`, which asks the 7-day safety report question with a review open. Save `p13-chat.png`. Pass when the answer shows a `21 CFR 312.32(c)(2)` citation that links to its stored text.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Seconds to the first token, and dollars per answer.
- [ ] Probe. Run `evals/chat/run.py --timing` over all questions.
- [ ] Baseline. Trunk has no chat. Record the head p50 and the mean cost.
- [ ] Rule. Fail if p50 time to first token exceeds 5 seconds or mean cost exceeds $0.05.

**Review gate.** The operator reviews before merge.

- [ ] Copy the Playwright screenshots into `docs/media/p13-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of three chat questions. Save it as `docs/media/p13-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P13 to the stack and the operator lands it.

## Generate an IND submission checklist as a workflow job (P14)

**Depends on.** P12.

**Files.**

- [ ] Create `src/fda_copilot/workflows/ind_checklist.py` and `src/fda_copilot/api/workflows.py`.
- [ ] Create `web/app/workflows/ind/page.tsx`.
- [ ] Create `evals/workflows/ind_checklist_gold.json` and `web/e2e/ind.spec.ts`.

**Build.**

- [ ] Build a LangGraph workflow that reads the user's uploaded documents and checks them against the IND contents listed in 21 CFR 312.23(a). It marks each item present, missing, or unclear, and cites its source in both the regulation and the user's document.
- [ ] Pause with `interrupt()` before the final checklist so the user can correct items.
- [ ] Export the checklist as Markdown and `.docx`.

**You see.**

- [ ] Running the workflow on a P07 IND protocol shows a checklist with one row per 21 CFR 312.23(a) item.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/workflows/test_ind_checklist.py` runs the workflow with stubbed models and asserts the exact set of checklist item citations. Run `uv run pytest tests/workflows`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Score the workflow against `ind_checklist_gold.json` for the three IND protocols. Save `ind-checklist.json`. Pass when item status accuracy is at least `0.85`.
- [ ] End to end. Run `npx playwright test web/e2e/ind.spec.ts`, which runs the workflow, corrects one item at the pause, and exports the `.docx`. Save `p14-ind.png`. Pass when the export contains the corrected item.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Dollars and wall time per checklist run.
- [ ] Probe. Run the workflow on the three IND protocols.
- [ ] Baseline. Trunk has no workflow. Record the head cost and time.
- [ ] Rule. Fail if a run costs more than $1 or takes more than 5 minutes.

**Review gate.** The operator reviews before merge.

- [ ] Copy the Playwright screenshots into `docs/media/p14-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of one checklist run with a correction. Save it as `docs/media/p14-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P14 to the stack and the operator lands it.

## Prototype the opt-in screen watcher as a stretch goal (P15)

**Depends on.** P13.

**Files.**

- [ ] Create `watcher/` as a small macOS Python agent.
- [ ] Create `src/fda_copilot/api/watch.py`.
- [ ] Create `evals/watcher/screens/` with 20 labeled screenshots.

**Build.**

- [ ] Capture the frontmost window only while the user has turned watching on, at most once every 10 seconds, and only when the image changed.
- [ ] Send the frame to `claude-sonnet-5-5` to decide whether the screen shows regulatory content. When it does, pass the visible text to the P13 chat agent and show a notification with one cited suggestion.
- [ ] Keep frames in memory only. Never write them to disk or to the database.

**You see.**

- [ ] With a consent form open in a text editor, a notification appears within 30 seconds with a `21 CFR 50.25` suggestion.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/watcher/test_throttle.py` feeds identical and changed frames to the throttle and asserts the exact list of frames sent. Run `uv run pytest tests/watcher`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Classify the 20 labeled screenshots. Save `watcher.json`. Pass when accuracy is at least `0.85` and no non-regulatory screen produces a suggestion.
- [ ] End to end. Run `scripts/e2e/p15.sh`, which opens a fixture consent form, turns watching on for 60 seconds, and turns it off. Save `p15-notify.png` and `p15-e2e.log`. Pass when one notification appears and the log shows no captures after watching was turned off.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Dollars per minute of active watching.
- [ ] Probe. Watch a scripted 10-minute editing session and sum the token usage.
- [ ] Baseline. Trunk has no watcher. Record the head cost.
- [ ] Rule. Fail if the cost exceeds $0.10 per minute.

**Review gate.** The operator reviews before merge.

- [ ] Copy the notification screenshots into `docs/media/p15-review-<slug>.png`.
- [ ] Record a 30 to 60 second video of the watcher producing one suggestion. Save it as `docs/media/p15-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P15 to the stack and the operator lands it.

## Package the demo, the README, and the walkthrough video (P16)

**Depends on.** P14 and P15.

**Files.**

- [ ] Create `README.md` with the architecture diagram, eval results, and setup steps.
- [ ] Create `docs/media/walkthrough.mp4`.
- [ ] Create `scripts/e2e/clean_clone.sh`.

**Build.**

- [ ] Generate the eval results table in the README from `evals/baselines.json` with `scripts/readme_evals.py`, so the README never drifts from measured numbers.
- [ ] Link one LangSmith trace per surface.
- [ ] Record the walkthrough on a real ClinicalTrials.gov protocol, with one fix accepted and one rejected.

**You see.**

- [ ] A fresh clone, `cp .env.example .env`, keys filled in, and `docker compose up` start the full demo.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `tests/scripts/test_readme_evals.py` renders the table from a fixture baseline file and asserts the exact Markdown. Run `uv run pytest tests/scripts`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. The eval suite plus one scripted end-to-end check at the PR head, per the boot recipe.

- [ ] Eval. Run every eval suite and regenerate the README table. Save `evals-all.json`. Pass when every score meets `evals/baselines.json` and the README table matches the file.
- [ ] End to end. Run `scripts/e2e/clean_clone.sh`, which clones the repo into a temp directory and runs the P12 Playwright spec against it. Save `p16-e2e.log`. Pass when the spec passes from the clean clone.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Minutes from `git clone` to a passing P12 spec on a clean machine.
- [ ] Probe. Run `scripts/e2e/clean_clone.sh` once with Docker image caches cleared.
- [ ] Baseline. Trunk has no clean-clone script. Record the head time.
- [ ] Rule. Fail if it takes more than 15 minutes.

**Review gate.** None. P16 is not review-gated.

**Merge.**

- [ ] Verifier's clean verdict at the exact head SHA.
- [ ] Review comments triaged.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P16 to the stack and the operator lands it.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] Reply to the operator with the report the execution playbook names.

## Appendix A. Prototype evidence

- **The eCFR API returns paragraph-level XML.** On 2026-10-16, `GET https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-21.xml?part=50&section=50.25` returned a `DIV8` element with `citation` set to `21 CFR 50.25` and one `<P>` element per paragraph, starting `(a)` and then `(1)`. The endpoint refuses requests without an `Accept-Encoding` header that allows compression. Title 21 was up to date as of 2026-10-15. P03 depends on both facts.
- **Paragraph markers nest and combine.** The same API returned `312.32` with one `<P>` that starts `(c)(1) IND safety reports` and two different paragraphs that start `(2)`, one under `(c)` and one under `(d)`. P03 tracks the marker stack for that reason. The 7-day report rule is in `(c)(2)`, which P13's end-to-end check relies on.
- **Anthropic has no embedding model.** Anthropic's embeddings page says "Anthropic does not offer its own embedding model" and points to Voyage AI. P06 settles the choice between `voyage-4` and `voyage-law-2` by the retrieval eval, not by opinion.
- **A Claude subscription cannot power the app.** Anthropic's Agent SDK overview says third-party products may not offer claude.ai login without approval. The app uses a Console API key.
- **Still unproven.** The LangGraph `Send`, `interrupt()`, and Postgres checkpointer APIs are named from memory. P09 and P11 confirm them against the installed `langgraph` version before building on them. Every cost and latency budget in this plan is a guess until its PR records a baseline.

## Appendix B. Alternatives rejected

- **Ten swarm lanes per PR.** The operator scaled live verification down because `control-ui` is not installed and the project has one developer. The eval suite carries the regression signal instead.
- **One agent with all regulations in context.** It is simpler, but it shows no orchestration, and it cannot filter retrieval by domain.
- **Hosted deployment.** The operator chose local only. CI, Docker, and the clean-clone check show production readiness without hosting cost.
- **A Word add-in.** It doubles the UI work. Upload through the web UI covers the demo.
- **An LLM judge for faithfulness.** An exact quote match against stored text is cheaper and cannot be talked into a pass.

## Appendix C. Risks

- **The eval set leaks into prompts.** Prompt tuning on the held-out protocols would inflate the scores. P07 marks the held-out set, and P10 reports it separately.
- **Guidance PDFs chunk badly.** Headings in FDA PDFs are inconsistent. P04 caps the list at ten documents, and its end-to-end check reads five chunks against the source.
- **Model refusals.** Regulatory text rarely triggers safety classifiers, but P09 handles `stop_reason == "refusal"` and enables server-side fallbacks.
- **Cost overrun from a runaway graph.** P09 and P10 set per-review budgets. Set a spending limit on the Console key before P09.
- **Screen capture privacy.** P15 is opt-in, keeps frames in memory only, and its end-to-end check proves that capture stops when watching is turned off.
- **The plan checker expects ten lanes.** `check-plan.mjs` reports one lane problem per PR. The operator accepted this on 2026-10-16.

## Appendix D. Links and reading list

- `docs/BRIEF.md` holds the product decisions.
- Each PR has one GitHub issue on `zhipengzhu1-dotcom/10-16-2026-FDA-Agent`. The issue body is that PR's owner brief.
- P09 and P10 get `/architect` before code, because the graph shape crosses many function boundaries.
- P10 and P11 get an independent `/code-review` at high effort before the verdict.
- Keep a decision trail per `show-me-your-work` in `docs/decisions.md` during the run.

**Standing orders.** Paste these verbatim into every owner brief.

1. Write Python 3.12 with type hints. `ruff`, `mypy --strict` on `src`, and `pytest` pass before every push.
2. Use the Anthropic Python SDK. The models are `claude-haiku-5-5` for routing, `claude-sonnet-5-5` for specialists and chat, and `claude-opus-5-5` for the verifier. Never hard-code an API key.
3. Every finding and every chat answer cites a stored `RegSection`. Code that shows the user an uncited or unverified claim is a defect.
4. Never tune prompts on the held-out protocols in `evals/review/gold.jsonl`.
5. Tests call code the way users do and assert literal expected values.
6. Never push to `main`, force-push a shared branch, merge, or retarget a PR. The root owns the stack and the operator lands it.
7. Write only the paths your issue's SCOPE names. Report anything outside scope as a follow-up.
8. Keep a comment only for a non-obvious reason the code cannot show.
