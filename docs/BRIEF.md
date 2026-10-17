# FDA regulatory co-pilot: project brief

Agreed in the kickoff interview on 2026-10-16. This brief is the contract for version 1. Change it here first when the plan changes.

## What we are building

A multi-agent assistant that reviews preclinical and clinical study documents against FDA regulations while you write them. Every finding cites the exact regulation text it relies on, and nothing changes in your document until you accept the suggested fix.

The project is a portfolio piece for agent engineer roles. It has to show four things an employer can inspect: multi-agent orchestration, a measured retrieval eval suite, human-in-the-loop control, and production-ready packaging.

## Decisions

| Topic | Decision |
| --- | --- |
| Primary user | The author, as a portfolio project |
| Success in 4 to 8 weeks | A working local demo, a recorded walkthrough video, and a clean public repo |
| Regulatory scope | IND (21 CFR 312), IDE (21 CFR 812), GLP (21 CFR 58), GCP (ICH E6(R3)), plus 21 CFR 50 (informed consent) and 21 CFR 56 (IRBs) |
| Centerpiece | Live document reviewer with inline, cited findings |
| Later surfaces, in order | Chat sidebar, then workflow automation, then screen watcher as a stretch goal |
| Stack | Python, LangGraph, FastAPI, Next.js frontend, Postgres with pgvector |
| Models | Claude through a Console API key. A subscription login is not allowed for apps built on Anthropic's SDKs. |
| Human-in-the-loop | Each finding proposes a fix. The graph pauses with LangGraph `interrupt()` until you accept or reject it. |
| Test documents | Public protocols from ClinicalTrials.gov for the demo. Synthetic protocols with planted violations for the eval suite. |
| Deployment | Local only. `docker compose up` starts everything. CI runs the eval suite on every pull request. |

## Model routing

| Role | Model | Price per 1M tokens (input / output) |
| --- | --- | --- |
| Router: assigns each document section to IND, IDE, GLP, or GCP | `claude-haiku-5-5` | $0.10 / $0.50 |
| Specialist reviewers, one per domain | `claude-sonnet-5-5` | $2 / $10 |
| Verifier: confirms each cited passage supports its finding | `claude-opus-5-5` | $4 / $20 |

Prices come from Anthropic's model table cached on 2026-10-06. The estimate of under $1 per 30-page protocol is a guess until the first eval run measures it. Set a spending limit on the Console key before the first run.

## Core data shapes

Define these before writing any graph logic. The rest of the code reads and writes them.

- `RegSection` is one citable unit of regulation text. Fields: `citation` (for example `21 CFR 312.32(c)(1)`), `source` (`cfr`, `ich`, or `fda_guidance`), `title`, `text`, `effective_date`, and `url`. CFR text is chunked at the paragraph level, so a citation always points at one chunk.
- `DocSection` is one section of the user's document. Fields: `id`, `heading`, `text`, and a character span into the original file.
- `Finding` is one issue a specialist raises. Fields: `doc_section_id`, `domain`, `severity`, `issue`, `citations` (a non-empty list of `RegSection` citations with the quoted text), `proposed_fix`, and `status`.
- A finding's `status` moves through a fixed state machine: `proposed`, then `verified` or `discarded` by the verifier, then `accepted` or `rejected` by you. A finding with no verified citation never reaches you.

## Review graph

1. Parse the uploaded `.docx` or `.pdf` into `DocSection` records.
2. The router tags each section with one or more domains.
3. LangGraph's `Send` API fans the tagged sections out to the four specialist agents, which run in parallel. Each specialist retrieves only from its part of the corpus, using hybrid keyword and vector search.
4. The verifier checks every finding's quoted citation against the stored `RegSection` text. Findings that fail are discarded and logged.
5. The graph calls `interrupt()` and shows the verified findings in the UI.
6. Accepted fixes are applied to the document. Rejected ones are kept in the trace as eval feedback.

## Corpus

- 21 CFR Parts 50, 56, 58, 312, and 812, pulled from the eCFR API so each section keeps its official citation and date.
- ICH E6(R3), ICH M3(R2), and the FDA guidance PDFs the specialists cite most. The full list is chosen in milestone 1.
- Anthropic has no embeddings endpoint, so embeddings come from a separate provider such as Voyage AI or a local open model. This is from memory and gets confirmed in milestone 1.

## Evaluation

The eval suite is the main differentiator, so it is built before the agents.

- **Retrieval set.** 50 or more regulatory questions, each labeled with the `RegSection` citations that answer it. Metric: recall at 5.
- **Planted-violation set.** Synthetic protocols, each containing known violations. One example is a consent form that leaves out an element required by 21 CFR 50.25. Metrics: the share of planted violations found, the share of findings that are real, and the share of findings whose citation is correct.
- **Faithfulness.** The share of findings whose quoted text matches the stored regulation exactly. This check is mechanical, not an LLM judge.
- CI runs all three sets on every pull request and fails if a metric drops below its recorded baseline.

## Definition of done for version 1

- On the held-out planted-violation set, the reviewer finds at least 80% of planted violations, and at least 90% of the findings it shows carry a correct citation. Both thresholds are proposals until the first baseline run.
- Every finding shown in the UI has passed the verifier.
- `docker compose up` on a clean machine starts the full demo.
- The walkthrough video shows a real ClinicalTrials.gov protocol reviewed end to end, with at least one fix accepted and one rejected.

## Milestones

These are estimates, not commitments.

1. **Week 1.** Corpus ingestion, hybrid retrieval, the retrieval eval set, and a baseline score.
2. **Weeks 2 and 3.** The review graph for one domain (informed consent, 21 CFR 50) and the planted-violation eval.
3. **Week 4.** All four specialists, the router, and the verifier.
4. **Week 5.** The Next.js review UI with accept and reject.
5. **Week 6.** The chat sidebar on the same retrieval core.
6. **Week 7.** Workflow automation, starting with an IND submission checklist generator.
7. **Week 8.** The screen watcher as a stretch goal, then the walkthrough video.

## Out of scope for version 1

- Hosted public deployment.
- Word or Google Docs add-ins. Documents are uploaded through the web UI.
- Legal or regulatory advice. The UI labels every output as a drafting aid that needs review by a qualified person.
