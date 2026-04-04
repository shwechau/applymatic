"""
Agent 1: Job Discovery
- Searches job boards for matching roles in Bay Area
- Scores each job against user profile using Claude
- Returns ranked list of JobPosting objects
"""
import os
import json
import hashlib
import httpx
from rich.console import Console
from rich.progress import track
import anthropic

from core.models import JobPosting, UserProfile

console = Console()

def _get_client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ── Job board search ──────────────────────────────────────────────────────────

def search_jsearch_api(query: str, location: str, num_results: int = 20) -> list[dict]:
    """Search jobs via JSearch API (RapidAPI) - free tier available."""
    api_key = os.getenv("JSEARCH_API_KEY", "")
    if not api_key:
        console.print("[yellow]No JSEARCH_API_KEY set. Using LinkedIn public search fallback.[/yellow]")
        return []

    url = "https://jsearch.p.rapidapi.com/search"
    params = {
        "query": f"{query} in {location}",
        "page": "1",
        "num_pages": "2",
        "date_posted": "week",
    }
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    try:
        with httpx.Client(timeout=15) as http:
            resp = http.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])[:num_results]
    except Exception as e:
        console.print(f"[red]JSearch API error: {e}[/red]")
        return []


def search_linkedin_public(query: str, location: str) -> list[dict]:
    """Scrape LinkedIn public job listings (no auth needed for public listings)."""
    import urllib.parse
    from bs4 import BeautifulSoup

    keywords = urllib.parse.quote_plus(query)
    loc = urllib.parse.quote_plus(location)
    url = f"https://www.linkedin.com/jobs/search/?keywords={keywords}&location={loc}&f_TPR=r604800&sortBy=DD"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    jobs = []
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as http:
            resp = http.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="base-card")[:20]

            for card in cards:
                try:
                    title_el = card.find("h3", class_="base-search-card__title")
                    company_el = card.find("h4", class_="base-search-card__subtitle")
                    loc_el = card.find("span", class_="job-search-card__location")
                    link_el = card.find("a", class_="base-card__full-link")
                    if not all([title_el, company_el, link_el]):
                        continue
                    jobs.append({
                        "title": title_el.get_text(strip=True),
                        "company": company_el.get_text(strip=True),
                        "location": loc_el.get_text(strip=True) if loc_el else location,
                        "url": link_el["href"].split("?")[0],
                        "source": "linkedin",
                        "description": "",  # fetched separately
                    })
                except Exception:
                    continue
    except Exception as e:
        console.print(f"[red]LinkedIn scrape error: {e}[/red]")

    return jobs


def fetch_job_description(url: str) -> str:
    """Fetch full job description from a job posting URL."""
    from bs4 import BeautifulSoup
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as http:
            resp = http.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Try common job description containers
            for selector in [
                "div.description__text",           # LinkedIn
                "div#jobDescriptionText",          # Indeed
                "div.job-description",
                "div[class*='description']",
                "section.jobsearch-jobDescriptionText",
                "div.show-more-less-html",
            ]:
                el = soup.select_one(selector)
                if el:
                    return el.get_text(separator="\n", strip=True)[:4000]
            # Fallback: grab main content
            main = soup.find("main") or soup.find("article")
            if main:
                return main.get_text(separator="\n", strip=True)[:4000]
    except Exception as e:
        console.print(f"[dim]Could not fetch JD from {url}: {e}[/dim]")
    return ""


def normalize_jsearch_job(raw: dict) -> dict:
    """Normalize JSearch API result to our internal format."""
    return {
        "title": raw.get("job_title", ""),
        "company": raw.get("employer_name", ""),
        "location": raw.get("job_city", "") + ", " + raw.get("job_state", ""),
        "url": raw.get("job_apply_link") or raw.get("job_google_link", ""),
        "source": raw.get("job_publisher", "jsearch").lower(),
        "description": raw.get("job_description", "")[:4000],
    }


# ── LLM scoring ───────────────────────────────────────────────────────────────

