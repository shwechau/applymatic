"""
Workday ATS form filler.
Workday is the most complex ATS — multi-step, heavy JS, requires careful sequencing.
Full implementation in Day 4-5 sprint.
"""
from playwright.sync_api import Page
from core.models import ApplicationRecord
from rich.console import Console

console = Console()


def fill_workday_form(page: Page, record: ApplicationRecord) -> bool:
    """
    Workday applications are multi-step with dynamic rendering.
    Strategy:
    1. Click 'Apply' button on job listing page
    2. Handle account creation / guest apply
    3. Step through each section: personal info → work history → education → documents → review
    4. Upload resume PDF at documents step
    5. Stop at review step for human approval
    """
    console.print("  [cyan]Workday adapter active[/cyan]")
    console.print("  [yellow]Workday adapter: full multi-step implementation coming Day 4.[/yellow]")
    console.print(f"  [dim]Please apply manually at: {record.job.url}[/dim]")
    console.print(f"  [dim]Resume ready at: {record.resume.pdf_path if record.resume else 'N/A'}[/dim]")

    # For now: open the page and let the user apply manually with the resume ready
    # Full implementation will handle:
    # - Guest vs. account apply flow
    # - Multi-page form navigation
    # - Auto-populating each section
    # - Resume upload at the attachments step
    return False
