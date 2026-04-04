# JobApply — Automated Job Application Agent

Automated job discovery, resume tailoring, and application for robotics/ADAS/AV engineers.

## Quick Start (5 minutes)

### 1. Install dependencies
```bash
cd jobapply
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure your environment
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Set up your profile
```bash
# From your LinkedIn URL (best option):
python main.py setup-profile --linkedin https://www.linkedin.com/in/your-profile

# From existing resume file:
python main.py setup-profile --resume /path/to/resume.docx

# Or interactively:
python main.py setup-profile
```

### 4. Run the pipeline
```bash
# Discover matching jobs:
python main.py discover

# Tailor resumes for each job:
python main.py tailor

# Fill out application forms (with human review):
python main.py apply

# Or run everything at once:
python main.py run
```

### 5. Check your application status
```bash
python main.py status
```

## Commands

| Command | Description |
|---------|-------------|
| `python main.py setup-profile` | Extract your profile from LinkedIn or resume |
| `python main.py discover` | Find matching jobs in Bay Area |
| `python main.py tailor` | Generate tailored PDFs for all discovered jobs |
| `python main.py apply` | Fill forms and open for review |
| `python main.py run` | Full pipeline in one shot |
| `python main.py status` | Application tracker dashboard |
| `python main.py edit-profile` | Edit your profile JSON manually |

## Configuration (.env)

```
ANTHROPIC_API_KEY=sk-ant-...        # Required
OWNER_NAME=Your Name                # Your name
OWNER_EMAIL=you@email.com           # Your email
LINKEDIN_URL=https://...            # Your LinkedIn
TARGET_LOCATION=San Francisco Bay Area
TARGET_ROLES=Robotics Software Engineer,Senior Software Engineer motion planning
MIN_MATCH_SCORE=70                  # 0-100, only apply to jobs above this
MAX_JOBS_PER_RUN=10
HUMAN_REVIEW=true                   # Always review before submitting
DRY_RUN=true                        # Fill forms but don't submit (set false when ready)
JSEARCH_API_KEY=                    # Optional: better job search (rapidapi.com)
```

## Output

- Tailored PDFs saved to `output/pdfs/shwetachauhan_nvidia_motionplanningengineer.pdf`
- Application tracker at `output/applications.json`

## ATS Platform Support

| Platform | Status |
|----------|--------|
| Greenhouse | ✅ Full support |
| Lever | ✅ Full support |
| Workday | 🚧 Day 4-5 (complex multi-step) |
| iCIMS | 🚧 Coming soon |
| Generic | ✅ Best-effort fill |

## Open Source

Core agent logic is MIT licensed. Fork it, self-host it, customize it.
