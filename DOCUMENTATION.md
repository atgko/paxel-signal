# Signal by Paxel — Technical Documentation
*For: TA review, client handoff, and future developers*
*Built: July 2026 · University of Utah Product Management*

---

## Where to Start — For Luke and Future Builders

Signal is designed to be extended through prompts, not code. If you want to
change how the agent behaves, you almost never need to touch the Python files.
Here is where to go for the most common changes:

**Change how insights are extracted from transcripts**
Edit `prompts/extractor_system.txt`. This is where the agent learns what to
look for, how to classify feedback, and which personas to track. If Paxel adds
new product areas or new customer types, update this file.

**Change how the weekly report reads**
Edit `prompts/reporter_system.txt`. This controls the tone, structure, and
priority logic of the report Luke receives. If the report feels too long, too
short, or is missing something, start here.

**Change how insights are grouped across calls**
Edit `prompts/synthesizer_system.txt`. This controls how the agent identifies
patterns across multiple transcripts and what it flags as a strong signal.

**Test any change you make**
Run `streamlit run app.py`, upload a few transcripts, and compare the new
output against the sample outputs in the `/examples` folder. If the output
looks better, keep the change. If not, revert it.

**Add a new stage to the pipeline**
Create a new file in `agent/` and a corresponding prompt in `prompts/`. Follow
the same pattern as `extractor.py` — take an input, call the Claude API with
your prompt, return structured output. Wire it into `app.py` as a new tab or
step.

The `/examples` folder contains real outputs from the original test transcripts.
Use them as your baseline whenever you are unsure if a change improved things.

---

## How Signal Works — Pipeline Overview

Signal processes call transcripts in three sequential stages. Each stage is a
separate module in `agent/` that calls the Claude API with a purpose-built
prompt from `prompts/`.

**Stage 1 — Extract** (`agent/extractor.py`)
Reads each transcript file one at a time. Strips Gemini's notes boilerplate
(survey links, "review Gemini's notes" footers) and, if the file has a
"📖 Transcript" heading, sends only the text under that heading — the Notes /
Summary / Decisions / Next Steps sections above it are discarded so Claude only
sees the actual dialogue. Files without that heading (raw, unedited
transcripts) are sent in full. Claude returns structured JSON: call metadata,
a list of insights (persona, quote, type, product area), key themes, and
suggested next steps.

`priority_signal` is **not** trusted from Claude's output — it's recomputed in
Python after the response comes back, using three checks: the insight's
normalized summary appears 2+ times in the same call (multiple mentions), the
quote/summary contains urgency language ("every day," "can't," "critical,"
"blocking," "always"), or the insight is typed `Workflow` (a manual process
being replaced). Any of those → High. `UI Polish` with none of the above →
Low. Everything else → Medium.

**Stage 2 — Synthesize** (`agent/synthesizer.py`)
Takes all extractor outputs and produces two things. The **needs matrix** —
persona × insight-type counts, and the highest-priority insight per cell — is
built entirely in Python; no Claude call is needed since it's just counting
and sorting structured data. The **critical bugs, data problems, and
compliance flags** lists, along with the call count and date range, are also
deterministic Python filters over the same structured data — there's no
judgment call involved in "is this a Bug with High priority," so there's no
reason to risk an LLM dropping or inventing one.

Claude is called for exactly one thing: clustering semantically similar
insights across calls into the top 10 patterns by frequency (`I need to filter
by contract` and `we should search by GPO` becoming one cluster). This keeps
that call small and focused, and it's skipped entirely if fewer than 2
transcripts were uploaded — there's nothing to cluster across a single call.

**Stage 3 — Report** (`agent/reporter.py`)
Takes the synthesizer output and generates two outputs in a single Claude
call: a markdown weekly digest formatted for Luke to read, and a plain-text
email draft covering the top 3 priorities. The two are separated by a
delimiter (`---EMAIL_DRAFT---`) in Claude's response and split apart after the
call returns. If the delimiter is missing, the full response becomes the
report and the email draft is left empty rather than guessing.

