#!/usr/bin/env python3
"""
JobApply CLI — Automated job discovery, resume tailoring, and application.

Usage:
  python main.py run              # Full pipeline: discover + tailor + fill forms
  python main.py discover         # Only discover and score jobs
  python main.py tailor           # Tailor resumes for already-discovered jobs
  python main.py status           # Show application tracker dashboard
  python main.py setup-profile    # Set up your profile from LinkedIn or manually
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import typer
from rich.console import Console
from rich.panel import Panel

load_dotenv()

# Validate API key early
if not os.getenv("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
    sys.exit(1)

app = typer.Typer(help="Automated job application agent for robotics/ADAS roles")
console = Console()


def _load_env_config() -> dict:
    return {
        "location": os.getenv("TARGET_LOCATION", "San Francisco Bay Area"),
        "min_score": float(os.getenv("MIN_MATCH_SCORE", "70")),
        "max_jobs": int(os.getenv("MAX_JOBS_PER_RUN", "10")),
        "human_review": os.getenv("HUMAN_REVIEW", "true").lower() == "true",
        "dry_run": os.getenv("DRY_RUN", "true").lower() == "true",
        "target_roles": [r.strip() for r in os.getenv("TARGET_ROLES", "Robotics Software Engineer").split(",")],
    }


@app.command()
def setup_profile(
    linkedin_url: str = typer.Option(None, "--linkedin", "-l", help="LinkedIn profile URL"),
    resume_file: str = typer.Option(None, "--resume", "-r", help="Path to existing resume (.docx or .pdf)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing profile"),
):
    """Set up your profile from LinkedIn URL or existing resume."""
    from core.profile import PROFILE_PATH, load_profile, save_profile
    from core.profile import extract_profile_from_linkedin, create_profile_interactively

    if PROFILE_PATH.exists() and not force:
        console.print(f"[yellow]Profile already exists at {PROFILE_PATH}[/yellow]")
        console.print("Use --force to overwrite, or run `python main.py status` to see it.")
        return

    url = linkedin_url or os.getenv("LINKEDIN_URL", "")

    if resume_file:
        console.print(f"[cyan]Extracting profile from resume: {resume_file}[/cyan]")
        from core.resume_parser import parse_resume_file
        profile = parse_resume_file(resume_file)
    elif url:
        console.print(f"[cyan]Extracting profile from LinkedIn: {url}[/cyan]")
        profile = extract_profile_from_linkedin(url)
    else:
        console.print("[yellow]No LinkedIn URL or resume provided. Using interactive setup.[/yellow]")
        profile = create_profile_interactively()

    console.print(f"\n[bold]Profile extracted:[/bold]")
    console.print(f"  Name: {profile.name}")
    console.print(f"  Title: {profile.current_title}")
    console.print(f"  Skills: {', '.join(profile.skills[:8])}...")
    console.print(f"  Experience: {len(profile.experience)} roles")

    save_profile(profile)
    console.print("\n[green]Profile saved! Run `python main.py discover` to find jobs.[/green]")


@app.command()
def discover(
    max_jobs: int = typer.Option(None, "--max", "-n", help="Max jobs to return"),
    min_score: float = typer.Option(None, "--score", "-s", help="Minimum match score (0-100)"),
    location: str = typer.Option(None, "--location", help="Override job search location"),
):
    """Discover and score jobs matching your profile."""
    from core.profile import load_profile
    from core.tracker import add_or_update
    from core.models import ApplicationRecord, ApplicationStatus
    from agents.agent1_discovery import run_discovery

    cfg = _load_env_config()
    profile = load_profile()

    jobs = run_discovery(
        profile=profile,
        search_queries=cfg["target_roles"],
        location=location or cfg["location"],
        min_score=min_score or cfg["min_score"],
        max_results=max_jobs or cfg["max_jobs"],
    )

    # Save to tracker
    for job in jobs:
        record = ApplicationRecord(job=job, status=ApplicationStatus.SCORED)
        add_or_update(record)

    console.print(f"\n[green]Saved {len(jobs)} jobs to tracker.[/green]")
    console.print("Run `python main.py tailor` to generate tailored resumes.")


@app.command()
def tailor(
    job_id: str = typer.Option(None, "--job-id", help="Tailor resume for specific job ID only"),
    with_cover_letter: bool = typer.Option(False, "--with-cover-letter", "-cl",
                                           help="Also generate a cover letter PDF for each job"),
):
    """Tailor resumes for discovered jobs. Resume only by default.

    Examples:
      python main.py tailor                     # resume PDFs only
      python main.py tailor --with-cover-letter # resume + cover letter PDFs
      python main.py tailor --job-id abc123 --with-cover-letter
    """
    from core.profile import load_profile
    from core.tracker import add_or_update, get_all_by_status, get_record
    from core.models import ApplicationStatus
    from agents.agent2_tailor import run_tailoring

    profile = load_profile()

    if job_id:
        record = get_record(job_id)
        if not record:
            console.print(f"[red]Job ID {job_id} not found in tracker.[/red]")
            return
        jobs_to_process = [record]
    else:
        jobs_to_process = get_all_by_status(ApplicationStatus.SCORED)

    if not jobs_to_process:
        console.print("[yellow]No jobs in SCORED status. Run `discover` first.[/yellow]")
        return

    mode = "resume + cover letter" if with_cover_letter else "resume only"
    console.print(f"\nTailoring {len(jobs_to_process)} jobs ({mode})...\n")

    for record in jobs_to_process:
        tailored = run_tailoring(profile, record.job, with_cover_letter=with_cover_letter)
        if tailored:
            record.resume = tailored
            record.status = ApplicationStatus.PDF_READY
        else:
            record.status = ApplicationStatus.ERROR
            record.error_message = "Resume tailoring failed"
        add_or_update(record)

    console.print("\n[green]Resume tailoring complete.[/green]")
    if with_cover_letter:
        console.print("[dim]Cover letters saved alongside resumes in output/pdfs/[/dim]")
    console.print("Run `python main.py apply` to fill out application forms.")


@app.command()
def apply(
    job_id: str = typer.Option(None, "--job-id", help="Apply to specific job ID only"),
    dry_run: bool = typer.Option(None, "--dry-run/--no-dry-run", help="Fill form but don't submit"),
):
    """Fill out and submit job applications."""
    from core.tracker import get_all_by_status, get_record, add_or_update
    from core.models import ApplicationStatus
    from agents.agent3_apply import run_application

    cfg = _load_env_config()
    is_dry_run = dry_run if dry_run is not None else cfg["dry_run"]

    if is_dry_run:
        console.print(Panel("[yellow]DRY RUN MODE — forms will be filled but NOT submitted[/yellow]"))

    if job_id:
        record = get_record(job_id)
        jobs_to_apply = [record] if record else []
    else:
        jobs_to_apply = get_all_by_status(ApplicationStatus.PDF_READY)

    if not jobs_to_apply:
        console.print("[yellow]No jobs with PDF_READY status. Run `tailor` first.[/yellow]")
        return

    console.print(f"\nApplying to {len(jobs_to_apply)} jobs...\n")

    for record in jobs_to_apply:
        result = run_application(record, dry_run=is_dry_run, human_review=cfg["human_review"])
        add_or_update(result)


@app.command("tailor-only")
def tailor_only(
    with_cover_letter: bool = typer.Option(False, "--with-cover-letter", "-cl"),
    url: str = typer.Option(None, "--url", "-u", help="Job posting URL (optional, for tracking)"),
    desc_file: str = typer.Option(None, "--desc-file", "-f", help="Path to .txt file with job description"),
):
    """Paste a job description and get a tailored resume PDF. No auto-apply.

    Three ways to provide the job description:
      1. Paste inline (default — just run the command, it will prompt you)
      2. From a file:  python main.py tailor-only --desc-file jd.txt
      3. With a URL:  python main.py tailor-only --url https://... --desc-file jd.txt

    Examples:
      python main.py tailor-only
      python main.py tailor-only --desc-file ~/nvidia_jd.txt
      python main.py tailor-only --url https://nvidia.wd5... --desc-file ~/nvidia_jd.txt
      python main.py tailor-only --desc-file ~/nvidia_jd.txt --with-cover-letter
    """
    import hashlib
    from core.profile import load_profile
    from core.tracker import add_or_update
    from core.models import JobPosting, ApplicationRecord, ApplicationStatus
    from agents.agent2_tailor import run_tailoring
    from agents.agent1_discovery import extract_job_meta, score_job, detect_ats_from_url

    profile = load_profile()

    # ── Step 1: Get job description ──────────────────────────────────────────
    description = ""

    if desc_file:
        from pathlib import Path as P
        p = P(desc_file)
        if not p.exists():
            console.print(f"[red]File not found: {desc_file}[/red]")
            raise typer.Exit(1)
        description = p.read_text(encoding="utf-8").strip()
        console.print(f"[green]Loaded {len(description)} chars from {desc_file}[/green]")
    else:
        console.print("\n[bold]Paste the job description below.[/bold]")
        console.print("[dim]Copy all text from the job posting page and paste it here.")
        console.print("Press Enter twice when done.[/dim]\n")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            description = "\n".join(lines[:-1]).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    if not description:
        console.print("[red]No job description provided.[/red]")
        raise typer.Exit(1)

    console.print(f"\n[dim]Got {len(description)} chars of job description[/dim]")

    # ── Step 2: Extract metadata ─────────────────────────────────────────────
    console.print("Extracting job details with Claude...")
    effective_url = url or f"manual://{hashlib.md5(description.encode()).hexdigest()[:8]}"
    meta = extract_job_meta(effective_url, description)

    console.print(f"  Company  : [cyan]{meta['company']}[/cyan]")
    console.print(f"  Title    : [cyan]{meta['title']}[/cyan]")
    console.print(f"  Location : {meta['location']}")

    # Let user confirm / correct
    console.print()
    confirmed_company = input(f"  Company name (Enter to keep '{meta['company']}'): ").strip()
    confirmed_title   = input(f"  Job title   (Enter to keep '{meta['title']}'): ").strip()
    if confirmed_company: meta["company"] = confirmed_company
    if confirmed_title:   meta["title"]   = confirmed_title

    # ── Step 3: Score against profile ────────────────────────────────────────
    score, reasons, ats, skip, _ = score_job(
        {"title": meta["title"], "company": meta["company"],
         "location": meta["location"], "description": description},
        profile,
    )
    console.print(f"\n  Match score: [bold]{score:.0f}/100[/bold]")
    for r in reasons[:3]:
        console.print(f"  [dim]- {r}[/dim]")

    # ── Step 4: Build job record ─────────────────────────────────────────────
    job_id = hashlib.md5(description[:200].encode()).hexdigest()[:12]
    job = JobPosting(
        id=job_id,
        title=meta["title"],
        company=meta["company"],
        location=meta["location"],
        url=effective_url,
        description=description,
        source="manual-paste",
        ats_platform=detect_ats_from_url(url) if url else "unknown",
        match_score=score,
        match_reasons=reasons,
    )

    # ── Step 5: Tailor resume ────────────────────────────────────────────────
    console.print(f"\nTailoring resume for [cyan]{meta['company']}[/cyan]...")
    tailored = run_tailoring(profile, job, with_cover_letter=with_cover_letter)

    if not tailored:
        console.print("[red]Resume tailoring failed.[/red]")
        raise typer.Exit(1)

    # ── Step 6: Save to tracker + show result ────────────────────────────────
    record = ApplicationRecord(
        job=job,
        resume=tailored,
        status=ApplicationStatus.PDF_READY,
        notes="Tailor-only — manual application",
    )
    add_or_update(record)

    console.print()
    console.print(f"[bold green]✓ Resume ready![/bold green]")
    console.print(f"  File    : [cyan]{tailored.filename}[/cyan]")
    console.print(f"  Location: output/pdfs/{tailored.filename}")
    console.print(f"  Keywords matched: {', '.join(tailored.keyword_matches[:6])}")
    if tailored.cover_letter_pdf_path:
        from pathlib import Path as P
        console.print(f"  Cover letter: {P(tailored.cover_letter_pdf_path).name}")
    console.print()
    console.print(f"[dim]Apply manually at: {url or 'the job posting URL'}[/dim]")
    console.print(f"[dim]Tracked in tracker as PDF_READY (job ID: {job_id})[/dim]")


@app.command("remove-job")
def remove_job(
    company: str = typer.Argument(..., help="Company name (partial match ok)"),
    reason: str = typer.Option("rejected", "--reason", "-r", help="Why removing: rejected/not-interested/applied-elsewhere"),
):
    """Remove a job from the tracker. Marks as skipped (keeps history).

    Examples:
      python main.py remove-job "Applied Intuition"
      python main.py remove-job "Applied" --reason rejected
    """
    from pathlib import Path
    from core.tracker import load_tracker, save_tracker
    from core.models import ApplicationStatus

    records = load_tracker()
    matches = [
        (jid, r) for jid, r in records.items()
        if company.lower() in r.job.company.lower()
    ]

    if not matches:
        console.print(f"[red]No job found matching '{company}'[/red]")
        return

    if len(matches) > 1:
        console.print(f"[yellow]Multiple matches:[/yellow]")
        for jid, r in matches:
            console.print(f"  [{jid}] {r.job.company} — {r.job.title}")
        console.print("Be more specific with the company name.")
        return

    jid, record = matches[0]
    record.status = ApplicationStatus.SKIPPED
    record.notes = f"Removed: {reason}"
    records[jid] = record
    save_tracker(records)
    console.print(f"[green]Removed:[/green] {record.job.company} — {record.job.title} ({reason})")

    # Auto-append to BLACKLISTED_JOBS in .env so it never appears in future discovery
    env_path = Path(".env")
    if env_path.exists() and reason in ("rejected", "not-interested"):
        env_text = env_path.read_text()
        entry = f"{record.job.company}::{record.job.title[:40]}"
        if "BLACKLISTED_JOBS=" in env_text:
            # Append to existing value
            import re
            def append_entry(m):
                existing = m.group(1).strip()
                new_val = f"{existing}|{entry}" if existing else entry
                return f"BLACKLISTED_JOBS={new_val}"
            env_text = re.sub(r"BLACKLISTED_JOBS=(.*)", append_entry, env_text)
        else:
            env_text += f"\nBLACKLISTED_JOBS={entry}\n"
        env_path.write_text(env_text)
        console.print(f"[dim]Added to BLACKLISTED_JOBS in .env — won't appear in future searches[/dim]")


@app.command("add-job")
def add_job(
    url: str = typer.Argument(..., help="Direct URL to a specific job posting"),
    with_cover_letter: bool = typer.Option(False, "--with-cover-letter", "-cl"),
    apply_now: bool = typer.Option(False, "--apply", help="Tailor + open form immediately after adding"),
    description_file: str = typer.Option(None, "--desc-file", "-f",
        help="Path to a .txt file containing the job description (use when auto-fetch fails)"),
):
    """Add a specific job URL directly, bypassing discovery.

    For sites like Workday that block automated fetching, copy the job
    description text, save it to a .txt file, and pass it with --desc-file.

    Examples:
      python main.py add-job https://nvidia.wd5.myworkdayjobs.com/...
      python main.py add-job https://... --desc-file nvidia_jd.txt
      python main.py add-job https://... --desc-file nvidia_jd.txt --apply
    """
    import hashlib
    from core.profile import load_profile
    from core.tracker import add_or_update, get_record
    from core.models import JobPosting, ApplicationRecord, ApplicationStatus
    from agents.agent1_discovery import fetch_job_description, score_job, detect_ats_from_url, extract_job_meta

    profile = load_profile()

    job_id = hashlib.md5(url.encode()).hexdigest()[:12]
    existing = get_record(job_id)
    if existing and not apply_now:
        console.print(f"[yellow]Already tracking: {existing.job.company} — {existing.job.title}[/yellow]")
        console.print(f"Status: {existing.status.value}  |  Job ID: {job_id}")
        return

    # ── Get job description ──────────────────────────────────────────────────
    description = ""

    if description_file:
        # User provided a file — read it directly
        from pathlib import Path
        desc_path = Path(description_file)
        if not desc_path.exists():
            console.print(f"[red]File not found: {description_file}[/red]")
            raise typer.Exit(1)
        description = desc_path.read_text(encoding="utf-8").strip()
        console.print(f"[green]Loaded job description from {description_file} ({len(description)} chars)[/green]")
    else:
        # Try auto-fetch
        console.print(f"\n[cyan]Fetching job details from URL...[/cyan]")
        description = fetch_job_description(url)

    if not description:
        # Auto-fetch failed — prompt user to paste it
        console.print(f"\n[yellow]Could not auto-fetch the job description.[/yellow]")
        console.print("[dim]This happens with Workday, iCIMS, and other JS-heavy sites.[/dim]")
        console.print("\n[bold]Option 1 (recommended):[/bold]")
        console.print("  1. Open the job URL in your browser")
        console.print("  2. Select all text on the page (Ctrl+A), copy it (Ctrl+C)")
        console.print(f"  3. Paste into a file:  nano jd.txt  then paste, save")
        console.print(f"  4. Rerun: python main.py add-job '{url}' --desc-file jd.txt")
        console.print("\n[bold]Option 2 — paste inline now:[/bold]")
        console.print("[dim]Paste the job description below. Press Enter twice when done.[/dim]")

        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            description = "\n".join(lines[:-1]).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    if not description:
        console.print("[red]No job description provided. Cannot continue.[/red]")
        raise typer.Exit(1)

    # ── Extract metadata & score ─────────────────────────────────────────────
    meta = extract_job_meta(url, description)
    console.print(f"  Company : {meta['company']}")
    console.print(f"  Title   : {meta['title']}")
    console.print(f"  ATS     : {meta['ats']}")

    console.print("  Scoring match against your profile...")
    score, reasons, ats, skip, skip_reason = score_job(
        {"title": meta["title"], "company": meta["company"],
         "location": meta["location"], "description": description},
        profile,
    )
    console.print(f"  Match score: [bold]{score:.0f}/100[/bold]")
    for r in reasons:
        console.print(f"    [dim]- {r}[/dim]")

    job = JobPosting(
        id=job_id,
        title=meta["title"],
        company=meta["company"],
        location=meta["location"],
        url=url,
        description=description,
        source="manual",
        ats_platform=meta["ats"],
        match_score=score,
        match_reasons=reasons,
    )
    record = ApplicationRecord(job=job, status=ApplicationStatus.SCORED)
    add_or_update(record)
    console.print(f"\n[green]Job added to tracker.  ID: {job_id}[/green]")

    if apply_now:
        console.print("\n[cyan]Tailoring resume...[/cyan]")
        from agents.agent2_tailor import run_tailoring
        tailored = run_tailoring(profile, job, with_cover_letter=with_cover_letter)
        if tailored:
            record.resume = tailored
            record.status = ApplicationStatus.PDF_READY
            add_or_update(record)
            console.print(f"\n[green]Resume ready: {tailored.filename}[/green]")
            console.print("Run `python main.py apply` when ready to fill the form.")
        else:
            console.print("[red]Resume tailoring failed.[/red]")
    else:
        console.print(f"\nNext steps:")
        console.print(f"  Tailor resume : python main.py tailor --job-id {job_id}")
        console.print(f"  Or do it now  : python main.py add-job '{url}' --apply")


@app.command()
def run(
    max_jobs: int = typer.Option(None, "--max", "-n"),
    dry_run: bool = typer.Option(None, "--dry-run/--no-dry-run"),
):
    """Full pipeline: discover → tailor → apply."""
    console.print(Panel("[bold cyan]JobApply — Full Pipeline[/bold cyan]\nDiscover → Tailor → Apply"))
    discover(max_jobs=max_jobs)
    tailor()
    apply(dry_run=dry_run)


@app.command()
def status():
    """Show application tracker dashboard."""
    from core.tracker import print_summary
    print_summary()


@app.command("edit-profile")
def edit_profile():
    """Open profile JSON in editor for manual edits."""
    from core.profile import PROFILE_PATH
    import subprocess
    editor = os.getenv("EDITOR", "nano")
    subprocess.run([editor, str(PROFILE_PATH)])


if __name__ == "__main__":
    app()
