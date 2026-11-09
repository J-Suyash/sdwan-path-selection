"""Export the project conversation and documents into a zip.

Reads Codex session rollouts (JSONL), keeps user messages and assistant
replies (marking progress notes), drops tool/system noise, and packages
the transcript with the project documents.
"""

import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/home/sxtr/Projects/Major Project")
SESSIONS = Path("/home/sxtr/.codex/sessions")
OUT_DIR = ROOT / "Exports" / "Major_Project_Chat_and_Docs_2026-11-03"
ZIP_PATH = ROOT / "Exports" / "Major_Project_Chat_and_Docs_2026-11-03.zip"

THREADS = [
    (
        "Part 1 - Proposal, environment, data and first results",
        SESSIONS
        / "2026/10/31/rollout-2026-10-31T21-54-54-01a192c7-40ce-7d13-b220-e091aa35509e.jsonl",
    ),
    (
        "Part 2 - Base-paper pivot, reproducibility check and Review 0",
        SESSIONS
        / "2026/11/03/rollout-2026-11-03T18-18-23-01a1a174-1a42-7452-b59d-19ea1e315726.jsonl",
    ),
    (
        "Part 3 - Technical Q&A for the review",
        SESSIONS
        / "2026/11/03/rollout-2026-11-03T19-19-49-01a1a1ac-5872-7d91-a834-2246969aca04.jsonl",
    ),
]

CONTEXT_TAGS = (
    "<environment_context>",
    "<codex_apps_client_time_context>",
    "<skills_instructions>",
    "<collaboration_mode>",
    "<model_switch>",
    "<app-context>",
    "<user_instructions>",
)


def is_context(text: str) -> bool:
    text = text.lstrip()
    return any(text.startswith(tag) for tag in CONTEXT_TAGS)


def message_text(payload: dict) -> str:
    parts = []
    for item in payload.get("content", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()


def thread_messages(path: Path) -> list[dict]:
    messages = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "response_item":
                continue
            payload = entry.get("payload", {})
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            text = message_text(payload)
            if not text:
                continue
            if role == "user" and is_context(text):
                continue
            messages.append(
                {
                    "timestamp": entry.get("timestamp", ""),
                    "role": role,
                    "phase": payload.get("phase"),
                    "text": text,
                }
            )
    return messages


def build_transcript() -> tuple[str, dict]:
    lines = [
        "# Major Project - Complete Chat Export",
        "",
        "AI-Driven SD-WAN Path Selection for Enterprise",
        "",
        f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "This transcript reconstructs the project conversation from the",
        "Codex session logs. User messages and assistant replies are",
        "included verbatim. Assistant progress notes are labelled",
        "'working note'; tool calls, terminal output, system prompts and",
        "environment-injection messages are omitted.",
        "",
        "---",
        "",
    ]
    counts = {}
    for title, path in THREADS:
        if not path.exists():
            lines += [f"## {title}", "", f"(session log not found: {path})", ""]
            continue
        messages = thread_messages(path)
        counts[title] = len(messages)
        lines += [f"# {title}", "", f"Session: `{path.name}`", ""]
        for msg in messages:
            stamp = msg["timestamp"].replace("T", " ").replace("Z", " UTC")
            if msg["role"] == "user":
                lines += [f"## User - {stamp}", "", msg["text"], ""]
            else:
                phase = "working note" if msg["phase"] == "commentary" else "reply"
                lines += [f"## Assistant ({phase}) - {stamp}", "", msg["text"], ""]
        lines += ["---", ""]
    return "\n".join(lines), counts


def copy_tree(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    transcript, counts = build_transcript()
    (OUT_DIR / "00_Chat_Transcript.md").write_text(transcript, encoding="utf-8")

    docs = OUT_DIR / "01_Original_Documents"
    docs.mkdir()
    for name in os.listdir(ROOT / "Docs"):
        src = ROOT / "Docs" / name
        if src.is_file():
            shutil.copy2(src, docs / name)

    notes = OUT_DIR / "02_Working_Notes"
    notes.mkdir()
    copy_tree(ROOT / "docs", notes / "docs")
    copy_tree(ROOT / "paper", notes / "paper")
    copy_tree(ROOT / "analysis", notes / "analysis")
    for name in ("README.md", "configs/config.yaml", "data/README.md", "env/README.md"):
        src = ROOT / name
        if src.exists():
            target = notes / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    manifest = [
        "# Export manifest",
        "",
        f"Created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Chat transcript",
        "",
        "- 00_Chat_Transcript.md - complete three-part conversation",
    ]
    for title, count in counts.items():
        manifest.append(f"  - {title}: {count} messages")
    manifest += [
        "",
        "## Original documents (01_Original_Documents)",
        "- Detailed Proposal and Plan (docx)",
        "- Review 0 (docx, v2)",
        "- Review 0 deck (pptx)",
        "- Base Paper.pdf (note: this file is Botta et al. 2024)",
        "",
        "## Working notes (02_Working_Notes)",
        "- Review 0 rubric-aligned brief",
        "- Environment and infrastructure notes",
        "- Bista 2026 reproducibility verification",
        "- Lab notebook and baseline/offline results",
        "- README and configuration",
        "",
        "Datasets, trained models, virtual environments and caches are",
        "not included to keep the archive small.",
        "",
    ]
    (OUT_DIR / "MANIFEST.md").write_text("\n".join(manifest), encoding="utf-8")

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, _, files in os.walk(OUT_DIR):
            for name in files:
                full = Path(folder) / name
                zf.write(full, full.relative_to(OUT_DIR.parent))

    size_mb = ZIP_PATH.stat().st_size / 1e6
    print(f"transcript: {len(transcript):,} chars")
    for title, count in counts.items():
        print(f"  {title}: {count} messages")
    print(f"zip: {ZIP_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