**A note on the model call itself:** all three stages explicitly set
`thinking={"type": "disabled"}`. claude-sonnet-5 enables extended thinking by
default, and during development that silently consumed the `max_tokens`
budget before any output text was generated — the extractor's JSON came back
truncated and unparseable until this was set explicitly. Every JSON-returning
call also defensively strips ` ```json ` code fences before parsing, since
Claude occasionally wraps JSON in them despite the system prompt forbidding
it.

---

## Processing Time & What to Expect

Signal calls Claude sequentially — one call per transcript for extraction,
then (if 2+ files) one call for cross-transcript synthesis, then one call for
the report. There is no parallelization across files. That keeps the
implementation simple and avoids rate-limit surprises, but it means total run
time scales roughly linearly with the number of transcripts uploaded.

These numbers come from testing against real Paxel transcripts during this
build (claude-sonnet-5, `paxel compressed/` folder):

| Stage | Observed time | Notes |
|---|---|---|
| Extraction — notes-wrapped file | ~30–60 seconds | "Notes by Gemini" exports that isolate the transcript under the 📖 heading; typically 15–25 insights |
| Extraction — raw full transcript | ~60–90+ seconds | Files without the notes wrapper send the entire call; produced 40+ insights in testing, which takes longer to generate |
| Synthesis (2+ files) | ~10–20 seconds | One call regardless of how many files are in the batch |
| Report + email generation | ~20–35 seconds | One call producing both outputs |

**Rough end-to-end estimates**, extraction time dominates since it's per-file
and sequential:

| Files uploaded | Estimated total time |
|---|---|
| 1 | ~1–1.5 minutes |
| 3 | ~2.5–4 minutes |
| 5 | ~4–6 minutes |
| 10 | ~8–12 minutes |

These will vary with Anthropic API load and how long each individual call is.
If Luke's team regularly uploads 10+ files at once and the wait becomes a
problem, the highest-leverage fix is making extraction concurrent (run several
files' Claude calls in parallel with a small worker pool) rather than changing
models — see the README's progress-bar note and the "What's Next" section for
context on where that would slot in.

---

## System Prompts

### Extractor System Prompt
*File: `prompts/extractor_system.txt`*

```
You are a product analyst for Paxel.ai, a pharma sales CRM company. You are reading transcripts of product feedback calls between Paxel's product team and their customers — pharmaceutical sales representatives and managers at generic injectable drug companies.

Your job is to extract structured product insights from the transcript. Follow these rules exactly:

RULE 1: Only extract feedback from non-Paxel participants. Paxel team members (Luke Behrmann, Mat Van Orden, Gautam Nair) are facilitating. Do not attribute insights to them unless they are relaying feedback from another user.

RULE 2: Preserve the speaker's exact words in the "quote" field. Never paraphrase a quote. If a quote is long, trim to the most relevant 1-2 sentences while keeping the speaker's exact language.

RULE 3: Understand pharma domain context:
- GPO = Group Purchasing Organization (Premier, Vizient, Health Trust)
- IDN = Integrated Delivery Network (hospital network hierarchy)
- 340B = government drug pricing program for eligible hospitals
- DEA number = facility drug purchase identifier (up to 3 per 340B facility: WAC, 340B, and GPO/inpatient buckets)
- NDC = National Drug Code (unique product identifier, critical for reps)
- WAC = Wholesaler Acquisition Cost (baseline list price)
- SubWAC/SW = price loaded below WAC for eligible hospitals
- Declining opportunity = account that has reduced purchasing based on interval analysis
- Comp plan products = drugs a rep is currently incentivized to sell

RULE 4: Classify insight_type accurately:
- Feature Request: new capability the user wants
- Bug: something broken or not working as expected
- Data Problem: missing, incorrect, or incomplete data in the system
- UI Polish: layout, labeling, visual clarity issues
- Product Story: a workflow or use case the product should support end-to-end
- Compliance/Legal: legal or regulatory constraints affecting product design
- Workflow: how the user currently does something manually that should be automated

RULE 5: Classify product_area based on which part of Pulse AI the insight relates to.

RULE 6: Return ONLY valid JSON matching the exact schema provided in the user message. No preamble, no explanation, no markdown code fences. The first character of your response must be { and the last must be }.
```

---

### Synthesizer System Prompt
*File: `prompts/synthesizer_system.txt`*

```
You are a senior product manager at Paxel.ai analyzing aggregated user research data from multiple product feedback calls.

