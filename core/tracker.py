import json
import os
from datetime import datetime
from pathlib import Path
from core.models import ApplicationRecord, ApplicationStatus


TRACKER_FILE = Path("output/applications.json")


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


def load_tracker() -> dict[str, ApplicationRecord]:
    if not TRACKER_FILE.exists():
        return {}
    with open(TRACKER_FILE) as f:
        raw = json.load(f)
    records = {}
    for job_id, data in raw.items():
        try:
            records[job_id] = ApplicationRecord.model_validate(data)
        except Exception:
            pass
    return records


def save_tracker(records: dict[str, ApplicationRecord]):
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for job_id, record in records.items():
        data[job_id] = json.loads(record.model_dump_json())
    with open(TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2, default=_serialize)


def add_or_update(record: ApplicationRecord):
    records = load_tracker()
    records[record.job.id] = record
    save_tracker(records)


def get_record(job_id: str) -> ApplicationRecord | None:
    records = load_tracker()
    return records.get(job_id)


def get_all_by_status(status: ApplicationStatus) -> list[ApplicationRecord]:
    records = load_tracker()
    return [r for r in records.values() if r.status == status]


def print_summary():
    from rich.table import Table
    from rich.console import Console
    console = Console()
    records = load_tracker()

    table = Table(title="Application Tracker", show_header=True)
    table.add_column("Company", style="cyan")
    table.add_column("Role", style="white")
    table.add_column("Score", style="yellow", justify="right")
    table.add_column("Status", style="green")
    table.add_column("PDF", style="dim")

    status_colors = {
        "submitted": "green",
        "awaiting_review": "yellow",
        "resume_tailored": "cyan",
        "error": "red",
        "skipped": "dim",
    }

    for record in sorted(records.values(), key=lambda r: r.job.match_score or 0, reverse=True):
        score = f"{record.job.match_score:.0f}" if record.job.match_score else "-"
        status = record.status.value
        color = status_colors.get(status, "white")
        pdf = record.resume.filename if record.resume else "-"
        table.add_row(
            record.job.company,
            record.job.title[:45],
            score,
            f"[{color}]{status}[/{color}]",
            pdf
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(records)} applications tracked[/dim]")
