from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ApplicationStatus(str, Enum):
    DISCOVERED = "discovered"
    SCORED = "scored"
    RESUME_TAILORED = "resume_tailored"
    PDF_READY = "pdf_ready"
    FORM_FILLED = "form_filled"
    AWAITING_REVIEW = "awaiting_review"
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    ERROR = "error"


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str  # linkedin, indeed, etc.
    posted_date: Optional[str] = None
    salary_range: Optional[str] = None
    job_type: Optional[str] = None  # full-time, contract, etc.
    ats_platform: Optional[str] = None  # workday, greenhouse, lever, icims
    match_score: Optional[float] = None
    match_reasons: Optional[list[str]] = None
    discovered_at: datetime = Field(default_factory=datetime.now)


class UserProfile(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: str
    years_experience: int
    current_title: str
    summary: str
    skills: list[str]
    experience: list[dict]  # [{title, company, dates, bullets}]
    education: list[dict]   # [{degree, school, year}]
    certifications: Optional[list[str]] = None
    github_url: Optional[str] = None
    website_url: Optional[str] = None


class TailoredResume(BaseModel):
    job_id: str
    company: str
    position: str
    resume_text: str                         # full resume as markdown/text
    resume_html: str                         # rendered HTML for PDF
    pdf_path: str                            # path to generated resume PDF
    filename: str                            # shwetachauhan_nvidia_motionplanning.pdf
    tailoring_notes: str                     # what was changed and why
    keyword_matches: list[str]
    cover_letter_text: Optional[str] = None          # plain text, if generated
    cover_letter_pdf_path: Optional[str] = None      # PDF path, if generated
    created_at: datetime = Field(default_factory=datetime.now)


class ApplicationRecord(BaseModel):
    job: JobPosting
    resume: Optional[TailoredResume] = None
    status: ApplicationStatus = ApplicationStatus.DISCOVERED
    error_message: Optional[str] = None
    submitted_at: Optional[datetime] = None
    notes: Optional[str] = None
