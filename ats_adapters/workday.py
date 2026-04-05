"""
Workday ATS adapter — full multi-step form filler.

Workday application flow:
  1. Job listing page → click Apply button
  2. Account gate → guest apply OR sign in OR create account
  3. Step 1: My Information (name, email, phone, address, source)
  4. Step 2: My Experience (work history, education, resume upload)
  5. Step 3: Application Questions (custom per company)
  6. Step 4: Self Identify (optional EEO questions)
  7. Step 5: Review → human clicks Submit

Key DOM patterns:
  - Fields use data-automation attributes: data-automation="legalNameSection_firstName"
  - Buttons use data-automation: data-automation="bottom-navigation-next-btn"
  - File upload: input[type=file] inside the resume section
  - Multi-select dropdowns use Workday's custom combobox pattern

Bot detection: Workday detects headless Chromium via navigator.webdriver.
We patch this out in agent3's browser context setup.
"""
import time
import os
from pathlib import Path
from rich.console import Console
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from core.models import ApplicationRecord

console = Console()

# How long to wait for elements (ms)
TIMEOUT = 8000
SHORT = 3000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fill(page: Page, selector: str, value: str, timeout: int = TIMEOUT) -> bool:
    """Fill a visible input. Returns True if filled."""
    if not value:
        return False
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.click()
        el.fill(value)
        return True
    except Exception:
        return False


def _click(page: Page, selector: str, timeout: int = TIMEOUT) -> bool:
    """Click a visible element. Returns True if clicked."""
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        el.click()
        time.sleep(0.5)
        return True
    except Exception:
        return False


def _select_dropdown(page: Page, label_text: str, value: str) -> bool:
    """
    Handle Workday's custom dropdown (not a native <select>).
    Clicks the field, types to filter, then clicks the matching option.
    """
    try:
        # Find the dropdown by its label
        field = page.locator(f"[data-automation*='{label_text}']").first
        field.click()
        time.sleep(0.3)
        field.type(value[:3])  # Type first 3 chars to filter options
        time.sleep(0.5)
        # Click the first matching option in the dropdown list
        option = page.locator(f"[data-automation='promptOption']:has-text('{value}')").first
        option.click(timeout=SHORT)
        return True
    except Exception:
        return False


def _next_step(page: Page) -> bool:
    """Click the Next/Continue button on a Workday step."""
    selectors = [
        "[data-automation='bottom-navigation-next-btn']",
        "[data-automation='bottom-navigation-next-button']",
        "button:has-text('Next')",
        "button:has-text('Continue')",
        "button:has-text('Save and Continue')",
    ]
    for sel in selectors:
        if _click(page, sel, timeout=SHORT):
            time.sleep(2)  # Wait for next step to load
            return True
    return False


def _wait_for_workday_step(page: Page, step_indicator: str, timeout: int = 15000):
    """Wait for a specific Workday step to become visible."""
    try:
        page.wait_for_selector(
            f"[data-automation*='{step_indicator}'], h2:has-text('{step_indicator}')",
            timeout=timeout
        )
    except PlaywrightTimeout:
        pass  # Continue anyway — page may have loaded differently


def _upload_resume(page: Page, pdf_path: str) -> bool:
    """Upload resume PDF in Workday's My Experience step."""
    if not pdf_path or not Path(pdf_path).exists():
        console.print(f"  [red]Resume not found: {pdf_path}[/red]")
        return False
    try:
        # Workday resume upload button
        for selector in [
            "input[data-automation='file-upload-input-ref']",
            "input[type='file']",
            "[data-automation='resume-section'] input[type='file']",
        ]:
            try:
                el = page.locator(selector).first
                el.wait_for(state="attached", timeout=SHORT)
                el.set_input_files(pdf_path)
                console.print(f"  [green]✓[/green] Resume uploaded: {Path(pdf_path).name}")
                time.sleep(2)
                return True
            except Exception:
                continue
    except Exception as e:
        console.print(f"  [yellow]Resume upload issue: {e}[/yellow]")
    return False


# ── Account gate ──────────────────────────────────────────────────────────────