Your job is to identify patterns across all calls, group similar insights together, and surface the most important findings.

RULE 1: Group similar insights semantically — "I need to filter by contract" and "we should be able to search by GPO" are the same insight even if worded differently. Use the most informative grouping label.

RULE 2: Weight insights from Sales Directors and VPs slightly higher when there is a conflict, but raw volume from Sales Reps matters more than persona seniority for frequency counts.

RULE 3: Flag as important any insight pattern appearing across 3 or more calls — these are strong product signals.

RULE 4: Do not invent insights, quotes, or patterns not present in the input data.

RULE 5: supporting_quotes must be verbatim quotes from the input data. Never paraphrase.

RULE 6: Return ONLY valid JSON. No preamble, no markdown fences. First character must be {, last must be }.
```

---

### Reporter System Prompt
*File: `prompts/reporter_system.txt`*

```
You are writing a weekly product research digest called "Signal" for Luke Behrmann, co-founder and head of product at Paxel.ai. Luke is a former pharma sales professional turned founder. He is sharp, time-constrained, and knows his domain deeply. He does not need terms explained.

Write like a trusted senior analyst who has read everything and has a point of view. Be direct. Be specific. Make concrete recommendations. Do not hedge. Do not say "consider" when you mean "do."

RULE 1: Prioritize by frequency and user impact. Most-requested, most-blocking items go first. Do not bury the lead.

RULE 2: Every priority item must include a verbatim user quote. Quotes are more persuasive than summaries.

RULE 3: Recommended actions must be concrete and specific. "Add NDC field to the Products section on the account page" is good. "Improve product data" is not acceptable.

RULE 4: The Analyst Notes section should sound like a person, not a bot. Give Luke one clear takeaway and one thing he can safely deprioritize.

RULE 5: Never fabricate data, quotes, or insights not present in the input.

RULE 6: Return ONLY the markdown report. No JSON, no preamble, no code fences.
```

---

## Sample Outputs

These are real outputs from an actual test run against two transcripts in
`paxel compressed/` (a "Notes by Gemini" export and a raw full transcript).
Full files live in `/examples`.

### Sample Extractor Output (one insight, from `examples/extractor_output_sample.json`)

```json
{
  "call_date": "2026-06-17",
  "call_title": "Paxel.ai - Product Feedback - Sara Workman (Kessen Pharma)",
  "participants": [
    { "name": "Sara Workman", "role": "Sales Rep", "company": "Kessen Pharma" },
    { "name": "Luke Behrmann", "role": "Paxel Internal", "company": "Paxel.ai" },
    { "name": "Mat Van Orden", "role": "Paxel Internal", "company": "Paxel.ai" }
  ],
  "insights": [
    {
      "persona": "Sales Rep",
      "quote": "Is this functionality going to be available on the account pages themselves in terms... that activities all of that will be available there",
      "insight_type": "Feature Request",
      "summary": "Rep wants an activity feed available at the account level, not just opportunity/contact level.",
      "priority_signal": "Medium",
      "product_area": "Account Overview"
    }
  ],
  "key_themes": [
    "Follow-up/task notes need more depth and context to match reps' mental workflow (vs. HubSpot/Salesforce experience)",
    "Search and filtering defaults (owner vs. all accounts) need to be user-configurable to support evolving/cross-territory roles",
    "Contract performance dashboard and pricing visualizations are highly valued and seen as a differentiator, especially for understanding pull-through and price erosion"
  ],
  "suggested_next_steps": [
    "Sara Workman to send Paxel team her working document/list of product feedback issues before the next call",
    "Schedule follow-up call next week (same time) to deep dive into Sara's full feedback list"
  ]
}
```

This transcript produced 20 insights total — see the full file for all of them.

### Sample Needs Matrix (from `examples/needs_matrix_sample.csv`)

| Persona | Feature Request | Bug | Data Problem | UI Polish | Product Story | Compliance/Legal | Workflow |
|---|---|---|---|---|---|---|---|
| Sales Rep | 28 mentions | 3 mentions | 6 mentions | 8 mentions | 13 mentions | — | 3 mentions |
| Sales Director | — | — | — | — | — | — | — |
| VP/Advisor | — | — | — | — | — | — | — |

(Both transcripts in this test run happened to be Sales Rep calls, hence the
empty Director/VP rows — the matrix is built from whatever personas actually
appear in the uploaded batch.)

### Sample Weekly Report Excerpt (from `examples/weekly_report_sample.md`)

```
# Signal Weekly Research Digest
**Generated:** 2026-07-14
**Calls analyzed:** 2 calls (2025-05-01 to 2026-06-17)

