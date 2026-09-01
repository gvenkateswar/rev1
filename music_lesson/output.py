"""Render a LessonResult: transcript, subtitles, JSON, or a practice sheet.

The practice sheet is the format that justifies the tool. A transcript answers
"what was said"; a student going back to a lesson six weeks later needs "what
did she tell me to work on, what did it sound like, and where do I scrub to to
hear it again". So the Markdown output leads with the tonic, the scale, and an
indexed list of every demonstration with its sargam, and puts the running
transcript underneath.
"""
from __future__ import annotations

import json

from . import lexicon, rhythm
from .core import ATTEMPT, DEMONSTRATION, LessonResult, LessonSegment

_KIND_LABEL = {
    "instruction": "says",
    "demonstration": "sings",
    "attempt": "sings (you)",
}


def _fmt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


def _fmt_srt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_text(result: LessonResult, show_roman: bool = True) -> str:
    """Plain running transcript, sung stretches shown as sargam."""
    lines = [
        f"Sa = {result.tonic.western}  ({result.tonic.hz:.1f} Hz)",
        f"Scale: {result.scale.summary()}",
        "",
    ]
    for segment in result.segments:
        who = f"{segment.speaker} " if segment.speaker else ""
        verb = _KIND_LABEL.get(segment.kind, segment.kind)
        head = f"[{_fmt_ts(segment.start)}] {who}{verb}:"
        if segment.is_sung:
            lines.append(f"{head} {segment.sargam}   ({segment.duration:.1f}s)")
        else:
            lines.append(f"{head} {segment.text}")
            if show_roman and segment.roman:
                lines.append(f"{' ' * (len(head) - 1)}  ({segment.roman})")
    return "\n".join(lines) + "\n"


def to_json(result: LessonResult, indent: int = 2) -> str:
    return json.dumps(result.to_dict(), indent=indent, ensure_ascii=False)


def to_srt(result: LessonResult) -> str:
    """Subtitles, so you can play the lesson back with the sargam on screen."""
    blocks: list[str] = []
    for i, segment in enumerate(result.segments, start=1):
        body = segment.sargam if segment.is_sung else segment.text
        if not body:
            continue
        who = f"{segment.speaker}: " if segment.speaker else ""
        blocks.append(
            f"{i}\n"
            f"{_fmt_srt_ts(segment.start)} --> {_fmt_srt_ts(segment.end)}\n"
            f"{who}{body}\n"
        )
    return "\n".join(blocks)


def to_practice_sheet(result: LessonResult) -> str:
    """Markdown you can practise from: tonic, scale, demos, drills, glossary."""
    out: list[str] = []
    out.append(f"# Lesson notes — {result.source.rsplit('/', 1)[-1]}")
    out.append("")
    out.extend(_summary_block(result))
    out.extend(_demonstration_block(result))
    out.extend(_drill_block(result))
    out.extend(_glossary_block(result))
    out.extend(_transcript_block(result))
    return "\n".join(out) + "\n"


def _summary_block(result: LessonResult) -> list[str]:
    total = result.sung_seconds + result.spoken_seconds
    lines = ["## At a glance", ""]
    lines.append(f"- **Sa (tonic):** {result.tonic.western} — {result.tonic.hz:.1f} Hz"
                 + (f" · detector confidence {result.tonic.confidence:.0%}"
                    if result.tonic.confidence < 1.0 else " · set by you"))
    lines.append(f"- **Scale:** {result.scale.summary()}")

    named = result.mentions.get("ragas", [])
    if named:
        display = ", ".join(lexicon.iast_display(n) for n in named)
        lines.append(f"- **Raags named out loud:** {display}")
        agreement = _scale_agreement(result)
        if agreement:
            lines.append(f"- **Cross-check:** {agreement}")
    if result.mentions.get("talas"):
        display = ", ".join(
            lexicon.iast_display(t) for t in result.mentions["talas"]
        )
        lines.append(f"- **Taals named:** {display}")
    if total > 0:
        lines.append(
            f"- **Time:** {_fmt_ts(result.sung_seconds)} sung, "
            f"{_fmt_ts(result.spoken_seconds)} spoken"
        )
    lines.append("")
    return lines


def _scale_agreement(result: LessonResult) -> str:
    """Does the pitch evidence agree with the raag the guru named?"""
    from .raga import thaat_of_raga

    named = result.mentions.get("ragas", [])
    if not named or not result.scale.swaras:
        return ""
    if result.scale.exact_ragas:
        for name in named:
            if name in result.scale.exact_ragas:
                return f"the sung notes match {name} exactly"
    candidates = result.scale.thaats or ((result.scale.thaat,) if result.scale.thaat else ())
    if candidates:
        for name in named:
            if thaat_of_raga(name) in candidates:
                return (
                    f"the sung notes fit {thaat_of_raga(name)} thaat, "
                    f"which is where {name} lives — consistent"
                )
        fits = " or ".join(candidates)
        return (
            f"the sung notes fit {fits} thaat, but {named[0]} does not sit "
            f"there — either something else was sung here, or Sa is off "
            f"(re-run with --tonic)"
        )
    return ""


