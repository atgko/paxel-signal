import json
import os
import re
from collections import Counter
from pathlib import Path

import anthropic
import docx

from agent.config import MODEL_NAME

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "extractor_system.txt").read_text(encoding="utf-8")

TRANSCRIPT_HEADING = "📖 Transcript"

BOILERPLATE_MARKERS = [
    "You should review Gemini's notes",
    "qualtrics.com",
    "Get tips and learn how Gemini takes notes",
]

URGENCY_KEYWORDS = ["every day", "can't", "cannot", "need", "critical", "blocking", "always"]

SCHEMA_DESCRIPTION = """
Return a JSON object matching this exact schema:

{
  "call_date": "YYYY-MM-DD or Unknown",
  "call_title": "string",
  "participants": [
    {
      "name": "string",
      "role": "Sales Rep | Sales Director | VP/Advisor | Paxel Internal",
      "company": "string"
    }
  ],
  "insights": [
    {
      "persona": "Sales Rep | Sales Director | VP/Advisor",
      "quote": "verbatim or near-verbatim quote from transcript",
      "insight_type": "Feature Request | Bug | Data Problem | UI Polish | Product Story | Compliance/Legal | Workflow",
      "summary": "one sentence summary of the insight",
      "priority_signal": "High | Medium | Low",
      "product_area": "Account Overview | Contracts & Pricing | Opportunities | Contacts | Dashboard | Search & Navigation | Data & Identifiers | Notifications | Other"
    }
  ],
  "key_themes": ["list of 3-5 overarching themes from this call"],
  "suggested_next_steps": ["list extracted from transcript if present"]
}
""".strip()


class TranscriptReadError(Exception):
    """Raised when a file can't be read as a transcript (bad format, unsupported type)."""


def _read_raw_text(file_path: str) -> str:
    path = Path(file_path)
    try:
        if path.suffix.lower() == ".docx":
            document = docx.Document(str(path))
            return "\n".join(p.text for p in document.paragraphs)
        if path.suffix.lower() == ".txt":
            return path.read_text(encoding="utf-8")
    except Exception as e:
        raise TranscriptReadError(f"Could not read {path.name}: {e}") from e
    raise TranscriptReadError(f"Unsupported file type: {path.suffix} ({path.name})")


def _strip_boilerplate(text: str) -> str:
    lines = text.split("\n")
    kept = [line for line in lines if not any(marker in line for marker in BOILERPLATE_MARKERS)]
    return "\n".join(kept)


def _isolate_transcript_section(text: str) -> str:
    idx = text.find(TRANSCRIPT_HEADING)
    if idx == -1:
        return text
    return text[idx + len(TRANSCRIPT_HEADING):].strip()


def _prepare_transcript_text(file_path: str) -> str:
    raw = _read_raw_text(file_path)
    cleaned = _strip_boilerplate(raw)
    return _isolate_transcript_section(cleaned)


def _strip_code_fences(text: str) -> str:
    """Claude sometimes wraps JSON in ```json fences despite instructions not to."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _apply_priority_signal(insights: list[dict]) -> list[dict]:
    """Priority is decided in Python, not by Claude — see PRD priority_signal logic.

    "Mentioned by 2+ speakers" is approximated by grouping insights within this
    call whose summaries normalize to the same text; UI Polish defaults to Low
    since the PRD calls it out as the canonical low-priority example.
    """
    normalized = [re.sub(r"[^a-z0-9 ]", "", i.get("summary", "").lower()).strip() for i in insights]
    counts = Counter(normalized)

    for insight, norm in zip(insights, normalized):
        text = f"{insight.get('quote', '')} {insight.get('summary', '')}".lower()
        mentioned_multiple = counts[norm] >= 2
        has_urgency = any(kw in text for kw in URGENCY_KEYWORDS)
        replaces_workaround = insight.get("insight_type") == "Workflow"

        if mentioned_multiple or has_urgency or replaces_workaround:
            insight["priority_signal"] = "High"
        elif insight.get("insight_type") == "UI Polish":
            insight["priority_signal"] = "Low"
        else:
            insight["priority_signal"] = "Medium"

    return insights


def extract_insights(file_path: str, api_key: str | None = None) -> dict:
    """Extract structured insights from a single transcript file.

    Raises ValueError (with the filename in the message) if Claude's response
    is not valid JSON.
    """
    transcript_text = _prepare_transcript_text(file_path)
    filename = Path(file_path).name

    user_message = (
        f"{SCHEMA_DESCRIPTION}\n\n"
        f"Transcript filename: {filename}\n\n"
        f"Transcript:\n{transcript_text}"
    )

    client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": user_message}],
    )

    raw_response = next(block.text for block in response.content if block.type == "text")

    try:
        result = json.loads(_strip_code_fences(raw_response))
    except json.JSONDecodeError as e:
        print(f"[extractor] Failed to parse JSON response for {filename}:\n{raw_response}")
        raise ValueError(f"Claude returned invalid JSON while extracting insights from {filename}") from e

    result["insights"] = _apply_priority_signal(result.get("insights", []))
    return result
