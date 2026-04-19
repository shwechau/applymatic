# applymatic

AI-powered job application agent. Finds jobs, tailors your resume, fills ATS forms automatically.

Built with Python · Claude AI · Playwright · WeasyPrint

> **You need your own Anthropic API key to use this.**
> Get one free at [console.anthropic.com](https://console.anthropic.com) — costs ~.01 per application.

---

## Quickstart (5 minutes)
```bash
# 1. Clone and install
git clone https://github.com/shwechau/applymatic
cd applymatic
pip install -r requirements.txt
playwright install chromium

# 2. Add your API key
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY from console.anthropic.com

# 3. Set up your profile
cp config/profile.example.json config/profile.json
# Edit config/profile.json with your name, skills, experience

# 4. Start the chat agent
python main_chat.py
```

---
## Chat interface
```
╭──────────────────────────────────────╮
│        applymatic chat agent         │
│  Type what you want · Ctrl+C to quit │
╰──────────────────────────────────────╯

You: find me robotics engineering jobs with 85%+ match

Agent: Searching for robotics roles in the Bay Area...

Found 7 jobs:

[e6a4b9f] NVIDIA — Senior Systems Software Engineer (92%)
[d27dc7b] Aurora — SDE (91%)
[93919b3] Skild AI — Robotics Software Engineer (88%)

You: tailor my resume for the NVIDIA job

Agent: Analyzing keyword gaps...
Current match: 71% → projected: 89% with 4 additions
Suggested: "behavior trees", "Docker", "CI/CD", "CUDA"
Say "go" to add all, or "skip Docker, CI/CD" to exclude any.
You: skip Docker and CI/CD
Agent: Tailoring with 2 keywords...
Resume ready: yourname_nvidia_seniorswengineer.pdf
Match score: 84%
You: apply to it
Agent: Opening Workday application form...
Form filled. Please review in the browser, then click Submit.

## CLI commands

bash
python main.py discover          # find matching jobs
python main.py tailor            # tailor resumes for all scored jobs
python main.py apply             # fill application forms
python main.py status            # show all tracked applications
python main.py add-job <url>     # add a specific job URL
python main.py preferences       # configure auto-apply, cooldowns, exclusions
```

---

## How it works

Three agents, each responsible for one step:
Agent 1 — discover
Search job boards → score against your profile → rank by match %
Agent 2 — tailor
Extract JD keywords → show what will be added → rewrite resume → PDF
Agent 3 — apply
Detect ATS platform → map your data to form fields → fill → pause for review
Agents fail independently — if one job fails, the others continue.

---

## Reapplication cooldowns

The agent tracks rejections and enforces waiting periods automatically:

| Situation | Default wait |
|---|---|
| Same role, same company | 6 months |
| Different role, same company | 3 months |
| ATS rejection (no interview) | 1 month |

Run python main.py preferences to customize these.

---

## Supported ATS platforms

- Workday (most common — NVIDIA, Amazon, many others)
- Greenhouse
- Lever
- Generic (basic form filling for anything else)

---

## Requirements

- Python 3.10+
- Your own Anthropic API key — [console.anthropic.com](https://console.anthropic.com)
  - Cost: ~\.001 per chat message, ~\.01 per resume tailor
  - A \ credit covers hundreds of applications
- Chrome/Chromium (installed automatically via playwright install chromium)

---

## Profile setup

Edit config/profile.json with your real information. See config/profile.example.json for the format.

Your profile stays completely local — it is never sent anywhere except to the Anthropic API when Claude tailors your resume.

**Never commit config/profile.json** — it contains your personal information and is in .gitignore by default.

---

## Want the hosted version?

**[applymatic.io](https://applymatic.io)** has the same features in a web interface — no terminal required. Bring your own Anthropic API key, same as the CLI.

---

## License

MIT — use it however you want.
