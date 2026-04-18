# applymatic

AI-powered job application agent. Finds jobs, tailors your resume, fills ATS forms.

Built with Python · Claude AI · Playwright · WeasyPrint

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
# Edit .env and add: ANTHROPIC_API_KEY=sk-ant-...

# 3. Set up your profile
cp config/profile.example.json config/profile.json
# Edit config/profile.json with your details

# 4. Start the chat agent
python main_chat.py
```

That's it. Talk to it like you would to an assistant.

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
  [e6a4b9f] NVIDIA — Senior Systems Software Engineer (92)
  [d27dc7b] Aurora — Behavior Planning Engineer (91)
  [93919b3] Skild AI — Robotics Software Engineer (88)
  ...

You: tailor my resume for the NVIDIA job

Agent: Analyzing keyword gaps first...
  Current match: 71% → projected: 89% with 4 additions
  Suggested: "behavior trees", "Docker", "CI/CD", "CUDA"
  Say "go" to add all, or "skip Docker, CI/CD" to exclude any.

You: skip Docker and CI/CD

Agent: Tailoring with 2 keywords...
  Resume ready: shwetachauhan_nvidia_seniorswengineer.pdf
  Match score: 84%

You: apply to it

Agent: Opening Workday application form...
  Form filled. Please review in the browser, then click Submit.
```

---

## CLI commands (alternative to chat)

```bash
python main.py discover          # find matching jobs
python main.py tailor            # tailor resumes for all scored jobs
python main.py apply             # fill application forms
python main.py status            # show all tracked applications
python main.py add-job <url>     # add a specific job URL
```

---

## How it works

Three agents, each responsible for one thing:

```
Agent 1 (discover)   Search job boards → score against your profile → rank by match
Agent 2 (tailor)     Extract JD keywords → get your approval → rewrite resume → PDF
Agent 3 (apply)      Detect ATS platform → fill form fields → upload resume → review
```

Agents fail independently. If Agent 3 fails on one job, the others continue.

---

## Supported ATS platforms

- Workday (most common — NVIDIA, Amazon, many others)
- Greenhouse
- Lever
- Generic (basic form filling for anything else)

---

## Profile setup

Edit `config/profile.json` with your details. This is what the agent uses to fill forms and tailor resumes. See `config/profile.example.json` for the format.

Your profile stays local — it's never sent anywhere except to Claude's API for resume tailoring.

---

## Requirements

- Python 3.10+
- Anthropic API key (get one at console.anthropic.com — ~$5 for hundreds of applications)
- Chrome/Chromium (installed automatically by `playwright install chromium`)

---

## Want the hosted version?

If you don't want to run Python locally, the web version at **applymatic.io** has:
- Chat interface in your browser (no terminal needed)
- Resume upload and parsing
- Application history synced across devices
- 3 free applications, then $9/month

---

## License

MIT — use it however you want.
