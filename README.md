# Entwickler

> A self-evolving coding agent that writes, tests, and improves its own code — autonomously.

[![Evolve](https://github.com/rajdeep13-coder/Entwickler/actions/workflows/evolve.yml/badge.svg)](https://github.com/rajdeep13-coder/Entwickler/actions/workflows/evolve.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Stars](https://img.shields.io/github/stars/rajdeep13-coder/Entwickler?style=social)](https://github.com/rajdeep13-coder/Entwickler/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/rajdeep13-coder/Entwickler?style=social)](https://github.com/rajdeep13-coder/Entwickler/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/rajdeep13-coder/Entwickler)](https://github.com/rajdeep13-coder/Entwickler/issues)
[![Last Commit](https://img.shields.io/github/last-commit/rajdeep13-coder/Entwickler)](https://github.com/rajdeep13-coder/Entwickler/commits/main)

---

**[Fork this repo](https://github.com/rajdeep13-coder/Entwickler/fork)** &nbsp;|&nbsp;
**[Open an issue](https://github.com/rajdeep13-coder/Entwickler/issues/new)** &nbsp;|&nbsp;
**[View the journal](JOURNAL.md)** &nbsp;|&nbsp;
**[Watch it evolve](https://github.com/rajdeep13-coder/Entwickler/commits/main)**

---

## What is Entwickler?

**Entwickler** (German: *developer*) is a production-grade, self-evolving AI coding agent. It starts as a ~300-line Python script and autonomously grows into a powerful CLI tool capable of rivalling Aider, Claude Code, and Cursor agent mode — **without any human ever editing its code after the initial bootstrap.**

Every few hours, Entwickler wakes up via GitHub Actions, reads its own source code, reflects on what could be better, picks **one focused improvement**, implements it, runs tests, and — if everything passes — commits the change back to the repository. It writes its own history in `JOURNAL.md` and governs itself by `IDENTITY.md`.

---

## How It Works

```
+-------------------------------------------------------------+
|                  GitHub Actions (cron)                      |
|                    every 4 hours                            |
+-----------------------------+-------------------------------+
                              |
                       +------v------+
                       |  Read Self  |  <- .py files, IDENTITY.md,
                       |             |     JOURNAL.md, GitHub Issues
                       +------+------+
                              |
                       +------v------+
                       |  Assess &   |  <- LLM self-critique via
                       |  Prioritize |     skills/self_assess.yaml
                       +------+------+
                              |
                       +------v------+
                       |  Generate   |  <- Unified diff patch or
                       |  Patch      |     full-file rewrite
                       +------+------+
                              |
                       +------v------+
                       |  Apply on   |  <- directly on main
                       |  main       |     (in-place edit)
                       +------+------+
                              |
                       +------v------+
                       |  Run Tests  |  <- pytest + ruff + black
                       |  & Lint     |
                       +------+------+
                        pass? | fail?
              +---------------+--------------+
              |                              |
       +------v------+              +--------v----+
       |  Commit &   |              |  Revert     |
       |  Push to    |              |  in-place + |
       |  main       |              |  JOURNAL.md |
       +-------------+              +-------------+
```

### Core Rules
- No human edits the code after bootstrap — **only the agent commits**
- Every run picks **one** focused, incremental improvement
- All changes are tested before committing (pytest + ruff)
- Full history is preserved in `JOURNAL.md`
- Skills system (`skills/*.yaml`) defines the improvement strategies

---

## Setup

### 1. Fork & Clone
```bash
git clone https://github.com/your-username/Entwickler.git
cd Entwickler
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Secrets

Add these secrets to your GitHub repository (`Settings -> Secrets -> Actions`):

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (primary LLM) |
| `GEMINI_API_KEY` | Google Gemini API key (fallback) |
| `GROQ_API_KEY` | Groq/Llama API key (fast/cheap fallback) |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions |

You need at least **one** LLM API key.

### 4. Create `.env` for Local Development
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 5. Run Manually
```bash
python entwickler.py
```

### 6. Watch It Evolve

GitHub Actions runs the agent automatically every 4 hours. Watch the commits roll in:
```bash
git log --oneline --all
```

Or check the `JOURNAL.md` for a narrative history of every evolution attempt.

---

## Project Structure

```
Entwickler/
+-- entwickler.py          # Main agent bootstrap (self-modifying)
+-- IDENTITY.md            # Agent constitution & goals
+-- JOURNAL.md             # Auto-generated evolution history
+-- requirements.txt       # Python dependencies
+-- test_entwickler.py     # Initial test suite (grows over time)
+-- skills/
|   +-- self_assess.yaml   # Self-assessment skill definition
|   +-- *.yaml             # More skills added by agent over time
+-- .github/
    +-- workflows/
        +-- evolve.yml     # GitHub Actions cron job
```

---

## Supported LLM Providers

Entwickler uses [LiteLLM](https://github.com/BerriAI/litellm) for a unified multi-provider interface:

- **Anthropic Claude** (claude-3-5-sonnet, claude-3-opus)
- **Google Gemini** (gemini-1.5-pro, gemini-2.0-flash)
- **Groq** (llama-3.1-70b, llama-3.1-405b) — fastest, cheapest
- **DeepSeek** (deepseek-coder, deepseek-chat)
- **Mistral** (mistral-large, codestral)
- **Cohere** (command-r-plus)

The agent auto-selects providers based on cost/availability and falls back gracefully.

---

## Skills System

Skills are YAML-defined behaviors loaded at runtime from `skills/`. Each skill describes:
- **name**: skill identifier
- **description**: what it does
- **priority**: importance level (critical/high/medium/low)
- **prompt_template**: the LLM prompt to use
- **validation**: how to verify success

The agent accumulates skills over time as it discovers new improvement strategies.

---

## Watching It Grow

```bash
# See all evolution commits
git log --oneline | grep "evolve:"

# Read the journal
cat JOURNAL.md

# Check what skills have been added
ls skills/

# Run the test suite to see how far it's come
pytest test_entwickler.py -v
```

---

## FAQ

### Is it fully working?

Yes — with at least one LLM API key configured, the agent will run a complete evolution cycle:
it reads its own source, asks the LLM to identify one improvement, generates a patch, applies
it on a feature branch, runs `pytest` and `ruff`, and either merges to `main` (on success) or
reverts and writes the failure to `JOURNAL.md`. The bootstrap version is deliberately small and
conservative; it grows from there.

Set at least one of `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `GROQ_API_KEY` in your repo
secrets, then trigger the workflow manually from the Actions tab to see the first run.

### Can I deploy it to GitHub Pages?

No — this is a Python CLI agent, not a web application. GitHub Pages serves static HTML/CSS/JS
and cannot run a Python process. The agent runs entirely inside GitHub Actions workers. The
`JOURNAL.md` and `README.md` serve as the "live dashboard" you can read on GitHub without
any separate deployment.

### How do I suggest an improvement?

Open a GitHub Issue and add the `agent-input` label. The agent reads these issues on every
waking cycle and decides whether to act on the suggestion.

### Why does the agent pick small changes?

Small changes have a high probability of passing tests. The agent compounds many small correct
changes rather than making one large risky change that is likely to fail.

### How often does the agent evolve? Will it improve itself every hour?

By default, the agent runs **every 4 hours** via a GitHub Actions cron schedule (`0 */4 * * *`).
This is intentional — each evolution cycle makes one LLM call, so running every 4 hours balances
improvement speed against API cost. If you want it to run every hour, you can edit
`.github/workflows/evolve.yml` and change the cron line to `0 * * * *`.

---

## Philosophy

Entwickler embodies **German engineering precision**: systematic, thorough, iterative. No shortcuts, no duct tape. If a change doesn't pass tests, it doesn't ship. If it's not logged, it didn't happen.

It starts small and **earns** its complexity — one verified improvement at a time.

---

## Contributors

| Contributor | Role |
|-------------|------|
| [![rajdeep13-coder](https://avatars.githubusercontent.com/rajdeep13-coder?size=40)](https://github.com/rajdeep13-coder) **[rajdeep13-coder](https://github.com/rajdeep13-coder)** | Human creator & maintainer |
| [![github-actions[bot]](https://avatars.githubusercontent.com/in/15368?size=40)](https://github.com/apps/github-actions) **[github-actions[bot]](https://github.com/apps/github-actions)** | Entwickler Agent — autonomous self-evolution commits |

> The bot commits directly to this repository on every successful evolution cycle. Both contributors are visible on the [GitHub Contributors page](https://github.com/rajdeep13-coder/Entwickler/graphs/contributors).

---

## Contributing

You don't contribute code directly. You contribute **ideas**:

1. Open a GitHub Issue labeled `agent-input`
2. Describe the improvement you want to see
3. The agent will read it on its next waking cycle and decide whether to act on it

The agent also opens its own `agent-self` issues when it identifies problems it wants to address.

---

## License

MIT — see [LICENSE](LICENSE)

---

*"Ordnung muss sein." — There must be order.*