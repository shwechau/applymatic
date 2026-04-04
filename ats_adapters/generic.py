"""Generic form filler for unknown ATS platforms."""
from playwright.sync_api import Page
from core.models import ApplicationRecord
from rich.console import Console

console = Console()

FIELD_PATTERNS = {
    "first_name": ["input[name*='first']", "input[id*='first']", "input[placeholder*='First']"],
    "last_name":  ["input[name*='last']",  "input[id*='last']",  "input[placeholder*='Last']"],
    "full_name":  ["input[name='name']",   "input[id='name']",   "input[placeholder*='Full name']"],
    "email":      ["input[type='email']",  "input[name*='email']", "input[id*='email']"],
    "phone":      ["input[type='tel']",    "input[name*='phone']", "input[id*='phone']"],
    "linkedin":   ["input[name*='linkedin']", "input[placeholder*='LinkedIn']"],
    "location":   ["input[name*='location']", "input[name*='city']"],
}


def fill_generic_form(page: Page, record: ApplicationRecord) -> bool:
    from core.profile import load_profile
    profile = load_profile()
    resume = record.resume

    console.print("  [cyan]Generic adapter active[/cyan]")

    name_parts = profile.name.split(" ", 1)
    values = {
        "first_name": name_parts[0],
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "full_name": profile.name,
        "email": profile.email,
        "phone": profile.phone or "",
        "linkedin": profile.linkedin_url or "",
        "location": profile.location,
    }

    filled = 0
    for field, selectors in FIELD_PATTERNS.items():
        for selector in selectors:
            try:
                el = page.locator(selector).first
                if el.count() > 0 and el.is_visible():
                    el.fill(values.get(field, ""))
                    filled += 1
                    break
            except Exception:
                continue

    # File upload
    if resume and resume.pdf_path:
        try:
            file_input = page.locator("input[type=file]").first
            if file_input.count() > 0:
                file_input.set_input_files(resume.pdf_path)
                console.print("  [green]✓[/green] Resume uploaded")
        except Exception as e:
            console.print(f"  [yellow]Could not upload resume: {e}[/yellow]")

    console.print(f"  [green]✓[/green] Filled {filled} fields (generic adapter)")
    return filled > 0
