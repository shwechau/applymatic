"""
Agent 3: Application Form Filler

OS support:
  - Windows native : headed Playwright (visible browser, agent fills, human submits)
  - Linux + display: headed Playwright (same)
  - WSL            : not supported for form filling — opens URL in Windows browser instead
  - macOS          : headed Playwright (same as Linux)

Flow:
  1. Detect OS + display availability
  2. Open job URL in headed browser
  3. Detect ATS platform from redirected URL
  4. Route to correct ATS adapter to fill all fields + attach resume PDF
  5. Pause for human review — agent filled everything, human just clicks Submit
  6. Record result in tracker
"""
import os
import sys
import time
import platform
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from core.models import ApplicationRecord, ApplicationStatus

console = Console()


# ── OS / display detection ────────────────────────────────────────────────────

def detect_environment() -> str:
    """
    Returns: 'windows' | 'linux-display' | 'wsl' | 'linux-headless' | 'mac'
    """
    system = platform.system()

    if system == "Windows":
        return "windows"

    if system == "Darwin":
        return "mac"

    if system == "Linux":
        # Check if running inside WSL
        try:
            with open("/proc/version") as f:
                if "microsoft" in f.read().lower():
                    return "wsl"
        except Exception:
            pass

        # Check if a display is available
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            return "linux-display"

        return "linux-headless"

    return "unknown"


def can_run_headed_browser(env: str) -> bool:
    return env in ("windows", "mac", "linux-display")


# ── ATS detection ─────────────────────────────────────────────────────────────

def detect_ats(url: str) -> str:
    u = url.lower()
    if "myworkdayjobs" in u or "workday" in u: return "workday"
    if "greenhouse.io" in u or "boards.greenhouse" in u: return "greenhouse"
    if "lever.co" in u:                         return "lever"
    if "icims" in u:                            return "icims"
    if "taleo" in u:                            return "taleo"
    if "smartrecruiters" in u:                  return "smartrecruiters"
    if "jobvite" in u:                          return "jobvite"
    return "unknown"


# ── Browser launcher ──────────────────────────────────────────────────────────