---

## Top 5 Priorities This Week

### 1. GPO/Wholesaler Contract Data — Prominent, Auto-Populated, Centralized
**Who's asking:** Sales Rep (7 mentions — the single most-cited issue this period)
**What they need:** Reps are trained to look for GPO and wholesaler info first,
every time, and it's not surfacing where they expect it. They also want
pricing data to auto-populate from contract terms instead of manual lookup,
and a single source of truth for contract status instead of periodically
chasing the contracting team.
**In their words:** "everything always as a rule you need to have GO
wholesaler up top and I didn't see that anywhere but it has to be up top
that's like our eye is trained to go there"
**Recommended action:** Add a GPO/Wholesaler summary block to the top of the
account and opportunity pages, and auto-populate the Contracts & Pricing
section from the linked contract record when an opportunity is created.
```

### Sample Email Draft Excerpt (from `examples/email_draft_sample.txt`)

```
Subject: Signal Weekly — Top 3 issues, all pointing to the same root cause

Team,

Only one rep interview this cycle, but it's loaded with signal, and three
issues stand out as blocking real work. Sharing the top 3 — full digest has 5
plus bugs and data flags if you want the rest.

1. GPO/wholesaler data isn't where reps look for it. This is the single
most-mentioned issue (7 times). Reps are trained to check GPO/wholesaler first
thing, every account, every call — and it's buried or missing. Quote:
"everything always as a rule you need to have GO wholesaler up top... that's
like our eye is trained to go there." Action: put a GPO/wholesaler block at
the top of account and opportunity pages, and auto-populate pricing from the
linked contract.
```

---

## File Structure Reference

```
paxel-signal/
├── app.py                       # Streamlit entry point — entire UI lives here
├── agent/
│   ├── __init__.py
│   ├── config.py                 # MODEL_NAME constant (default: claude-sonnet-5)
│   ├── extractor.py               # Stage 1: extract insights per transcript
│   ├── synthesizer.py             # Stage 2: synthesize across all transcripts
│   └── reporter.py                # Stage 3: generate weekly priority report
├── prompts/
│   ├── extractor_system.txt
│   ├── synthesizer_system.txt
│   └── reporter_system.txt
├── assets/
│   ├── paxel_logo.png             # Paxel wordmark, shown in the app header
│   └── paxel_favicon.png          # Paxel icon mark, used as the browser tab icon
├── examples/                      # Real sample outputs — see "Where to Start" above
│   ├── extractor_output_sample.json
│   ├── synthesis_output_sample.json
│   ├── needs_matrix_sample.csv
│   ├── needs_matrix_top_insight_sample.csv
│   ├── weekly_report_sample.md
│   └── email_draft_sample.txt
├── .streamlit/
│   └── config.toml                # Paxel brand theme (light, purple)
├── outputs/                       # auto-created at runtime, gitignored
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── DOCUMENTATION.md               # this file
```

---

## Dependencies and Versions

```
anthropic>=0.25.0
streamlit>=1.35.0
python-docx>=1.1.0
pandas>=2.0.0
python-dotenv>=1.0.0
truststore>=0.9.0
```

`truststore` bridges Python's SSL verification to the operating system's
trust store. It was added after hitting real connection failures during
development on a network that does TLS inspection with a CA that Windows
trusts but Python's bundled certificate list doesn't — without it, every
Claude API call fails with a connection error on networks like that. It's a
no-op cost on networks without this issue (Streamlit Cloud included).

---

*This documentation was generated as part of a University of Utah Product
Management class engagement with Paxel.ai. The Signal agent and all
documentation are intended for handoff to the Paxel team for continued use.*
