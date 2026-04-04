"""
Agent 2: Resume Tailoring + PDF Generation
- Takes a job posting + user profile
- Uses Claude to tailor the resume to the specific job
- Converts to PDF via WeasyPrint
- Saves as shwetachauhan_companyname_position.pdf
"""
import os
import re
import json
from pathlib import Path
from datetime import datetime
import anthropic
from rich.console import Console

from core.models import JobPosting, UserProfile, TailoredResume

console = Console()

def _get_client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PDF_OUTPUT_DIR = Path("output/pdfs")
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Filename builder ──────────────────────────────────────────────────────────

def build_filename(profile: UserProfile, job: JobPosting) -> str:
    """Build: shwetachauhan_nvidia_seniorroboticsswengineer.pdf"""
    def clean(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9]", "", s)
        return s[:30]

    name = clean(profile.name.replace(" ", ""))
    company = clean(job.company)
    # Shorten title: remove filler words
    title = job.title
    for word in ["Senior", "Staff", "Principal", "Software", "Engineer", "the", "and", "of", "for", "a"]:
        title = re.sub(rf"\b{word}\b", "", title, flags=re.IGNORECASE)
    title = clean(title.strip())
    if not title:
        title = "role"
    return f"{name}_{company}_{title}.pdf"


# ── LLM tailoring ─────────────────────────────────────────────────────────────

TAILORING_PROMPT = """You are an expert technical resume writer specializing in robotics, autonomous systems, and ADAS.

Your task: Tailor this resume for the specific job posting. The goal is to maximize ATS keyword matches and relevance while keeping everything 100% truthful — do NOT invent skills or experience.

CANDIDATE BASE RESUME (JSON):
{resume_json}

JOB POSTING:
Title: {title}
Company: {company}
Description:
{description}

INSTRUCTIONS:
1. Rewrite the professional summary (3-4 sentences) to directly address this role
2. Reorder and emphasize the most relevant skills for this job (put matching skills first)
3. For each experience entry, rewrite 2-4 bullet points to emphasize what's most relevant — use the job's keywords where they truthfully apply
4. Keep all dates, titles, companies, and education EXACTLY as-is
5. Identify 8-12 keywords from the JD that appear (or can truthfully appear) in the resume

Respond with valid JSON only:
{{
  "summary": "<rewritten 3-4 sentence summary>",
  "skills_ordered": ["skill1", "skill2", ...],
  "experience": [
    {{
      "title": "<exact same title>",
      "company": "<exact same company>",
      "dates": "<exact same dates>",
      "bullets": ["rewritten bullet 1", "rewritten bullet 2", "rewritten bullet 3"]
    }}
  ],
  "keyword_matches": ["keyword1", "keyword2", ...],
  "tailoring_notes": "<brief explanation of what was changed and why>"
}}
"""


def tailor_resume_with_llm(profile: UserProfile, job: JobPosting) -> dict:
    """Call Claude to tailor the resume for a specific job."""
    resume_json = json.dumps({
        "name": profile.name,
        "current_title": profile.current_title,
        "summary": profile.summary,
        "skills": profile.skills,
        "experience": profile.experience,
        "education": profile.education,
        "certifications": profile.certifications or [],
    }, indent=2)

    prompt = TAILORING_PROMPT.format(
        resume_json=resume_json,
        title=job.title,
        company=job.company,
        description=job.description[:3500],
    )

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

    return json.loads(text)


# ── HTML resume template ──────────────────────────────────────────────────────

