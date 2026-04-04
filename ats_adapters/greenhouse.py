"""Greenhouse ATS form filler."""
from playwright.sync_api import Page
from core.models import ApplicationRecord
from rich.console import Console

console = Console()


def fill_greenhouse_form(page: Page, record: ApplicationRecord) -> bool:
    job = record.job
    resume = record.resume
    profile_data = _get_profile_data(record)

    console.print("  [cyan]Greenhouse adapter active[/cyan]")

    try:
        # First name
        _fill_if_exists(page, "input#first_name", profile_data["first_name"])
        # Last name
        _fill_if_exists(page, "input#last_name", profile_data["last_name"])
        # Email
        _fill_if_exists(page, "input#email", profile_data["email"])
        # Phone
        _fill_if_exists(page, "input#phone", profile_data["phone"])
        # LinkedIn URL
        _fill_if_exists(page, "input[name*='linkedin']", profile_data["linkedin"])
        # Location / city
        _fill_if_exists(page, "input[name*='location']", profile_data["location"])

        # Resume upload
        if resume and resume.pdf_path:
            file_input = page.locator("input[type=file]").first
            if file_input:
                file_input.set_input_files(resume.pdf_path)
                console.print("  [green]✓[/green] Resume uploaded")

        # Cover letter (auto-generated)
        cover = _build_cover_letter(record)
        _fill_if_exists(page, "textarea[name*='cover']", cover)
        _fill_if_exists(page, "div[data-qa='cover-letter-text']", cover)

        console.print("  [green]✓[/green] Greenhouse form filled")
        return True

    except Exception as e:
        console.print(f"  [red]Greenhouse fill error: {e}[/red]")
        return False


def _fill_if_exists(page: Page, selector: str, value: str):
    if not value:
        return
    try:
        el = page.locator(selector).first
        if el.count() > 0:
            el.fill(value)
    except Exception:
        pass


def _get_profile_data(record: ApplicationRecord) -> dict:
    from core.profile import load_profile
    profile = load_profile()
    name_parts = profile.name.split(" ", 1)
    return {
        "first_name": name_parts[0],
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "email": profile.email,
        "phone": profile.phone or "",
        "linkedin": profile.linkedin_url or "",
        "location": profile.location,
    }


def _build_cover_letter(record: ApplicationRecord) -> str:
    from core.profile import load_profile
    profile = load_profile()
    job = record.job
    return f"""Dear Hiring Manager,

I am excited to apply for the {job.title} position at {job.company}. With {profile.years_experience}+ years of experience in robotics and autonomous systems software engineering, I bring deep expertise in motion planning, C++ systems development, and production-grade robotics software architecture.

At Amazon Robotics, I lead motion planning and controls architecture for a unified C++ SDK supporting multiple robotic platforms. My background spans ADAS/AD systems at Lucid Motors, where I delivered Highway Assist and autonomous parking, and extensive work with ISO 26262, MPC, and real-time embedded systems.

I am particularly drawn to {job.company} because of its leadership in this space and the opportunity to contribute to your mission. I would welcome the chance to discuss how my experience aligns with your team's goals.

Best regards,
{profile.name}"""