def launch_browser(env: str, headless: bool = False):
    """Launch Playwright browser appropriate for the OS."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()

    launch_args = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }

    if env == "windows":
        # On Windows, try to use installed Chrome for better site compatibility
        chrome_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        ]
        for path in chrome_paths:
            if Path(path).exists():
                launch_args["executable_path"] = path
                break

    browser = pw.chromium.launch(**launch_args)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    # Remove webdriver fingerprint — key for bypassing bot detection
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return pw, browser, context


# ── WSL fallback: open in real Windows browser ────────────────────────────────

def open_in_windows_browser(url: str):
    """Open URL in Windows default browser from WSL."""
    chrome_paths = [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    ]
    for path in chrome_paths:
        if Path(path).exists():
            subprocess.Popen([path, url])
            return path.split("/")[-1].split(".")[0]
    subprocess.Popen(["explorer.exe", url])
    return "browser"


def open_folder_in_explorer(path: str):
    """Open containing folder of a file in Windows Explorer from WSL."""
    abs_path = str(Path(path).resolve())
    if abs_path.startswith("/mnt/"):
        parts = abs_path[5:].split("/", 1)
        drive = parts[0].upper() + ":\\"
        rest = parts[1].replace("/", "\\") if len(parts) > 1 else ""
        win_folder = str(Path(drive + rest).parent)
    else:
        win_folder = str(Path(abs_path).parent)
    subprocess.Popen(["explorer.exe", win_folder])


# ── Form filling helpers ──────────────────────────────────────────────────────

def wait_and_fill(page, selector: str, value: str, timeout: int = 3000):
    """Fill a field if it exists, silently skip if not."""
    if not value:
        return False
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.fill(value)
        return True
    except Exception:
        return False


def upload_resume(page, pdf_path: str) -> bool:
    """Attach resume PDF to the first file input found."""
    if not pdf_path or not Path(pdf_path).exists():
        console.print(f"  [red]Resume PDF not found: {pdf_path}[/red]")
        return False
    try:
        file_input = page.locator("input[type='file']").first
        file_input.wait_for(state="attached", timeout=5000)
        file_input.set_input_files(pdf_path)
        console.print(f"  [green]✓[/green] Resume uploaded: {Path(pdf_path).name}")
        return True
    except Exception as e:
        console.print(f"  [yellow]Could not auto-upload resume: {e}[/yellow]")
        console.print(f"  [dim]Attach manually: {pdf_path}[/dim]")
        return False


# ── ATS form fillers ──────────────────────────────────────────────────────────

def fill_greenhouse(page, record: ApplicationRecord, profile: dict):
    console.print("  [cyan]Filling Greenhouse form...[/cyan]")
    wait_and_fill(page, "input#first_name", profile["first_name"])
    wait_and_fill(page, "input#last_name", profile["last_name"])
    wait_and_fill(page, "input#email", profile["email"])
    wait_and_fill(page, "input#phone", profile["phone"])
    wait_and_fill(page, "input[name*='linkedin']", profile["linkedin"])
    wait_and_fill(page, "input[name*='location']", profile["location"])
    upload_resume(page, record.resume.pdf_path)
    console.print("  [green]✓[/green] Greenhouse form filled")


def fill_lever(page, record: ApplicationRecord, profile: dict):
    console.print("  [cyan]Filling Lever form...[/cyan]")
    wait_and_fill(page, "input[name='name']", profile["full_name"])
    wait_and_fill(page, "input[name='email']", profile["email"])
    wait_and_fill(page, "input[name='phone']", profile["phone"])
    wait_and_fill(page, "input[name='org']", profile["current_company"])
    wait_and_fill(page, "input[name='urls[LinkedIn]']", profile["linkedin"])
    wait_and_fill(page, "input[name='urls[GitHub]']", profile["github"])
    upload_resume(page, record.resume.pdf_path)
    console.print("  [green]✓[/green] Lever form filled")


def fill_workday(page, record: ApplicationRecord, profile: dict):
    """
    Workday is multi-step. We navigate to the apply page and fill what we can.
    The agent handles personal info; complex steps pause for human.
    """
    console.print("  [cyan]Workday: navigating to apply page...[/cyan]")

    # Click Apply button if present
    for apply_selector in [
        "a[data-automation='applyButton']",
        "button[data-automation='applyButton']",
        "a:has-text('Apply')",
        "button:has-text('Apply Now')",
    ]:
        try:
            btn = page.locator(apply_selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                console.print("  [green]✓[/green] Clicked Apply")
                break
        except Exception:
            continue

    time.sleep(2)

    # Fill personal info fields (Workday uses data-automation attributes)
    fields = [
        ("input[data-automation='legalNameSection_firstName']", profile["first_name"]),
        ("input[data-automation='legalNameSection_lastName']", profile["last_name"]),
        ("input[data-automation='email']", profile["email"]),
        ("input[data-automation='phone']", profile["phone"]),
        ("input[data-automation='addressSection_addressLine1']", profile.get("address", "")),
        ("input[data-automation='addressSection_city']", profile.get("city", "")),
        # Generic fallbacks
        ("input[id*='firstName']", profile["first_name"]),
        ("input[id*='lastName']", profile["last_name"]),
        ("input[type='email']", profile["email"]),
        ("input[type='tel']", profile["phone"]),
    ]

    filled = 0
    seen_selectors = set()
    for selector, value in fields:
        if selector not in seen_selectors and value:
            if wait_and_fill(page, selector, value, timeout=2000):
                filled += 1
                seen_selectors.add(selector)

    # Try resume upload
    upload_resume(page, record.resume.pdf_path)

    console.print(f"  [green]✓[/green] Workday: filled {filled} fields")
    console.print("  [yellow]Note: Workday is multi-step — review each section carefully[/yellow]")


def fill_generic(page, record: ApplicationRecord, profile: dict):
    """Best-effort fill for unknown ATS platforms."""
    console.print("  [cyan]Generic form fill...[/cyan]")

    field_map = [
        (["input[name*='first']", "input[id*='first']", "input[placeholder*='First']"], profile["first_name"]),
        (["input[name*='last']", "input[id*='last']", "input[placeholder*='Last']"], profile["last_name"]),
        (["input[name='name']", "input[placeholder*='Full name']", "input[placeholder*='Your name']"], profile["full_name"]),
        (["input[type='email']", "input[name*='email']"], profile["email"]),
        (["input[type='tel']", "input[name*='phone']"], profile["phone"]),
        (["input[name*='linkedin']", "input[placeholder*='LinkedIn']"], profile["linkedin"]),
        (["input[name*='location']", "input[name*='city']"], profile["location"]),
    ]

    filled = 0
    for selectors, value in field_map:
        if not value:
            continue
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible(timeout=1000):
                    el.fill(value)
                    filled += 1
                    break
            except Exception:
                continue

    upload_resume(page, record.resume.pdf_path)
    console.print(f"  [green]✓[/green] Generic: filled {filled} fields")


# ── Main entry point ──────────────────────────────────────────────────────────

def run_application(
    record: ApplicationRecord,
    dry_run: bool = True,
    human_review: bool = True,
) -> ApplicationRecord:
    """
    Fill out a job application form.

    On Windows/Mac/Linux-with-display:
      - Opens headed browser (visible to user)
      - Agent fills all fields + attaches resume
      - Pauses for human to review and click Submit

    On WSL:
      - Opens URL in Windows Chrome (where user is logged in)
      - Opens resume folder in Explorer
      - User fills and submits manually
    """
    job = record.job
    resume = record.resume

    if not resume:
        console.print(f"[red]No resume for {job.company}. Run `tailor` first.[/red]")
        record.status = ApplicationStatus.ERROR
        record.error_message = "No resume available"
        return record

    env = detect_environment()
    ats = job.ats_platform or detect_ats(job.url)

    console.print(f"\n[bold cyan]Agent 3: {job.company} — {job.title}[/bold cyan]")
    console.print(f"  ATS: {ats}  |  Env: {env}  |  Resume: {resume.filename}")

    # Load profile for form filling
    from core.profile import load_profile
    profile_obj = load_profile()
    name_parts = profile_obj.name.split(" ", 1)
    profile = {
        "first_name": name_parts[0],
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "full_name": profile_obj.name,
        "email": profile_obj.email,
        "phone": profile_obj.phone or "",
        "linkedin": profile_obj.linkedin_url or "",
        "github": profile_obj.github_url or "",
        "location": profile_obj.location,
        "city": profile_obj.location.split(",")[0].strip(),
        "current_company": profile_obj.experience[0]["company"] if profile_obj.experience else "",
        "address": "",
    }

    # ── WSL: can't run headed browser, open in Windows Chrome ────────────────
    if env == "wsl":
        console.print("  [yellow]WSL detected — opening in your Windows browser[/yellow]")
        browser_name = open_in_windows_browser(job.url)
        open_folder_in_explorer(resume.pdf_path)
        console.print(f"  [green]✓[/green] Opened in {browser_name}")
        console.print(f"  [green]✓[/green] Resume folder opened in Explorer")
        console.print(f"\n  Attach: [cyan]{resume.filename}[/cyan]")
        console.print("  Fill the form, submit, then return here.\n")

        if dry_run:
            console.print("  [dim]DRY RUN — auto-advancing in 5s (Ctrl+C to stop)[/dim]")
            try:
                for i in range(5, 0, -1):
                    sys.stdout.write(f"\r  Continuing in {i}s... ")
                    sys.stdout.flush()
                    time.sleep(1)
                sys.stdout.write("\r  Moving to next job...        \n")
                sys.stdout.flush()
            except KeyboardInterrupt:
                raise
            record.status = ApplicationStatus.AWAITING_REVIEW
        else:
            try:
                with open("/dev/tty") as tty:
                    sys.stdout.write("  Applied? [y/s/q] > ")
                    sys.stdout.flush()
                    result = tty.readline().strip().lower()
            except Exception:
                result = input("  Applied? [y/s/q] > ").strip().lower()
            record.status = _record_result(result, record)
        return record

    # ── Windows / Mac / Linux with display: headed Playwright ────────────────
    if not can_run_headed_browser(env):
        console.print(f"  [red]No display available (env={env}). Cannot open browser.[/red]")
        console.print(f"  Apply manually: {job.url}")
        record.status = ApplicationStatus.AWAITING_REVIEW
        return record

    pw = None
    try:
        console.print("  Launching browser...")
        pw, browser, context = launch_browser(env, headless=False)
        page = context.new_page()

        # Navigate to job page
        console.print(f"  Navigating to {job.url[:60]}...")
        page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Re-detect ATS from actual loaded URL (may have redirected)
        actual_url = page.url
        actual_ats = detect_ats(actual_url) or ats
        if actual_ats != ats:
            console.print(f"  [dim]ATS updated: {ats} → {actual_ats}[/dim]")

        # Fill the form
        if actual_ats == "greenhouse":
            fill_greenhouse(page, record, profile)
        elif actual_ats == "lever":
            fill_lever(page, record, profile)
        elif actual_ats == "workday":
            fill_workday(page, record, profile)
        else:
            fill_generic(page, record, profile)

        record.status = ApplicationStatus.FORM_FILLED

        # ── Human review gate ─────────────────────────────────────────────
        console.print()
        console.print(Panel(
            f"[bold]Form filled by agent.[/bold]\n\n"
            f"Please review all fields in the browser.\n"
            f"Make any corrections needed, then [bold green]click Submit[/bold green] yourself.\n\n"
            f"[dim]Resume attached: {resume.filename}[/dim]",
            title="Review required",
            border_style="yellow",
        ))

        if dry_run:
            console.print("[dim]DRY RUN — browser will stay open for 15s then close[/dim]")
            time.sleep(15)
            record.status = ApplicationStatus.AWAITING_REVIEW
        else:
            console.print("After submitting in the browser, come back here:")
            console.print("  [green]y[/green] = submitted  |  [yellow]s[/yellow] = skip  |  [red]q[/red] = quit")
            try:
                with open("/dev/tty") as tty:
                    sys.stdout.write("\n  Result > ")
                    sys.stdout.flush()
                    result = tty.readline().strip().lower()
            except Exception:
                result = input("\n  Result > ").strip().lower()
            record.status = _record_result(result, record)

        context.close()
        browser.close()
        pw.stop()

    except ImportError:
        console.print("[red]Playwright not installed. Run: pip install playwright && playwright install chromium[/red]")
        record.status = ApplicationStatus.ERROR
        record.error_message = "Playwright not installed"
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        record.status = ApplicationStatus.ERROR
        record.error_message = str(e)
        if pw:
            try: pw.stop()
            except Exception: pass

    return record


def _record_result(result: str, record: ApplicationRecord) -> ApplicationStatus:
    if result == "y":
        console.print("  [green]✓ Marked as submitted![/green]")
        return ApplicationStatus.SUBMITTED
    elif result == "q":
        console.print("  [yellow]Session stopped.[/yellow]")
        import typer
        raise typer.Exit(0)
    else:
        console.print("  [dim]Skipped.[/dim]")
        return ApplicationStatus.SKIPPED
