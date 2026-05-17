"""Stage 1: shotlist generator.

Reads a plain-text essay/script and uses the Anthropic API to break it
into sequential visual beats ("segments"). Each segment carries the
verbatim narration text, a suggested visual type, and archive-friendly
search queries that later stages use to fetch and align candidate
imagery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal

import anthropic
from pydantic import BaseModel

from .config import Config

VisualType = Literal[
    "map",
    "portrait",
    "manuscript",
    "artifact",
    "architecture",
    "text_card",
    "landscape",
]

# The model returns segments without ids; ids are assigned deterministically
# after parsing so they are always sequential and zero-padded.
class _Segment(BaseModel):
    narration_text: str
    visual_type: VisualType
    visual_query: str
    search_priority: List[str]
    notes: str
    duration_estimate_sec: float


class _Shotlist(BaseModel):
    video_title: str
    segments: List[_Segment]


SYSTEM_PROMPT = """\
You are the shotlist editor for a YouTube channel about South Asian history. \
You work for a curator who makes every final creative decision; your job is to \
propose candidates, never to decide.

Given the full text of a narration script, break it into a sequential list of \
visual "beats" — segments. Each segment is a stretch of narration that should be \
covered by a single visual on screen.

Rules for segmentation:
- Work strictly in order. The segments, read top to bottom, must cover the \
entire script with no gaps and no overlaps.
- `narration_text` must be copied VERBATIM from the script — exact words, exact \
order. Do not paraphrase, summarise, correct, or rewrite. Concatenating every \
segment's narration_text in order must reproduce the original script. This is \
required so later stages can force-align the text to the narration audio.
- A new beat begins when the visual subject would naturally change — a new \
person, place, object, date, or idea. Typical beats are one to three sentences. \
Avoid single-clause fragments, and avoid beats longer than about four sentences.

For each segment provide:
- `visual_type`: the single best fit from map, portrait, manuscript, artifact, \
architecture, text_card, landscape. Use `text_card` only for moments better \
served by an on-screen title or quote than by a found image.
- `visual_query`: a 3-6 word search phrase for museum and archive image APIs \
(Wikimedia Commons, the Met, Smithsonian, Cleveland Museum of Art, Rijksmuseum). \
Use concrete, catalogued nouns — specific people, places, dynasties, objects, \
and periods. Avoid abstract or emotional words that archives do not index \
("powerful", "tragic", "golden age").
- `search_priority`: an ordered list of 2-3 queries. The first is the most \
specific; each later entry is a broader fallback for when the specific query \
returns nothing.
- `notes`: a short curation note when useful — what to look for, a caveat, a \
disambiguation, or a likely licensing concern. Use an empty string when there \
is nothing helpful to add.
- `duration_estimate_sec`: estimated on-screen time, derived from the narration \
length at roughly 2.5 spoken words per second.

Also provide `video_title`: a concise title for the video, inferred from the \
script.

Prefer historically precise queries. For South Asian topics, prefer the names, \
places, and institutions a museum catalogue would actually use. When a topic is \
visually ambiguous or unlikely to have a faithful public-domain image, say so \
in `notes` rather than inventing an over-specific query.
"""

MAX_OUTPUT_TOKENS = 16000


class ShotlistError(Exception):
    """Raised when a shotlist cannot be generated."""


def _format_api_error(exc: anthropic.APIError) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return "Anthropic API authentication failed — check your API key."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "The Anthropic API key lacks permission for this model."
    if isinstance(exc, anthropic.NotFoundError):
        return "Model not found — check the 'shotlist_model' value in config.json."
    if isinstance(exc, anthropic.RateLimitError):
        return "Anthropic API rate limit reached. Wait a moment and try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the Anthropic API — check your network connection."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API error ({exc.status_code}): {exc.message}"
    return f"Anthropic API error: {exc}"


def generate_shotlist(
    config: Config, script_text: str, script_filename: str
) -> dict:
    """Call the Anthropic API to turn a script into a shotlist dict.

    The returned dict matches the Stage 1 JSON schema.
    """
    script_text = script_text.strip()
    if not script_text:
        raise ShotlistError("The script is empty.")

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    user_prompt = (
        "Break the following history video script into a sequential visual "
        "shotlist.\n\n<script>\n" + script_text + "\n</script>"
    )

    try:
        response = client.messages.parse(
            model=config.shotlist_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=_Shotlist,
        )
    except anthropic.APIError as exc:
        raise ShotlistError(_format_api_error(exc)) from exc

    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "refusal":
        raise ShotlistError("The model declined to process this script.")
    if stop_reason == "max_tokens":
        raise ShotlistError(
            "The shotlist was cut off before completion (hit the output token "
            "limit). Try splitting the script into shorter parts."
        )

    parsed = response.parsed_output
    if parsed is None:
        raise ShotlistError("The model did not return a usable shotlist.")

    segments = []
    for index, seg in enumerate(parsed.segments, start=1):
        segments.append(
            {
                "id": f"seg_{index:03d}",
                "narration_text": seg.narration_text.strip(),
                "visual_type": seg.visual_type,
                "visual_query": seg.visual_query.strip(),
                "search_priority": [q.strip() for q in seg.search_priority if q.strip()],
                "notes": seg.notes.strip(),
                "duration_estimate_sec": round(seg.duration_estimate_sec, 1),
            }
        )

    if not segments:
        raise ShotlistError("The model returned a shotlist with no segments.")

    return {
        "video_title": parsed.video_title.strip(),
        "source_script": script_filename,
        "segments": segments,
    }


def write_shotlist(shotlist: dict, output_path: Path) -> None:
    """Write the shotlist dict to disk as pretty-printed JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(shotlist, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
