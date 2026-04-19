"""
Smart job recommendations engine for Applymatic.

Handles:
1. Rejection tracking + reapplication cooldown enforcement
2. User preferences (manual vs daily auto-recommend + auto-apply)
3. Login-time recommendations
4. Autonomous application with user consent
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

# ── Cooldown rules (based on research) ───────────────────────────────────────
# Same role, same company: 6 months minimum
# Different role, same company: 3 months minimum
# ATS rejection (no human review): 1 month minimum
COOLDOWN_SAME_ROLE_DAYS = 180      # 6 months
COOLDOWN_DIFF_ROLE_DAYS = 90       # 3 months
COOLDOWN_ATS_REJECTION_DAYS = 30   # 1 month (likely just ATS filter)

PREFS_FILE = Path("config/user_prefs.json")
REJECTIONS_FILE = Path("config/rejections.json")


# ── User preferences ──────────────────────────────────────────────────────────

@dataclass
class UserPreferences:
    # Recommendation mode
    recommend_mode: str = "on_request"  # "on_request" | "daily"
    recommend_time: str = "09:00"       # time of day for daily recommendations (HH:MM)

    # Auto-apply mode
    auto_apply: bool = False            # if True, apply without asking
    auto_apply_min_score: float = 85.0  # only auto-apply if score >= this
    auto_apply_limit_per_day: int = 5   # max auto-applies per day
    
    # Filters always applied
    excluded_companies: list = None     # companies to never apply to
    excluded_keywords: list = None      # job title keywords to skip
    
    # Notification
    notify_on_new_jobs: bool = True
    
    def __post_init__(self):
        if self.excluded_companies is None:
            self.excluded_companies = []
        if self.excluded_keywords is None:
            self.excluded_keywords = []


def load_prefs() -> UserPreferences:
    if PREFS_FILE.exists():
        data = json.loads(PREFS_FILE.read_text())
        return UserPreferences(**data)
    return UserPreferences()


def save_prefs(prefs: UserPreferences):
    PREFS_FILE.parent.mkdir(exist_ok=True)
    PREFS_FILE.write_text(json.dumps(asdict(prefs), indent=2))


# ── Rejection tracking ────────────────────────────────────────────────────────

@dataclass
class RejectionRecord:
    company: str
    role_title: str
    role_category: str          # e.g. "motion planning", "robotics"
    rejected_at: str            # ISO date string
    rejection_stage: str        # "ats" | "screening" | "interview" | "offer"
    job_url: str = ""
    notes: str = ""


def load_rejections() -> list[RejectionRecord]:
    if REJECTIONS_FILE.exists():
        data = json.loads(REJECTIONS_FILE.read_text())
        return [RejectionRecord(**r) for r in data]
    return []


def save_rejection(record: RejectionRecord):
    rejections = load_rejections()
    rejections.append(record)
    REJECTIONS_FILE.parent.mkdir(exist_ok=True)
    REJECTIONS_FILE.write_text(json.dumps([asdict(r) for r in rejections], indent=2))


def mark_rejected(job_id: str, stage: str = "unknown", notes: str = ""):
    """Mark a tracked job as rejected and save to rejections log."""
    try:
        from core.tracker import load_tracker, add_or_update
        from core.models import ApplicationStatus
        records = load_tracker()
        record = records.get(job_id)
        if not record:
            return None

        # Update tracker status
        record.status = ApplicationStatus.REJECTED
        add_or_update(record)

        # Save to rejections log
        rejection = RejectionRecord(
            company=record.job.company,
            role_title=record.job.title,
            role_category=_categorize_role(record.job.title),
            rejected_at=datetime.now().isoformat(),
            rejection_stage=stage,
            job_url=record.job.url,
            notes=notes,
        )
        save_rejection(rejection)
        return rejection
    except Exception as e:
        print(f"Error marking rejection: {e}")
        return None


def _categorize_role(title: str) -> str:
    """Rough category for a job title for cooldown matching."""
    title_lower = title.lower()
    if any(k in title_lower for k in ["motion plan", "path plan", "trajectory"]):
        return "motion_planning"
    if any(k in title_lower for k in ["adas", "autonomous", "self-driving", "av "]):
        return "autonomous_vehicles"
    if any(k in title_lower for k in ["robotics", "robot"]):
        return "robotics"
    if any(k in title_lower for k in ["perception", "computer vision", "lidar"]):
        return "perception"
    if any(k in title_lower for k in ["controls", "control system"]):
        return "controls"
    return "software_engineering"


# ── Cooldown check ────────────────────────────────────────────────────────────

def check_reapplication_eligibility(
    company: str,
    job_title: str,
    job_url: str = "",
) -> dict:
    """
    Check if it's OK to apply to this job given rejection history.
    
    Returns:
        {
            "can_apply": bool,
            "reason": str,
            "days_remaining": int | None,
            "eligible_date": str | None,
            "similar_rejections": list
        }
    """
    rejections = load_rejections()
    company_lower = company.lower().strip()
    new_category = _categorize_role(job_title)

    similar = []
    for r in rejections:
        if r.company.lower().strip() != company_lower:
            continue

        rejected_at = datetime.fromisoformat(r.rejected_at)
        days_since = (datetime.now() - rejected_at).days
        same_role = r.role_category == new_category

        # Determine cooldown
        if r.rejection_stage == "ats":
            cooldown = COOLDOWN_ATS_REJECTION_DAYS
            cooldown_name = "1 month (ATS rejection)"
        elif same_role:
            cooldown = COOLDOWN_SAME_ROLE_DAYS
            cooldown_name = "6 months (same role type)"
        else:
            cooldown = COOLDOWN_DIFF_ROLE_DAYS
            cooldown_name = "3 months (different role, same company)"

        days_remaining = cooldown - days_since
        eligible_date = (rejected_at + timedelta(days=cooldown)).strftime("%B %d, %Y")

        similar.append({
            "role": r.role_title,
            "rejected_at": r.rejected_at[:10],
            "stage": r.rejection_stage,
            "days_since": days_since,
            "cooldown_days": cooldown,
            "days_remaining": max(0, days_remaining),
            "eligible_date": eligible_date,
            "cooldown_name": cooldown_name,
        })

    if not similar:
        return {
            "can_apply": True,
            "reason": "No previous rejections at this company.",
            "days_remaining": None,
            "eligible_date": None,
            "similar_rejections": [],
        }

    # Find the most restrictive active cooldown
    blocking = [s for s in similar if s["days_remaining"] > 0]

    if not blocking:
        return {
            "can_apply": True,
            "reason": f"Cooldown period has passed. You previously applied to {len(similar)} role(s) here.",
            "days_remaining": None,
            "eligible_date": None,
            "similar_rejections": similar,
        }

    most_restrictive = max(blocking, key=lambda x: x["days_remaining"])
    return {
        "can_apply": False,
        "reason": (
            f"You were rejected from {company} {most_restrictive['days_since']} days ago "
            f"({most_restrictive['role']}, {most_restrictive['stage']} stage). "
            f"Recommended wait: {most_restrictive['cooldown_name']}."
        ),
        "days_remaining": most_restrictive["days_remaining"],
        "eligible_date": most_restrictive["eligible_date"],
        "similar_rejections": similar,
    }


# ── Login recommendations ─────────────────────────────────────────────────────

def get_login_recommendations(max_jobs: int = 5) -> dict:
    """
    Called on login. Returns:
    - New jobs to review
    - Jobs ready to apply (resume tailored, not yet submitted)
    - Rejections that have passed cooldown (can reapply)
    - User's preference summary
    """
    try:
        from core.tracker import load_tracker
        records = load_tracker()
        prefs = load_prefs()

        ready_to_apply = []
        pending_tailor = []
        reapply_eligible = []

        for jid, record in records.items():
            status = record.status.value if hasattr(record.status, 'value') else str(record.status)

            if status == "pdf_ready":
                ready_to_apply.append({
                    "id": jid,
                    "company": record.job.company,
                    "title": record.job.title,
                    "score": record.job.match_score,
                })
            elif status == "scored":
                pending_tailor.append({
                    "id": jid,
                    "company": record.job.company,
                    "title": record.job.title,
                    "score": record.job.match_score,
                })

        # Check if any rejections are now eligible for reapplication
        rejections = load_rejections()
        for r in rejections:
            eligibility = check_reapplication_eligibility(r.company, r.role_title)
            if eligibility["can_apply"] and not eligibility["similar_rejections"]:
                continue
            if eligibility["can_apply"]:
                reapply_eligible.append({
                    "company": r.company,
                    "original_role": r.role_title,
                    "rejected_at": r.rejected_at[:10],
                    "suggestion": f"Consider reapplying to {r.company} — cooldown has passed.",
                })

        return {
            "ready_to_apply": sorted(ready_to_apply, key=lambda x: x["score"] or 0, reverse=True)[:max_jobs],
            "pending_tailor": sorted(pending_tailor, key=lambda x: x["score"] or 0, reverse=True)[:max_jobs],
            "reapply_eligible": reapply_eligible[:3],
            "preferences": {
                "recommend_mode": prefs.recommend_mode,
                "auto_apply": prefs.auto_apply,
                "auto_apply_min_score": prefs.auto_apply_min_score,
            }
        }
    except Exception as e:
        return {"error": str(e)}


def format_login_message(recommendations: dict, user_name: str = "") -> str:
    """Format the login recommendation as a chat message."""
    lines = []
    first = user_name.split()[0] if user_name else "there"
    lines.append(f"Welcome back{', ' + first if first != 'there' else ''}!\n")

    prefs = recommendations.get("preferences", {})
    mode = prefs.get("recommend_mode", "on_request")
    auto = prefs.get("auto_apply", False)

    # Status summary
    ready = recommendations.get("ready_to_apply", [])
    pending = recommendations.get("pending_tailor", [])
    reapply = recommendations.get("reapply_eligible", [])

    if ready:
        lines.append(f"**{len(ready)} jobs ready to apply** (resumes tailored):")
        for j in ready:
            lines.append(f"  • {j['company']} — {j['title']} (score: {j['score']:.0f})")

    if pending:
        lines.append(f"\n**{len(pending)} jobs need resume tailoring**:")
        for j in pending[:3]:
            lines.append(f"  • {j['company']} — {j['title']} (score: {j['score']:.0f})")

    if reapply:
        lines.append(f"\n**{len(reapply)} companies you can reapply to** (cooldown passed):")
        for r in reapply:
            lines.append(f"  • {r['company']} (previously applied to: {r['original_role']})")

    if not ready and not pending and not reapply:
        lines.append("No pending actions. Say 'find me jobs' to discover new opportunities.")

    # Preference reminder
    if mode == "daily" and auto:
        lines.append(f"\n_Auto-apply is ON for jobs scoring {prefs.get('auto_apply_min_score', 85)}+._")
    elif mode == "daily":
        lines.append("\n_Daily recommendations are ON. I'll suggest new jobs each morning._")
    else:
        lines.append("\n_Recommendations are on-request. Say 'find me jobs' anytime._")

    lines.append("\nWhat would you like to do?")
    return "\n".join(lines)