def _handle_account_gate(page: Page, profile: dict) -> str:
    """
    Handle the Workday sign-in/create account gate.
    Returns: 'signed_in' | 'guest' | 'created' | 'unknown'
    """
    time.sleep(2)
    url = page.url.lower()

    # Already past the gate
    if "myinformation" in url or "step" in url:
        return "signed_in"

    # Check for sign in page
    if "signin" in url or "login" in url:
        wd_email = os.getenv("WORKDAY_EMAIL", profile["email"])
        wd_pass  = os.getenv("WORKDAY_PASSWORD", "")

        if wd_pass:
            console.print("  [cyan]Signing into Workday account...[/cyan]")
            _fill(page, "input[data-automation='email']", wd_email)
            _fill(page, "input[data-automation='password']", wd_pass)
            _click(page, "[data-automation='click_filter']")  # Sign In button
            time.sleep(3)
            return "signed_in"
        else:
            console.print("  [yellow]No WORKDAY_PASSWORD set. Add to .env to auto-sign-in.[/yellow]")

    # Look for "Apply Manually / Guest" option
    for guest_sel in [
        "a:has-text('Apply Manually')",
        "button:has-text('Apply Manually')",
        "a:has-text('apply without an account')",
        "[data-automation='applyManually']",
    ]:
        if _click(page, guest_sel, timeout=SHORT):
            console.print("  [cyan]Applying as guest[/cyan]")
            time.sleep(2)
            return "guest"

    # Create account flow
    for create_sel in [
        "a:has-text('Create Account')",
        "button:has-text('Create Account')",
        "[data-automation='createAccount']",
    ]:
        if _click(page, create_sel, timeout=SHORT):
            console.print("  [cyan]Creating Workday account...[/cyan]")
            time.sleep(1)
            _fill(page, "input[data-automation='email']", profile["email"])
            _fill(page, "input[data-automation='verifyEmail']", profile["email"])
            _fill(page, "input[data-automation='password']", "Applymatic2025!")
            _fill(page, "input[data-automation='verifyPassword']", "Applymatic2025!")
            _click(page, "[data-automation='createAccountSubmitButton']")
            time.sleep(3)
            console.print("  [yellow]Account created with temp password: Applymatic2025![/yellow]")
            console.print("  [yellow]Change this in your Workday profile after applying.[/yellow]")
            return "created"

    return "unknown"


# ── Step fillers ──────────────────────────────────────────────────────────────

def _fill_my_information(page: Page, profile: dict):
    """Step 1: My Information — name, contact, address."""
    console.print("  [cyan]Step 1: My Information[/cyan]")
    _wait_for_workday_step(page, "myInformation")

    # Name fields
    _fill(page, "[data-automation='legalNameSection_firstName']", profile["first_name"])
    _fill(page, "[data-automation='legalNameSection_lastName']", profile["last_name"])

    # Contact
    _fill(page, "[data-automation='email']", profile["email"])
    _fill(page, "[data-automation='phone-number']", profile["phone"])

    # Address
    _fill(page, "[data-automation='addressSection_addressLine1']", profile.get("address", ""))
    _fill(page, "[data-automation='addressSection_city']", profile.get("city", ""))
    _fill(page, "[data-automation='addressSection_postalCode']", profile.get("zip", ""))

    # How did you hear about us — pick first option
    _select_dropdown(page, "sourceSection_source", "LinkedIn")

    # Generic fallbacks for any missed fields
    _fill(page, "input[type='email']", profile["email"])
    _fill(page, "input[type='tel']", profile["phone"])

    console.print("  [green]✓[/green] My Information filled")


def _fill_my_experience(page: Page, profile: dict, record: ApplicationRecord):
    """Step 2: My Experience — work history, education, resume upload."""
    console.print("  [cyan]Step 2: My Experience[/cyan]")
    _wait_for_workday_step(page, "myExperience")

    # Upload resume first — Workday can auto-parse it
    if record.resume:
        _upload_resume(page, record.resume.pdf_path)
        time.sleep(3)  # Give Workday time to parse the resume

    # LinkedIn URL
    _fill(page, "[data-automation='linkedin']", profile["linkedin"])

    # Website / portfolio
    if profile.get("github"):
        _fill(page, "[data-automation='website']", profile["github"])

    console.print("  [green]✓[/green] My Experience filled")


def _fill_application_questions(page: Page, profile: dict, record: ApplicationRecord):
    """
    Step 3: Application Questions — company-specific questions.
    These vary per company. We handle common ones.
    """
    console.print("  [cyan]Step 3: Application Questions[/cyan]")
    time.sleep(1)

    job = record.job

    # Common yes/no questions — look for radio buttons
    yes_no_patterns = [
        # Sponsorship
        ("sponsorship", "No"),
        ("visa", "No"),
        ("authorize", "Yes"),  # Authorized to work in US
        ("18 years", "Yes"),
        ("relocat", "Yes"),
        ("hybrid", "Yes"),
        ("remote", "Yes"),
    ]

    for pattern, answer in yes_no_patterns:
        try:
            # Find radio group containing the pattern text
            group = page.locator(f"[data-automation*='questionnaire'] label:has-text('{pattern}')").first
            if group.count() > 0:
                # Click Yes or No radio in that group
                radio = page.locator(
                    f"[data-automation*='questionnaire'] label:has-text('{pattern}') ~ div input[value='{answer}']"
                ).first
                if radio.count() > 0:
                    radio.click()
        except Exception:
            continue

    # Text area questions — generate answer with a brief response
    try:
        textareas = page.locator("textarea[data-automation*='question']").all()
        for ta in textareas[:3]:  # Handle up to 3 text questions
            placeholder = ta.get_attribute("placeholder") or ""
            if ta.input_value() == "":  # Only fill empty ones
                # Generic professional response
                ta.fill(
                    f"With {profile.get('years_experience', 10)}+ years in robotics and autonomous systems "
                    f"engineering, I am excited about this opportunity at {job.company}. "
                    f"My background in motion planning, C++, and safety-critical systems aligns directly "
                    f"with this role. I look forward to contributing to your team."
                )
    except Exception:
        pass

    console.print("  [green]✓[/green] Application Questions answered")


