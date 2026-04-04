"""Lever ATS form filler."""
from playwright.sync_api import Page
from core.models import ApplicationRecord
from rich.console import Console

console = Console()


def fill_lever_form(page: Page, record: ApplicationRecord) -> bool:
    from core.profile import load_profile
    profile = load_profile()
    resume = record.resume
    job = record.job

    console.print("  [cyan]Lever adapter active[/cyan]")

    try:
        name_parts = profile.name.split(" ", 1)

        _fill(page, "input[name='name']", profile.name)
        _fill(page, "input[name='email']", profile.email)
        _fill(page, "input[name='phone']", profile.phone or "")
        _fill(page, "input[name='org']", "Amazon Robotics")  # Current company
        _fill(page, "input[name='urls[LinkedIn]']", profile.linkedin_url or "")
        _fill(page, "input[name='urls[GitHub]']", profile.github_url or "")

        if resume and resume.pdf_path:
            file_input = page.locator("input[type=file]").first
            if file_input.count() > 0:
                file_input.set_input_files(resume.pdf_path)
                console.print("  [green]✓[/green] Resume uploaded")

        cover = _build_cover_letter(profile, job)
        _fill(page, "textarea[name='comments']", cover)

        console.print("  [green]✓[/green] Lever form filled")
        return True

    except Exception as e:
        console.print(f"  [red]Lever fill error: {e}[/red]")
        return False


def _fill(page: Page, selector: str, value: str):
    if not value:
        return
    try:
        el = page.locator(selector).first
        if el.count() > 0:
            el.fill(value)
    except Exception:
        pass


def _build_cover_letter(profile, job) -> str:
    return f"""I'm excited to apply for the {job.title} role at {job.company}. With {profile.years_experience}+ years building production robotics and ADAS systems in C++, I'd love to contribute to your team.\n\n{profile.summary}\n\nBest,\n{profile.name}"""