SCORING_PROMPT = """You are an expert technical recruiter specializing in robotics and autonomous systems.

Given this candidate profile and job posting, score the match from 0-100 and explain why.

CANDIDATE PROFILE:
{profile_summary}

JOB POSTING:
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

Respond ONLY with valid JSON in this exact format:
{{
  "score": <integer 0-100>,
  "reasons": ["reason1", "reason2", "reason3"],
  "ats_platform": "<workday|greenhouse|lever|icims|taleo|unknown>",
  "skip": <true|false>,
  "skip_reason": "<only if skip=true>"
}}

Scoring criteria:
- 90-100: Near-perfect match (same domain, right seniority, strong keyword overlap)
- 70-89: Good match (related domain, reasonable seniority fit)
- 50-69: Partial match (transferable skills but some gaps)
- Below 50: Poor match (skip)

Skip if: clearly a management role when candidate is IC, requires clearance, clearly not tech, or location is wrong.
"""


def score_job(job: dict, profile: UserProfile) -> tuple[float, list[str], str, bool, str]:
    """Use Claude to score job relevance. Returns (score, reasons, ats_platform, skip, skip_reason)."""
    profile_summary = f"""
Name: {profile.name}
Current title: {profile.current_title}
Years experience: {profile.years_experience}
Location preference: {profile.location}
Skills: {', '.join(profile.skills[:20])}
Recent experience: {profile.experience[0]['title']} at {profile.experience[0]['company']} - {', '.join(profile.experience[0].get('bullets', [])[:3])}
"""

    prompt = SCORING_PROMPT.format(
        profile_summary=profile_summary.strip(),
        title=job["title"],
        company=job["company"],
        location=job["location"],
        description=job["description"][:3000],
    )

    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        return (
            float(result.get("score", 0)),
            result.get("reasons", []),
            result.get("ats_platform", "unknown"),
            result.get("skip", False),
            result.get("skip_reason", ""),
        )
    except Exception as e:
        console.print(f"[red]Scoring error: {e}[/red]")
        return 50.0, ["Scoring failed"], "unknown", False, ""


# ── Main agent entry point ────────────────────────────────────────────────────

def run_discovery(
    profile: UserProfile,
    search_queries: list[str] | None = None,
    location: str = "San Francisco Bay Area",
    min_score: float = 70.0,
    max_results: int = 10,
) -> list[JobPosting]:
    """
    Full job discovery pipeline.
    Returns sorted list of JobPosting objects above min_score.
    """
    if search_queries is None:
        search_queries = [
            "Robotics Software Engineer",
            "ADAS Software Engineer motion planning",
            "Autonomous Driving Software Engineer",
            "Staff Software Engineer robotics",
            "Senior Software Engineer motion planning C++",
        ]

    console.print(f"\n[bold cyan]Agent 1: Job Discovery[/bold cyan]")
    console.print(f"Searching {len(search_queries)} queries in {location}...\n")

    raw_jobs: list[dict] = []

    for query in search_queries:
        # Try JSearch API first, fall back to LinkedIn scraper
        api_key = os.getenv("JSEARCH_API_KEY", "")
        if api_key:
            results = search_jsearch_api(query, location)
            raw_jobs.extend([normalize_jsearch_job(r) for r in results])
        else:
            results = search_linkedin_public(query, location)
            raw_jobs.extend(results)

    # Filter blacklisted company+title combos
    # BLACKLISTED_COMPANIES = company-level block (e.g. "Uber,Lyft")
    # BLACKLISTED_JOBS = "Company::Title" pairs (e.g. "Applied Intuition::Motion Planning")
    blacklist_companies_raw = os.getenv("BLACKLISTED_COMPANIES", "")
    blacklist_companies = [c.strip().lower() for c in blacklist_companies_raw.split(",") if c.strip()]

    blacklist_jobs_raw = os.getenv("BLACKLISTED_JOBS", "")
    blacklist_jobs = []
    for entry in blacklist_jobs_raw.split("|"):
        entry = entry.strip()
        if "::" in entry:
            co, title = entry.split("::", 1)
            blacklist_jobs.append((co.strip().lower(), title.strip().lower()))

    def is_blacklisted(job: dict) -> bool:
        company = job.get("company", "").lower()
        title = job.get("title", "").lower()
        if any(b in company for b in blacklist_companies):
            return True
        for bl_co, bl_title in blacklist_jobs:
            if bl_co in company and any(w in title for w in bl_title.split()):
                return True
        return False

    if blacklist_companies or blacklist_jobs:
        before = len(raw_jobs)
        raw_jobs = [j for j in raw_jobs if not is_blacklisted(j)]
        filtered = before - len(raw_jobs)
        if filtered:
            console.print(f"[dim]Filtered {filtered} blacklisted jobs[/dim]")

    # Deduplicate by URL
    seen_urls = set()
    unique_jobs = []
    for job in raw_jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    console.print(f"Found {len(unique_jobs)} unique job postings. Fetching descriptions...\n")

    # Fetch descriptions for jobs that don't have them
    for job in unique_jobs:
        if not job.get("description") and job.get("url"):
            job["description"] = fetch_job_description(job["url"])

    console.print(f"Scoring {len(unique_jobs)} jobs against your profile...\n")

    scored: list[JobPosting] = []

    for job in track(unique_jobs, description="Scoring jobs..."):
        score, reasons, ats, skip, skip_reason = score_job(job, profile)

        if skip:
            console.print(f"[dim]Skipping {job['company']} - {job['title']}: {skip_reason}[/dim]")
            continue

        if score < min_score:
            console.print(f"[dim]Score {score:.0f} < {min_score} — skipping {job['company']}[/dim]")
            continue

        job_id = hashlib.md5(job["url"].encode()).hexdigest()[:12]

        posting = JobPosting(
            id=job_id,
            title=job["title"],
            company=job["company"],
            location=job["location"],
            url=job["url"],
            description=job["description"],
            source=job.get("source", "unknown"),
            ats_platform=ats,
            match_score=score,
            match_reasons=reasons,
        )
        scored.append(posting)
        console.print(f"[green]✓[/green] {score:.0f}/100 — {job['company']}: {job['title']}")

    # Sort by score descending, cap at max_results
    scored.sort(key=lambda j: j.match_score or 0, reverse=True)
    final = scored[:max_results]

    console.print(f"\n[bold green]Found {len(final)} matching jobs above score {min_score}[/bold green]\n")
    return final