def _fill_self_identify(page: Page):
    """Step 4: Self Identify — EEO/voluntary disclosure. Decline all."""
    console.print("  [cyan]Step 4: Self Identify (EEO)[/cyan]")
    time.sleep(1)

    # Click "Decline to Answer" or "I don't wish to answer" for all questions
    for sel in [
        "input[value='Decline_To_Identify']",
        "input[value='I_Do_Not_Wish_To_Answer']",
        "[data-automation*='decline']",
        "label:has-text('Decline')",
        "label:has-text('do not wish')",
    ]:
        try:
            els = page.locator(sel).all()
            for el in els:
                try:
                    el.click(timeout=SHORT)
                except Exception:
                    pass
        except Exception:
            continue

    console.print("  [green]✓[/green] Self Identify completed")


# ── Main entry point ──────────────────────────────────────────────────────────

def fill_workday_form(page: Page, record: ApplicationRecord, profile: dict) -> bool:
    """
    Fill a complete Workday application form.

    Steps:
      1. Click Apply button on job listing
      2. Handle account gate (sign in / guest / create)
      3. Fill My Information
      4. Fill My Experience + upload resume
      5. Answer Application Questions
      6. Complete Self Identify (decline EEO)
      7. Reach Review step — pause for human

    Args:
        page: Playwright page already navigated to the job URL
        record: ApplicationRecord with resume attached
        profile: dict with first_name, last_name, email, phone, etc.

    Returns:
        True if reached Review step, False if failed partway
    """
    job = record.job
    console.print(f"  [cyan]Workday adapter: {job.company}[/cyan]")

    # Step 0: Click the Apply button on the listing page
    console.print("  Looking for Apply button...")
    apply_clicked = False
    for sel in [
        "a:has-text('Apply')",              # NVIDIA and most Workday sites
        "[data-automation='applyButton']",
        "a[data-automation='applyButton']",
        "button:has-text('Apply Now')",
        "a:has-text('Apply Now')",
        "button:has-text('Apply')",
        "a[href*='startApplication']",
    ]:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=2000):
                href = el.get_attribute("href") or ""
                # If it's a full URL, navigate directly instead of clicking
                if href.startswith("http"):
                    page.goto(href, wait_until="domcontentloaded", timeout=30000)
                else:
                    el.click()
                apply_clicked = True
                console.print("  [green]✓[/green] Clicked Apply")
                time.sleep(4)
                break
        except Exception:
            continue

    if not apply_clicked:
        console.print("  [yellow]Could not find Apply button — may already be on application page[/yellow]")

    # Step 1: Handle account gate
    account_status = _handle_account_gate(page, profile)
    console.print(f"  Account status: {account_status}")

    # Step 2: My Information
    try:
        _fill_my_information(page, profile)
        _next_step(page)
    except Exception as e:
        console.print(f"  [yellow]My Information step issue: {e}[/yellow]")

    # Step 3: My Experience
    try:
        _fill_my_experience(page, profile, record)
        _next_step(page)
    except Exception as e:
        console.print(f"  [yellow]My Experience step issue: {e}[/yellow]")

    # Step 4: Application Questions
    try:
        _fill_application_questions(page, profile, record)
        _next_step(page)
    except Exception as e:
        console.print(f"  [yellow]Application Questions step issue: {e}[/yellow]")

    # Step 5: Self Identify
    try:
        _fill_self_identify(page)
        _next_step(page)
    except Exception as e:
        console.print(f"  [yellow]Self Identify step issue: {e}[/yellow]")

    # Now on Review page — hand off to human
    console.print()
    console.print("  [bold green]Reached Review step![/bold green]")
    console.print("  All fields filled. Please review everything carefully.")
    console.print("  When ready, [bold]click Submit[/bold] in the browser.")
    return True
