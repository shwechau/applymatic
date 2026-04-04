"""
Parse an existing resume file (.docx or .pdf) and extract structured profile data.
"""
import json
import os
from pathlib import Path
import anthropic
from rich.console import Console
from core.models import UserProfile

console = Console()
def _get_client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def parse_resume_file(file_path: str) -> UserProfile:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    ext = path.suffix.lower()
    text = ""

    if ext == ".docx":
        text = _extract_docx(path)
    elif ext == ".pdf":
        text = _extract_pdf(path)
    elif ext in (".txt", ".md"):
        text = path.read_text()
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    console.print(f"Extracted {len(text)} characters from resume. Parsing with Claude...")
    return _parse_with_llm(text)


def _extract_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_pdf(path: Path) -> str:
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        console.print(f"[yellow]PyPDF2 failed ({e}). Trying pdfminer...[/yellow]")
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path))
        except Exception as e2:
            console.print(f"[red]PDF extraction failed: {e2}[/red]")
            return ""


def _parse_with_llm(resume_text: str) -> UserProfile:
    prompt = f"""Parse this resume and extract structured data.

RESUME TEXT:
{resume_text[:6000]}

Respond with valid JSON only, exactly matching this structure:
{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "+1-xxx-xxx-xxxx",
  "linkedin_url": "https://linkedin.com/in/...",
  "location": "City, State",
  "years_experience": <integer>,
  "current_title": "Most recent job title",
  "summary": "Professional summary or objective",
  "skills": ["C++", "Python", "ROS", ...],
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "dates": "Month Year - Month Year",
      "bullets": ["achievement 1", "achievement 2"]
    }}
  ],
  "education": [
    {{
      "degree": "MS Electrical Engineering",
      "school": "University Name",
      "year": "2015"
    }}
  ],
  "certifications": [],
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

    data = json.loads(text)
    return UserProfile.model_validate(data)
