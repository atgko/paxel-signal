import json
import os
from datetime import date
from pathlib import Path

import anthropic
import pandas as pd

from agent.config import MODEL_NAME

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "reporter_system.txt").read_text(encoding="utf-8")

EMAIL_DELIMITER = "---EMAIL_DRAFT---"

REPORT_TEMPLATE = """
# Signal Weekly Research Digest
**Generated:** {date}
**Calls analyzed:** {n} calls ({date_range})

---

## Top 5 Priorities This Week

### 1. {Priority name — be specific, e.g. "NDC and Wholesaler Numbers on Product Cards"}
**Who's asking:** {personas, mention count}
**What they need:** {2-3 sentences — describe the need, not the solution}
**In their words:** *"{best supporting quote}"*
**Recommended action:** {one concrete, specific next step — e.g. "Add NDC field and facility-specific wholesaler number to the Products section within the Contracts & Pricing page"}

### 2. ...
### 3. ...
### 4. ...
### 5. ...

---

## Bugs Requiring Attention
{bullet list of High-priority bugs with a one-line description each, or "None identified this period."}

---

## Data & Compliance Flags
{bullet list of data problems and compliance/legal insights, or "None identified this period."}

---

## Needs Matrix

{markdown table of the needs matrix — persona rows, insight type columns}

---

## Analyst Notes
{2-3 sentences of direct commentary — what is the single most important pattern, what can safely wait, any risk or opportunity Luke should know about}
""".strip()

EMAIL_DRAFT_INSTRUCTIONS = f"""
After the markdown report, append a section delimited by the exact string {EMAIL_DELIMITER} on its own line, followed by a plain-text email version of the report formatted for sending to an internal team. The email should:
- Have a subject line on the first line prefixed with "Subject: "
- Be written in plain text (no markdown formatting, no asterisks, no pound signs)
- Cover the top 3 priorities only (not all 5) to keep it scannable for a busy team
- End with a clear call to action for the recipient (e.g., "Let me know if you want to discuss any of these before Thursday's sprint.")
- Sound like it was written by Luke, not a bot
""".strip()


def _needs_matrix_to_markdown(df: pd.DataFrame) -> str:
    headers = ["Persona"] + list(df.columns)
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for idx, row in df.iterrows():
        cells = [str(idx)] + [str(v) for v in row.tolist()]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def generate_report(
    synthesis: dict,
    needs_matrix_df: pd.DataFrame,
    api_key: str | None = None,
) -> tuple[str, str]:
    """Generate the weekly markdown report and plain-text email draft.

    Returns (report_md, email_draft). email_draft is "" if the delimiter
    is missing from Claude's response.
    """
    user_message = (
        "Produce the weekly report in exactly this markdown structure "
        "(replace the {...} placeholders with real content; keep all headings, "
        "horizontal rules, and formatting exactly as shown):\n\n"
        f"{REPORT_TEMPLATE}\n\n"
        f"Use today's date {date.today().isoformat()} as the Generated date.\n\n"
        f"Aggregated research data to analyze:\n{json.dumps(synthesis, ensure_ascii=False)}\n\n"
        f"Needs matrix for the Needs Matrix section:\n{_needs_matrix_to_markdown(needs_matrix_df)}\n\n"
        f"{EMAIL_DRAFT_INSTRUCTIONS}"
    )

    client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": user_message}],
    )
    raw_response = next(block.text for block in response.content if block.type == "text")

    if EMAIL_DELIMITER in raw_response:
        report_md, _, email_draft = raw_response.partition(EMAIL_DELIMITER)
        return report_md.strip(), email_draft.strip()

    return raw_response.strip(), ""