def _demonstration_block(result: LessonResult) -> list[str]:
    demos = [s for s in result.segments if s.kind == DEMONSTRATION and s.sargam]
    if not demos:
        return []
    lines = ["## Demonstrations to copy", ""]
    tala = _mentioned_tala(result)
    for segment in demos:
        who = f"{segment.speaker} · " if segment.speaker else ""
        lines.append(
            f"- **{_fmt_ts(segment.start)}** ({who}{segment.duration:.0f}s) "
            f"`{segment.sargam}`"
        )
        detail = _shruti_note(segment)
        if detail:
            lines.append(f"  - {detail}")
        # A phrase with a steady pulse gets the notebook treatment: one cell
        # per matra, sustain dashes, vibhag bars. An alaap gets none, because
        # laying an unmetered line on a grid would be inventing rhythm.
        pulse = rhythm.detect_pulse(segment.notes)
        if pulse is not None:
            lines.append(f"  - {rhythm.describe(pulse, tala)}")
            for row in rhythm.to_matra_grid(
                segment.notes, pulse, tala, style=result.notation
            ):
                lines.append(f"    `{row}`")
    lines.append("")
    return lines


def _mentioned_tala(result: LessonResult) -> str | None:
    """The tala to group matra grids by — only if exactly one was named."""
    named = [t for t in result.mentions.get("talas", []) if t in rhythm.TALAS]
    return named[0] if len(named) == 1 else None


def _shruti_note(segment: LessonSegment, threshold: float = 20.0) -> str:
    """Call out swaras held noticeably off equal temperament.

    This is not a mistake report — a komal Ga sung 30 cents flat is usually the
    raag being sung correctly, and it is exactly the detail that a student
    cannot hear yet but can be shown.
    """
    from .swara import SWARA_FULL

    interesting = [
        n for n in segment.notes
        if n.duration >= 0.4 and abs(n.deviation) >= threshold
    ]
    if not interesting:
        return ""
    parts = [
        f"{SWARA_FULL[n.swara]} {n.deviation:+.0f}c"
        for n in sorted(interesting, key=lambda n: -n.duration)[:3]
    ]
    return "held off equal temperament: " + ", ".join(parts)


def _drill_block(result: LessonResult, gap: float = 6.0) -> list[str]:
    """Guru sings, you sing it back: the call-and-response pairs in the lesson."""
    pairs: list[tuple[LessonSegment, LessonSegment]] = []
    for i, segment in enumerate(result.segments[:-1]):
        if segment.kind != DEMONSTRATION:
            continue
        for follower in result.segments[i + 1:]:
            if follower.start - segment.end > gap:
                break
            if follower.kind == ATTEMPT:
                pairs.append((segment, follower))
                break
    if not pairs:
        return []

    lines = ["## Call and response", "",
             "Places where a demonstration is followed by your attempt — the "
             "fastest parts of the recording to A/B.", ""]
    for call, response in pairs:
        lines.append(
            f"- **{_fmt_ts(call.start)}** guru `{call.sargam}` → "
            f"**{_fmt_ts(response.start)}** you `{response.sargam}`"
        )
    lines.append("")
    return lines


def _glossary_block(result: LessonResult) -> list[str]:
    terms = [t for t in result.mentions.get("terms", []) if lexicon.gloss_for(t)]
    if not terms:
        return []
    lines = ["## Terms used in this lesson", ""]
    for term in sorted(terms):
        lines.append(
            f"- **{lexicon.iast_display(term)}** — {lexicon.gloss_for(term)}"
        )
    lines.append("")
    return lines


def _transcript_block(result: LessonResult) -> list[str]:
    lines = ["## Transcript", ""]
    for segment in result.segments:
        stamp = _fmt_ts(segment.start)
        who = segment.speaker or ""
        if segment.is_sung:
            label = "sings back" if segment.kind == ATTEMPT else "sings"
            lines.append(f"**{stamp}** {who} *{label}* — `{segment.sargam}`")
        else:
            lines.append(f"**{stamp}** {who}: {segment.text}")
            if segment.roman:
                lines.append(f"> {segment.roman}")
        lines.append("")
    return lines


def render(result: LessonResult, fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "txt":
        return to_text(result)
    if fmt == "json":
        return to_json(result)
    if fmt == "srt":
        return to_srt(result)
    if fmt in ("md", "markdown", "practice"):
        return to_practice_sheet(result)
    raise ValueError(f"Unknown output format: {fmt!r} (use txt/json/srt/md)")
