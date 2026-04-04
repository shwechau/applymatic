"""
Profile management: load from JSON file or extract from LinkedIn.
"""
import json
import os
from pathlib import Path
from rich.console import Console
import anthropic

from core.models import UserProfile

console = Console()

def _get_client():
    """Lazy client init — avoids crashing at import time if key not yet set."""
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROFILE_PATH = Path("config/profile.json")


def load_profile() -> UserProfile:
    """Load profile from config/profile.json."""
    if not PROFILE_PATH.exists():
        console.print(f"[red]Profile not found at {PROFILE_PATH}[/red]")
        console.print("Run: python main.py setup-profile")
        raise FileNotFoundError(f"Profile not found: {PROFILE_PATH}")
    with open(PROFILE_PATH) as f:
        data = json.load(f)
    return UserProfile.model_validate(data)


def save_profile(profile: UserProfile):
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(json.loads(profile.model_dump_json()), f, indent=2)
    console.print(f"[green]Profile saved to {PROFILE_PATH}[/green]")


def extract_profile_from_linkedin(linkedin_url: str) -> UserProfile:
    """
    Fetch LinkedIn public profile page and use Claude to extract structured profile data.
    """
    import httpx
    from bs4 import BeautifulSoup

    console.print(f"Fetching LinkedIn profile: {linkedin_url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    profile_text = ""
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as http:
            resp = http.get(linkedin_url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Extract visible text from key sections
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            profile_text = soup.get_text(separator="\n", strip=True)[:6000]
    except Exception as e:
        console.print(f"[yellow]Could not auto-fetch LinkedIn (may need login). Error: {e}[/yellow]")
        console.print("Falling back to manual profile entry...")
        return create_profile_interactively()

    if len(profile_text) < 500:
        console.print("[yellow]LinkedIn profile text too short (profile may be private). Using manual entry.[/yellow]")
        return create_profile_interactively()

    # Use Claude to extract structured profile
    prompt = f"""Extract structured profile information from this LinkedIn page text.

LinkedIn page text:
{profile_text}

Environment variables for defaults:
- Name: {os.getenv('OWNER_NAME', '')}
- Email: {os.getenv('OWNER_EMAIL', '')}
- LinkedIn URL: {linkedin_url}
- Location: {os.getenv('TARGET_LOCATION', 'Bay Area, CA')}

Respond with valid JSON matching this exact structure:
{{
  "name": "Full Name",
  "email": "{os.getenv('OWNER_EMAIL', 'your@email.com')}",
  "phone": "+1-xxx-xxx-xxxx",
  "linkedin_url": "{linkedin_url}",
  "location": "City, State",
  "years_experience": <integer>,
  "current_title": "Current Job Title",
  "summary": "Professional summary paragraph",
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Month Year - Month Year",
      "bullets": ["achievement 1", "achievement 2", "achievement 3"]
    }}
  ],
  "education": [
    {{
      "degree": "MS Electrical Engineering",
      "school": "University Name",
      "year": "2015"
    }}
  ],
  "certifications": ["cert1", "cert2"],
  "github_url": null,
  "website_url": null
}}"""

    msg = _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]

    profile_data = json.loads(text)
    return UserProfile.model_validate(profile_data)


def create_profile_interactively() -> UserProfile:
    """Minimal interactive profile builder used as fallback."""
    from rich.prompt import Prompt
    console.print("\n[bold]Let's build your profile manually.[/bold]")

    name = Prompt.ask("Full name", default=os.getenv("OWNER_NAME", ""))
    email = Prompt.ask("Email", default=os.getenv("OWNER_EMAIL", ""))
    phone = Prompt.ask("Phone (optional)", default="")
    location = Prompt.ask("Location", default=os.getenv("TARGET_LOCATION", "Bay Area, CA"))

    console.print("\n[dim]Paste your professional summary (press Enter twice when done):[/dim]")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    summary = "\n".join(lines[:-1]) if lines else ""

    years = int(Prompt.ask("Years of experience", default="10"))
    current_title = Prompt.ask("Current job title", default="Senior Software Engineer")

    console.print("\n[dim]Skills (comma-separated):[/dim]")
    skills_raw = input()
    skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

    return UserProfile(
        name=name,
        email=email,
        phone=phone or None,
        linkedin_url=os.getenv("LINKEDIN_URL"),
        location=location,
        years_experience=years,
        current_title=current_title,
        summary=summary,
        skills=skills,
        experience=[],
        education=[],
    )