# ── Manual job URL helpers ────────────────────────────────────────────────────

def detect_ats_from_url(url: str) -> str:
    """Detect ATS platform from URL string."""
    u = url.lower()
    if "myworkdayjobs" in u or "workday" in u: return "workday"
    if "greenhouse" in u:                       return "greenhouse"
    if "lever.co" in u:                         return "lever"
    if "icims" in u:                            return "icims"
    if "taleo" in u:                            return "taleo"
    if "smartrecruiters" in u:                  return "smartrecruiters"
    if "jobvite" in u:                          return "jobvite"
    return "unknown"


def extract_job_meta(url: str, description: str) -> dict:
    """
    Use Claude to extract company name, job title, and location from
    a job URL + description. Falls back to URL parsing if LLM fails.
    """
    # Fast path: parse from Workday-style URLs
    # e.g. nvidia.wd5.myworkdayjobs.com → NVIDIA
    import re
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Extract company from subdomain (nvidia.wd5... → nvidia)
    company_guess = hostname.split(".")[0].upper()
    # Clean known suffixes
    for suffix in ["WD5", "WD1", "WD3", "WD10", "EXTERNAL", "CAREERS", "JOBS"]:
        company_guess = company_guess.replace(suffix, "").strip("-")

    # Extract title from URL path slug
    path = parsed.path
    slug = path.split("/")[-1] if "/" in path else path
    # Remove job ID suffix (e.g. _JR2015666)
    slug = re.sub(r"_[A-Z]{2}\d+$", "", slug)
    title_guess = slug.replace("-", " ").title()

    # Use LLM to refine if description available
    if description:
        try:
            prompt = f"""Extract the job title, company name, and location from this job posting.

URL: {url}
Description excerpt: {description[:1500]}

Respond with JSON only:
{{"title": "exact job title", "company": "company name", "location": "City, State or Remote"}}"""

            msg = _get_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
                text = text.rsplit("```", 1)[0]
            import json
            data = json.loads(text)
            return {
                "title": data.get("title", title_guess),
                "company": data.get("company", company_guess),
                "location": data.get("location", "Bay Area, CA"),
                "ats": detect_ats_from_url(url),
            }
        except Exception:
            pass

    return {
        "title": title_guess,
        "company": company_guess,
        "location": "Bay Area, CA",
        "ats": detect_ats_from_url(url),
    }
