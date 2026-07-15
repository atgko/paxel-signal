import json
import os
from pathlib import Path

import anthropic
import pandas as pd

from agent.config import MODEL_NAME

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "synthesizer_system.txt").read_text(encoding="utf-8")

PERSONAS = ["Sales Rep", "Sales Director", "VP/Advisor"]
INSIGHT_TYPES = [
    "Feature Request",
    "Bug",
    "Data Problem",
    "UI Polish",
    "Product Story",
    "Compliance/Legal",
    "Workflow",
]
PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}

CLUSTER_SCHEMA_DESCRIPTION = """
Return a JSON object matching this exact schema:

{
  "top_insights_by_frequency": [
    {
      "insight_summary": "string — your grouping label for this cluster",
      "mention_count": int,
      "personas_affected": ["list of unique personas who mentioned it"],
      "product_area": "string",
      "supporting_quotes": ["up to 3 best quotes from across calls"]
    }
  ]
}

Return the top 10 clusters, sorted by mention_count descending.
""".strip()


def build_needs_matrix(extractor_outputs: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = {p: {t: 0 for t in INSIGHT_TYPES} for p in PERSONAS}
    top_insight = {p: {t: None for t in INSIGHT_TYPES} for p in PERSONAS}

    for output in extractor_outputs:
        for insight in output.get("insights", []):
            persona = insight.get("persona")
            itype = insight.get("insight_type")
            if persona not in PERSONAS or itype not in INSIGHT_TYPES:
                continue
            counts[persona][itype] += 1
            rank = PRIORITY_RANK.get(insight.get("priority_signal"), 3)
            current = top_insight[persona][itype]
            if current is None or rank < current[0]:
                top_insight[persona][itype] = (rank, insight.get("summary", ""))

    matrix_df = pd.DataFrame(
        {t: [f"{counts[p][t]} mentions" if counts[p][t] > 0 else "—" for p in PERSONAS] for t in INSIGHT_TYPES},
        index=PERSONAS,
    )
    top_df = pd.DataFrame(
        {t: [(top_insight[p][t][1] if top_insight[p][t] else "—") for p in PERSONAS] for t in INSIGHT_TYPES},
        index=PERSONAS,
    )
    return matrix_df, top_df


def matrix_to_csv(df: pd.DataFrame) -> str:
    return df.to_csv(index_label="Persona")


def _compute_date_range(extractor_outputs: list[dict]) -> str:
    dates = sorted(o.get("call_date") for o in extractor_outputs if o.get("call_date") and o.get("call_date") != "Unknown")
    if not dates:
        return "Unknown"
    if len(dates) == 1:
        return dates[0]
    return f"{dates[0]} to {dates[-1]}"


def _filter_insights(extractor_outputs: list[dict], predicate) -> list[dict]:
    return [i for o in extractor_outputs for i in o.get("insights", []) if predicate(i)]


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        import re
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _cluster_top_insights(extractor_outputs: list[dict], api_key: str | None) -> list[dict]:
    all_insights = []
    for output in extractor_outputs:
        for insight in output.get("insights", []):
            enriched = dict(insight)
            enriched["call_title"] = output.get("call_title")
            enriched["call_date"] = output.get("call_date")
            all_insights.append(enriched)

    user_message = (
        f"{CLUSTER_SCHEMA_DESCRIPTION}\n\n"
        f"Insights from {len(extractor_outputs)} calls:\n"
        f"{json.dumps(all_insights, ensure_ascii=False)}"
    )

    client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": user_message}],
    )
    raw_response = next(block.text for block in response.content if block.type == "text")

    try:
        parsed = json.loads(_strip_code_fences(raw_response))
    except json.JSONDecodeError as e:
        print(f"[synthesizer] Failed to parse JSON response:\n{raw_response}")
        raise ValueError("Claude returned invalid JSON during cross-transcript synthesis") from e

    return parsed.get("top_insights_by_frequency", [])


def synthesize(extractor_outputs: list[dict], api_key: str | None = None) -> dict:
    """Cross-transcript synthesis. Deterministic filters (bugs/data problems/
    compliance flags, call counts, date range) are computed in Python; Claude
    is only used for the semantic clustering that Python can't do reliably.
    """
    base = {
        "total_calls_analyzed": len(extractor_outputs),
        "date_range": _compute_date_range(extractor_outputs),
        "critical_bugs": _filter_insights(
            extractor_outputs,
            lambda i: i.get("insight_type") == "Bug" and i.get("priority_signal") == "High",
        ),
        "data_problems": _filter_insights(extractor_outputs, lambda i: i.get("insight_type") == "Data Problem"),
        "compliance_flags": _filter_insights(extractor_outputs, lambda i: i.get("insight_type") == "Compliance/Legal"),
    }

    if len(extractor_outputs) < 2:
        base["top_insights_by_frequency"] = []
        base["note"] = "Fewer than 2 transcripts provided — cross-call synthesis skipped."
        return base

    base["top_insights_by_frequency"] = _cluster_top_insights(extractor_outputs, api_key)
    return base