def build_resume_html(profile: UserProfile, tailored: dict) -> str:
    """Build clean HTML resume from tailored data. Optimized for PDF rendering."""
    experience_html = ""
    for exp in tailored.get("experience", profile.experience):
        bullets_html = "\n".join(
            f"<li>{b}</li>" for b in exp.get("bullets", [])
        )
        experience_html += f"""
        <div class="entry">
          <div class="entry-header">
            <span class="entry-title">{exp['title']}</span>
            <span class="entry-dates">{exp.get('dates', '')}</span>
          </div>
          <div class="entry-company">{exp['company']}</div>
          <ul>{bullets_html}</ul>
        </div>"""

    education_html = ""
    for edu in profile.education:
        education_html += f"""
        <div class="entry">
          <div class="entry-header">
            <span class="entry-title">{edu.get('degree', '')}</span>
            <span class="entry-dates">{edu.get('year', '')}</span>
          </div>
          <div class="entry-company">{edu.get('school', '')}</div>
        </div>"""

    skills = tailored.get("skills_ordered", profile.skills)
    skills_html = " &bull; ".join(skills[:24])

    certifications_html = ""
    if profile.certifications:
        certs = " &bull; ".join(profile.certifications)
        certifications_html = f"""
        <div class="section">
          <div class="section-title">Certifications</div>
          <p>{certs}</p>
        </div>"""

    links = []
    if profile.linkedin_url:
        links.append(f'<a href="{profile.linkedin_url}">LinkedIn</a>')
    if profile.github_url:
        links.append(f'<a href="{profile.github_url}">GitHub</a>')
    links_html = " &nbsp;|&nbsp; ".join(links)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #1a1a1a;
    padding: 0.6in 0.7in;
    max-width: 8.5in;
  }}
  h1 {{ font-size: 22pt; font-weight: 600; color: #0f172a; letter-spacing: -0.5px; }}
  .contact {{
    font-size: 9pt;
    color: #475569;
    margin-top: 4px;
    margin-bottom: 16px;
  }}
  .contact a {{ color: #2563eb; text-decoration: none; }}
  .section {{ margin-bottom: 18px; }}
  .section-title {{
    font-size: 10pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #0f172a;
    border-bottom: 1.5px solid #e2e8f0;
    padding-bottom: 3px;
    margin-bottom: 10px;
  }}
  .summary {{ font-size: 9.5pt; color: #334155; line-height: 1.6; }}
  .skills {{ font-size: 9pt; color: #334155; line-height: 1.8; }}
  .entry {{ margin-bottom: 12px; }}
  .entry-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .entry-title {{ font-weight: 600; font-size: 10pt; color: #0f172a; }}
  .entry-dates {{ font-size: 9pt; color: #64748b; white-space: nowrap; }}
  .entry-company {{ font-size: 9.5pt; color: #2563eb; margin-bottom: 4px; }}
  ul {{ padding-left: 16px; }}
  li {{
    font-size: 9pt;
    color: #334155;
    margin-bottom: 2px;
    line-height: 1.5;
  }}
</style>
</head>
<body>
<h1>{profile.name}</h1>
<div class="contact">
  {profile.email} &nbsp;|&nbsp; {profile.phone or ''} &nbsp;|&nbsp;
  {profile.location} &nbsp;|&nbsp; {links_html}
</div>

<div class="section">
  <div class="section-title">Summary</div>
  <p class="summary">{tailored.get('summary', profile.summary)}</p>
</div>

<div class="section">
  <div class="section-title">Technical Skills</div>
  <p class="skills">{skills_html}</p>
</div>

<div class="section">
  <div class="section-title">Experience</div>
  {experience_html}
</div>

<div class="section">
  <div class="section-title">Education</div>
  {education_html}
</div>
{certifications_html}
</body>
</html>"""


# ── PDF generation ────────────────────────────────────────────────────────────

def generate_pdf(html: str, output_path: Path) -> bool:
    """Convert HTML to PDF using WeasyPrint."""
    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(output_path))
        return True
    except ImportError:
        console.print("[yellow]WeasyPrint not installed. Saving HTML instead.[/yellow]")
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html)
        console.print(f"[dim]Saved HTML to {html_path}[/dim]")
        return False
    except Exception as e:
        console.print(f"[red]PDF generation error: {e}[/red]")
        return False


# ── Main agent entry point ────────────────────────────────────────────────────

def run_tailoring(
    profile: UserProfile,
    job: JobPosting,
    with_cover_letter: bool = False,
) -> TailoredResume | None:
    """
    Full resume tailoring pipeline for a single job.

    Args:
        profile: Candidate profile.
        job: Job posting to tailor for.
        with_cover_letter: If True, also generate a cover letter PDF alongside
                           the resume. Defaults to False — resume only.

    Returns:
        TailoredResume with pdf_path set. If with_cover_letter=True,
        cover_letter_pdf_path is also populated.
    """
    console.print(f"\n[bold cyan]Agent 2: Tailoring resume for {job.company} — {job.title}[/bold cyan]")

    try:
        # Step 1: LLM resume tailoring
        console.print("  Calling Claude to tailor resume...")
        tailored_data = tailor_resume_with_llm(profile, job)
        console.print(f"  [green]✓[/green] Tailored — {len(tailored_data.get('keyword_matches', []))} keyword matches")

        # Step 2: Build resume HTML and generate PDF
        resume_html = build_resume_html(profile, tailored_data)
        filename = build_filename(profile, job)
        pdf_path = PDF_OUTPUT_DIR / filename
        console.print(f"  Generating resume PDF → {filename}")
        success = generate_pdf(resume_html, pdf_path)
        if not success:
            pdf_path = PDF_OUTPUT_DIR / filename.replace(".pdf", ".html")
        console.print(f"  [green]✓[/green] Resume saved to {pdf_path}")

        # Step 3 (optional): Cover letter
        cl_text = None
        cl_pdf_path = None
        if with_cover_letter:
            console.print("  Generating cover letter...")
            cl_text = generate_cover_letter(profile, job)
            cl_html = build_cover_letter_html(profile, job, cl_text)
            cl_filename = filename.replace(".pdf", "_coverletter.pdf")
            cl_path = PDF_OUTPUT_DIR / cl_filename
            cl_success = generate_pdf(cl_html, cl_path)
            if cl_success:
                cl_pdf_path = str(cl_path)
                console.print(f"  [green]✓[/green] Cover letter saved to {cl_path}")
            else:
                console.print("  [yellow]Cover letter PDF failed — skipping[/yellow]")

        return TailoredResume(
            job_id=job.id,
            company=job.company,
            position=job.title,
            resume_text=json.dumps(tailored_data, indent=2),
            resume_html=resume_html,
            pdf_path=str(pdf_path),
            filename=filename,
            tailoring_notes=tailored_data.get("tailoring_notes", ""),
            keyword_matches=tailored_data.get("keyword_matches", []),
            cover_letter_text=cl_text,
            cover_letter_pdf_path=cl_pdf_path,
        )

    except Exception as e:
        console.print(f"[red]Tailoring failed for {job.company}: {e}[/red]")
        import traceback
        traceback.print_exc()
        return None


# ── Cover letter (optional) ───────────────────────────────────────────────────

COVER_LETTER_PROMPT = """You are writing a concise, honest cover letter for a senior engineering role.

Candidate: {name}, {years_experience}+ years in robotics/ADAS/autonomous systems.
Applying to: {title} at {company}.

Job description excerpt:
{description}

Candidate's current summary:
{summary}

Write a 3-paragraph cover letter (no greeting, no sign-off — just the body paragraphs):
- Paragraph 1 (2-3 sentences): Why this specific role and company. Be concrete, not generic.
- Paragraph 2 (3-4 sentences): The 2-3 most relevant accomplishments from their background that map directly to this JD. Use numbers/impact where truthful.
- Paragraph 3 (1-2 sentences): Forward-looking close.

Rules: No clichés ("I am writing to express..."). No hollow flattery. Direct and specific.
Return plain text only — no markdown, no headers."""


def generate_cover_letter(profile: UserProfile, job: JobPosting) -> str:
    """Generate a targeted cover letter. Returns plain text."""
    prompt = COVER_LETTER_PROMPT.format(
        name=profile.name,
        years_experience=profile.years_experience,
        title=job.title,
        company=job.company,
        description=job.description[:2000],
        summary=profile.summary,
    )
    msg = _get_client().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def build_cover_letter_html(profile: UserProfile, job: JobPosting, body: str) -> str:
    """Wrap cover letter body in print-ready HTML."""
    from datetime import date
    today = date.today().strftime("%B %d, %Y")
    paragraphs = "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip())
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"/>
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 10.5pt;
         line-height: 1.7; color: #1a1a1a; padding: 0.9in 0.9in; max-width: 8.5in; }}
  .header {{ margin-bottom: 2rem; }}
  .name {{ font-size: 15pt; font-weight: 600; margin-bottom: 4px; }}
  .contact {{ font-size: 9pt; color: #555; }}
  .date {{ margin: 1.5rem 0 0.5rem; color: #333; }}
  .salutation {{ margin-bottom: 1rem; }}
  p {{ margin: 0 0 1rem; }}
  .sign-off {{ margin-top: 1.5rem; }}
</style>
</head>
<body>
<div class="header">
  <div class="name">{profile.name}</div>
  <div class="contact">{profile.email} &nbsp;|&nbsp; {profile.phone or ''} &nbsp;|&nbsp; {profile.location}</div>
</div>
<div class="date">{today}</div>
<div class="salutation">Dear Hiring Manager,</div>
{paragraphs}
<div class="sign-off">
  Sincerely,<br/><br/>
  {profile.name}
</div>
</body>
</html>"""
