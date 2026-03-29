#!/usr/bin/env python3
"""
Entwickler — A self-evolving coding agent.

Bootstrap version: 1.0.0
Philosophy: Start small, test everything, improve incrementally, commit only on success.

This script is the seed of a self-improving AI coding agent. It reads its own source,
assesses what could be better, generates a precise patch, tests it, and commits if
all checks pass. No human edits this file after bootstrap — only the agent commits.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import sys
import textwrap
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
log = logging.getLogger("entwickler")

REPO_ROOT = Path(__file__).parent.resolve()
JOURNAL_FILE = REPO_ROOT / "JOURNAL.md"
IDENTITY_FILE = REPO_ROOT / "IDENTITY.md"
SKILLS_DIR = REPO_ROOT / "skills"

# GitHub API base
GITHUB_API = "https://api.github.com"

# ---------------------------------------------------------------------------
# Tuning constants (extracted for readability and easy adjustment)
# ---------------------------------------------------------------------------

# Approximate ratio of tokens to words in typical Python/code+text content.
# Evidence from production journal: actual Groq-measured token counts are ~2.1x
# the naive word-split count, so 1.8 gives a conservative (safe) buffer.
TOKEN_TO_WORD_RATIO: float = 1.8

# Journal compaction: if journal exceeds this length, keep only the tail
JOURNAL_MAX_LENGTH: int = 8000
JOURNAL_KEEP_LENGTH: int = 5000

# Context assembly: how many chars of source to include per file preview
MAX_SOURCE_PREVIEW_LENGTH: int = 1500

# Context assembly: max number of source files to include in the summary
MAX_FILES_IN_SUMMARY: int = 3

# Context assembly: max chars of recent journal to send to LLM
JOURNAL_RECENT_CHARS: int = 1500

# Context assembly: max chars of IDENTITY.md to include in prompt
IDENTITY_MAX_CHARS: int = 1000

# Journal: max chars of check output to log per check
CHECK_OUTPUT_MAX_CHARS: int = 4000

# ---------------------------------------------------------------------------
# Secret Audit Configuration
# ---------------------------------------------------------------------------

# Regex patterns that strongly indicate a real API key.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Google/Gemini API key", re.compile(r"AIzaSy[0-9A-Za-z_-]{33}")),
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    # OpenRouter keys start with sk-or-v1- followed by an alphanumeric payload (~48 chars typical).
    ("OpenRouter API key", re.compile(r"sk-or-v1-[A-Za-z0-9]{32,96}")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub PAT (classic)", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub PAT (fine-grained)", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
]

# File extensions the secret audit will scan.
_SCANNABLE_EXTENSIONS: set[str] = {
    ".py", ".yml", ".yaml", ".json", ".toml",
    ".cfg", ".ini", ".md", ".txt", ".sh", ".env",
}

# ---------------------------------------------------------------------------
# LLM Provider Configuration
# ---------------------------------------------------------------------------

# Ordered by preference: fastest/cheapest first, most capable last as fallback.
LLM_PROVIDERS: list[dict[str, Any]] = [
    {
        "name": "groq-llama3",
        "model": "groq/llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
        "max_tokens": 8192,
        # Free tier TPM cap is 12 000/min; leaving headroom for burst usage.
        "max_input_tokens": 6000,
        "cost_per_1k_input": 0.0006,
    },
    {
        "name": "groq-llama3-fast",
        "model": "groq/llama-3.1-8b-instant",
        "env_key": "GROQ_API_KEY",
        "max_tokens": 8192,
        # Free tier TPM cap is 6 000/min; keep well under to survive burst.
        "max_input_tokens": 3000,
        "cost_per_1k_input": 0.0001,
    },
    {
        "name": "gemini-flash",
        "model": "gemini/gemini-2.0-flash",
        "env_key": "GEMINI_API_KEY",
        "max_tokens": 8192,
        # Tightened from 8 000 to account for TOKEN_TO_WORD_RATIO under-estimation.
        "max_input_tokens": 6000,
        "cost_per_1k_input": 0.0001,
    },
    {
        "name": "deepseek-coder",
        "model": "deepseek/deepseek-coder",
        "env_key": "DEEPSEEK_API_KEY",
        "max_tokens": 8192,
        "max_input_tokens": 8192,
        "cost_per_1k_input": 0.00014,
    },
    {
        "name": "openrouter",
        # OpenRouter uses slash-separated provider/model identifiers.
        "model": "openrouter/anthropic/claude-3.5-sonnet",
        "env_key": "OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1",
        "max_tokens": 8192,
        "max_input_tokens": 8192,
        # Pricing varies by routed model; this estimates Claude 3.5 Sonnet input cost.
        "cost_per_1k_input": 0.003,
    },
    {
        "name": "anthropic-claude",
        "model": "anthropic/claude-3-5-sonnet-20241022",
        "env_key": "ANTHROPIC_API_KEY",
        "max_tokens": 8192,
        "max_input_tokens": 8192,
        "cost_per_1k_input": 0.003,
    },
    {
        "name": "mistral",
        "model": "mistral/mistral-small-latest",
        "env_key": "MISTRAL_API_KEY",
        "max_tokens": 8192,
        "max_input_tokens": 8192,
        "cost_per_1k_input": 0.001,
    },
    {
        "name": "cohere",
        "model": "cohere/command-r",
        "env_key": "COHERE_API_KEY",
        "max_tokens": 4096,
        "max_input_tokens": 4096,
        "cost_per_1k_input": 0.0005,
    },
    {
        "name": "github-models",
        "model": "github/gpt-4o-mini",
        "env_key": "GITHUB_TOKEN",
        "max_tokens": 4096,
        # Tightened from 8 000 to account for TOKEN_TO_WORD_RATIO under-estimation.
        "max_input_tokens": 6000,
        "cost_per_1k_input": 0.0,
    },
]


def get_available_provider() -> dict[str, Any] | None:
    """Return first provider with a configured API key."""
    for provider in LLM_PROVIDERS:
        if os.environ.get(provider["env_key"]):
            return provider
    return None


def call_llm(prompt: str, system: str = "", max_tokens: int = 4096) -> str:
    """
    Call the LLM with graceful fallback across providers.

    Returns the text response or raises RuntimeError if all providers fail.
    """
    try:
        import litellm  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("litellm not installed — run: pip install litellm") from exc

    available = [p for p in LLM_PROVIDERS if os.environ.get(p["env_key"])]
    if not available:
        raise RuntimeError(
            "No LLM API key found. Set one of: "
            + ", ".join(p["env_key"] for p in LLM_PROVIDERS)
        )

    last_errors: list[str] = []

    for provider in available:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})

        prompt_for_provider = prompt
        system_words = system.split() if system else []
        prompt_words = prompt_for_provider.split()
        max_input_tokens = provider.get("max_input_tokens", provider["max_tokens"])
        estimated_input_tokens = (len(system_words) + len(prompt_words)) * TOKEN_TO_WORD_RATIO
        original_input_tokens = estimated_input_tokens

        if estimated_input_tokens > max_input_tokens:
            allowed_prompt_words = max(
                int(max_input_tokens / TOKEN_TO_WORD_RATIO) - len(system_words),
                0,
            )
            if len(prompt_words) > allowed_prompt_words:
                log.warning(
                    f"Prompt too large for {provider['name']} (est. {estimated_input_tokens:.0f} tokens) — truncating to fit limit {max_input_tokens}"
                )
                prompt_words = prompt_words[:allowed_prompt_words]
                prompt_for_provider = " ".join(prompt_words)
                estimated_input_tokens = (len(system_words) + len(prompt_words)) * TOKEN_TO_WORD_RATIO
                log.info(
                    f"Truncated prompt from ~{original_input_tokens:.0f} to ~{estimated_input_tokens:.0f} tokens for provider {provider['name']}"
                )

        messages.append({"role": "user", "content": prompt_for_provider})
        final_prompt_words = prompt_words

        log.info(f"Calling LLM: {provider['name']} ({provider['model']})")

        # Estimate cost using token-to-word ratio approximation
        # This estimate reflects the final (possibly truncated) prompt actually sent.
        token_estimate = (len(final_prompt_words) + len(system_words)) * TOKEN_TO_WORD_RATIO
        cost_estimate = (token_estimate / 1000) * provider["cost_per_1k_input"]
        log.info(f"Estimated cost: ~${cost_estimate:.4f} ({token_estimate:.0f} tokens)")

        retries = 2
        for attempt in range(retries):
            try:
                request_kwargs: dict[str, Any] = {}
                if provider.get("api_base"):
                    request_kwargs["api_base"] = provider["api_base"]
                response = litellm.completion(
                    model=provider["model"],
                    messages=messages,
                    max_tokens=min(max_tokens, provider["max_tokens"]),
                    api_key=os.environ.get(provider["env_key"]),
                    **request_kwargs,
                )
                return response.choices[0].message.content or ""
            except litellm.RateLimitError as e:
                if attempt < retries - 1:
                    wait = 2 ** attempt  # 1s then 2s
                    log.warning(f"Provider {provider['name']} rate-limited, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    log.warning(f"Provider {provider['name']} failed: {e} — trying next provider")
                    last_errors.append(f"{provider['name']}: {e}")
            except Exception as e:
                log.warning(f"Provider {provider['name']} failed: {e} — trying next provider")
                last_errors.append(f"{provider['name']}: {e}")
                break

    raise RuntimeError("All LLM providers failed:\n" + "\n".join(last_errors))


# ---------------------------------------------------------------------------
# Skills System
# ---------------------------------------------------------------------------


def load_skills() -> list[dict[str, Any]]:
    """Load all skill definitions from skills/*.yaml."""
    skills: list[dict[str, Any]] = []
    if not SKILLS_DIR.exists():
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        return skills

    for skill_file in sorted(SKILLS_DIR.glob("*.yaml")):
        try:
            with open(skill_file) as f:
                skill = yaml.safe_load(f)
                if skill:
                    skills.append(skill)
        except Exception as e:
            log.warning(f"Failed to load skill {skill_file}: {e}")

    log.info(f"Loaded {len(skills)} skill(s): {[s.get('name', '?') for s in skills]}")
    return skills


def _recent_journal_categories(journal: str, max_entries: int = 5) -> list[str]:
    """Extract category values from recent journal entries (newest first)."""
    return re.findall(r"\*\*Category\*\*:\s*(\w+)", journal)[:max_entries]


def select_skill(skills: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any] | None:
    """Select a skill, rotating to avoid repeating recent categories.

    Logic:
    1. Look at the categories of the last few journal entries.
    2. Prefer skills whose category has NOT been attempted recently.
    3. Among those, pick randomly (weighted by inverse priority rank) so
       that different skills get a chance across cycles.
    4. Fall back to all skills if every category was recently attempted.
    """
    import random

    if not skills:
        return None

    journal = context.get("journal", "")
    recent_cats = _recent_journal_categories(journal)

    # Separate skills into "fresh" (category not recently tried) and "rest"
    fresh = [s for s in skills if s.get("category", "") not in recent_cats]
    pool = fresh if fresh else skills

    # Weighted random selection: all skills get a chance, not just the highest.
    # Higher numeric weight = higher chance of being picked by random.choices().
    # Low-priority skills get *higher* weights so they aren't starved out.
    priority_weight = {"critical": 1, "high": 2, "medium": 3, "low": 4}
    weights = [priority_weight.get(s.get("priority", "low"), 3) for s in pool]
    return random.choices(pool, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Code Reading & Context Building
# ---------------------------------------------------------------------------


def read_source_files() -> dict[str, str]:
    """Read all Python source files in the repo."""
    sources: dict[str, str] = {}
    for py_file in sorted(REPO_ROOT.glob("**/*.py")):
        # Skip hidden dirs, __pycache__, venv, etc.
        parts = py_file.relative_to(REPO_ROOT).parts
        if any(p.startswith(".") or p in {"__pycache__", "venv", ".venv", "node_modules"} for p in parts):
            continue
        try:
            sources[str(py_file.relative_to(REPO_ROOT))] = py_file.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"Could not read {py_file}: {e}")
    return sources


def read_markdown(path: Path) -> str:
    """Read a markdown file, returning empty string if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def fetch_github_issues(label: str = "agent-input") -> list[dict[str, Any]]:
    """Fetch open GitHub Issues with the given label."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        log.warning("GITHUB_TOKEN or GITHUB_REPOSITORY not set — skipping issue fetch")
        return []

    try:
        import requests  # type: ignore[import-untyped]

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        url = f"{GITHUB_API}/repos/{repo}/issues"
        params = {"labels": label, "state": "open", "per_page": 10}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        issues = resp.json()
        log.info(f"Fetched {len(issues)} issue(s) labeled '{label}'")
        return issues  # type: ignore[return-value]
    except Exception as e:
        log.warning(f"Failed to fetch GitHub issues: {e}")
        return []


def build_context() -> dict[str, Any]:
    """Assemble the full context for the evolution cycle."""
    sources = read_source_files()
    identity = read_markdown(IDENTITY_FILE)
    journal = read_markdown(JOURNAL_FILE)
    skills = load_skills()
    issues = fetch_github_issues("agent-input") + fetch_github_issues("agent-self")

    # Compact journal if it's very long (keep last JOURNAL_KEEP_LENGTH chars)
    if len(journal) > JOURNAL_MAX_LENGTH:
        journal = "...[earlier entries compacted]...\n\n" + journal[-JOURNAL_KEEP_LENGTH:]

    return {
        "sources": sources,
        "identity": identity,
        "journal": journal,
        "skills": skills,
        "issues": issues,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Self-Assessment
# ---------------------------------------------------------------------------

SELF_ASSESS_SYSTEM = textwrap.dedent("""\
    You are Entwickler, a self-evolving coding agent performing a critical self-assessment.
    Your goal is to identify the SINGLE most impactful improvement you can make to your own codebase right now.
    Be precise, focused, and pragmatic. Small correct changes beat large risky ones.

    VARIETY IS KEY — do NOT keep picking the same category every cycle:
    - The "Suggested Focus" section tells you which skill/category to focus on THIS cycle.
      Follow it! If it says "add_test", propose a test. If it says "refactor", propose a
      refactoring. If it says "optimize", propose a performance improvement.
    - The "Recently attempted categories" section lists categories already tried.
      AVOID proposing the same category again — pick something different.
    - Cycle through ALL categories over time: test, bug, architecture, performance, ux, feature.
    - Security is already RESOLVED — do NOT propose security improvements.

    Rules for reading the journal:
    - If the most recent journal entry records a FAILURE for the same category as your top candidate improvement, deprioritize that category and pick the next most impactful improvement instead.
    - If the journal contains a SUCCESS entry for a topic, treat that topic as RESOLVED — do NOT propose it again.
    - Never propose adding or changing environment variables / API keys.
    - Focus only on improvements to the Python source code or test suite in the repository.
    CRITICAL RULES — violations will cause automatic failure:
    - NEVER propose changes to LLM API keys, environment variables, secrets, or provider configuration. The fact that you are responding proves the LLM is working. Any such proposal will be rejected.
    - NEVER add new package imports (e.g. cryptography, keyring) that are not already used in the codebase.
    - NEVER remove or rename existing public functions — this will break tests.
    - NEVER replace an entire large file — use targeted, minimal changes.
    - Prefer adding new tests, fixing bugs, or improving existing code over adding new features.
""")

SELF_ASSESS_PROMPT = textwrap.dedent("""\
    ## Current Source Code
    {source_summary}

    ## Identity / Constitution
    {identity}

    ## Recent Journal
    {journal_recent}

    ## Open Issues (human input + self-generated)
    {issues_summary}

    ## Active Skills
    {skills_summary}

    ## Suggested Focus (from Skills System)
    {selected_skill_hint}

    ## Recently attempted categories (AVOID these — pick something DIFFERENT)
    {recent_categories}

    ---

    Perform a thorough self-assessment. Identify the SINGLE most valuable improvement to make.
    IMPORTANT: Do NOT pick a category listed in "Recently attempted categories" above.
    Instead, choose from the categories that have NOT been tried recently.
    Respond in this exact JSON format:
    {{
      "priority": "critical|high|medium|low",
      "category": "bug|security|architecture|test|performance|ux|feature",
      "title": "Short title of improvement",
      "rationale": "Why this is the most important thing to fix right now",
      "approach": "Precise description of the code change needed",
      "files_to_modify": ["list", "of", "files"],
      "test_strategy": "How to verify this works"
    }}

    Respond ONLY with the JSON object, no prose before or after.
""")


def self_assess(context: dict[str, Any]) -> dict[str, Any]:
    """Ask the LLM to assess the codebase and choose one improvement."""
    sources = context["sources"]
    source_summary = "\n\n".join(
        f"### {fname}\n```python\n{content[:MAX_SOURCE_PREVIEW_LENGTH]}"
        f"{'...' if len(content) > MAX_SOURCE_PREVIEW_LENGTH else ''}\n```"
        for fname, content in list(sources.items())[:MAX_FILES_IN_SUMMARY]
    )

    issues_summary = "\n".join(
        f"- #{i.get('number', '?')}: {i.get('title', '?')} — {i.get('body', '')[:200]}"
        for i in context["issues"][:5]
    ) or "No open issues."

    skills_summary = "\n".join(
        f"- {s.get('name', '?')}: {s.get('description', '?')}"
        for s in context["skills"]
    ) or "Only bootstrap skills loaded."

    journal_recent = (
        context["journal"][-JOURNAL_RECENT_CHARS:] if context["journal"] else "No journal entries yet."
    )

    # Tell the LLM which categories were recently attempted so it avoids them.
    recent_cats = _recent_journal_categories(context.get("journal", ""))
    if recent_cats:
        recent_categories = ", ".join(dict.fromkeys(recent_cats))  # unique, ordered
    else:
        recent_categories = "None yet — feel free to pick any category."

    skill = context.get("selected_skill")
    if skill:
        selected_skill_hint = f"Apply skill '{skill.get('name', '?')}': {skill.get('description', '?')}"
    else:
        selected_skill_hint = "No specific skill selected — use your own judgment."

    prompt = SELF_ASSESS_PROMPT.format(
        source_summary=source_summary,
        identity=context["identity"][:IDENTITY_MAX_CHARS],
        journal_recent=journal_recent,
        issues_summary=issues_summary,
        skills_summary=skills_summary,
        selected_skill_hint=selected_skill_hint,
        recent_categories=recent_categories,
    )

    response = call_llm(prompt, system=SELF_ASSESS_SYSTEM)

    # Extract JSON from response (handle markdown code fences)
    json_match = re.search(r"\{.*\}", response, re.DOTALL)
    if not json_match:
        raise ValueError(f"LLM did not return valid JSON:\n{response[:500]}")

    assessment = json.loads(json_match.group())
    log.info(f"Assessment: [{assessment.get('priority', '?').upper()}] {assessment.get('title', '?')}")
    return assessment  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Patch Generation
# ---------------------------------------------------------------------------

PATCH_SYSTEM = textwrap.dedent("""\
    You are Entwickler, a self-evolving coding agent. You are implementing a specific code improvement.
    Generate a precise, minimal, correct code change. Follow these rules:
    1. If the file is small (<150 lines), return the COMPLETE new file content.
    2. If the file is large (>=150 lines), you MUST return a unified diff (--- a/file +++ b/file format).
       NEVER return a complete file replacement for large files — you will lose existing functions.
    3. A unified diff must only change the lines relevant to the improvement; all other lines stay identical.
    4. Include proper Python 3.11+ type hints.
    5. Follow PEP 8 style. Do NOT add or remove imports that are unrelated to the change.
    6. Add docstrings where missing only for functions you are adding or modifying.
    7. Always include test code if you add new functionality.
    CRITICAL CONSTRAINTS — violating these causes automatic rejection:
    - NEVER add imports for packages not already in requirements.txt (e.g. no cryptography, keyring, vault).
    - NEVER remove or rename existing functions or classes.
    - NEVER modify LLM provider configuration, API key handling, or environment variable loading.
    - NEVER replace the entire content of a large file (>=150 lines). Use unified diff.
    - Preserve ALL existing tests when modifying test files — only ADD new tests.
""")

PATCH_PROMPT = textwrap.dedent("""\
    ## Improvement to implement:
    **Title**: {title}
    **Category**: {category}
    **Rationale**: {rationale}
    **Approach**: {approach}
    **Files to modify**: {files_to_modify}
    **Test strategy**: {test_strategy}

    ## Current file contents:
    {file_contents}

    ---

    Generate the implementation. For each file to modify, provide either:
    A) Complete new file content wrapped in:
       ```python:path/to/file.py
       <complete file content>
       ```
    B) Unified diff wrapped in:
       ```diff:path/to/file.py
       <unified diff>
       ```

    Generate ONLY code blocks, no prose explanations.
""")


def generate_patch(assessment: dict[str, Any], sources: dict[str, str]) -> dict[str, str]:
    """Ask the LLM to generate a code patch based on the assessment."""
    files_to_modify = assessment.get("files_to_modify", [])

    # Gather current content of files to modify
    file_contents = ""
    for fname in files_to_modify:
        content = sources.get(fname, "")
        if not content:
            # Try reading directly
            fpath = REPO_ROOT / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8")
        # Send full file content — truncation causes the LLM to generate incomplete
        # replacements that destroy functions beyond the truncation point.
        file_contents += f"\n### {fname}\n```python\n{content}\n```\n"

    prompt = PATCH_PROMPT.format(
        title=assessment.get("title", ""),
        category=assessment.get("category", ""),
        rationale=assessment.get("rationale", ""),
        approach=assessment.get("approach", ""),
        files_to_modify=", ".join(files_to_modify),
        test_strategy=assessment.get("test_strategy", ""),
        file_contents=file_contents,
    )

    response = call_llm(prompt, system=PATCH_SYSTEM, max_tokens=6144)
    return parse_patch_response(response)


def parse_patch_response(response: str) -> dict[str, str]:
    """
    Parse LLM response into a mapping of filepath -> new content.
    Handles both complete file blocks (any language tag) and unified diff blocks.
    """
    patches: dict[str, str] = {}

    # Match ```<any-lang>:path/to/file blocks — language tag is just a hint.
    # Examples: ```python:foo.py  ```diff:foo.py  ```env:.env  ```yaml:config.yml
    pattern = re.compile(
        r"```(?P<type>[a-zA-Z0-9_+-]*):(?P<path>[^\n]+)\n(?P<content>.*?)```",
        re.DOTALL,
    )

    for match in pattern.finditer(response):
        block_type = match.group("type").lower()
        fpath = match.group("path").strip()
        content = match.group("content")

        if block_type == "diff":
            # Apply unified diff to existing file
            existing = ""
            full_path = REPO_ROOT / fpath
            if full_path.exists():
                existing = full_path.read_text(encoding="utf-8")
            patched = apply_unified_diff(existing, content)
            if patched is not None:
                patches[fpath] = patched
            else:
                log.warning(f"Failed to apply diff to {fpath}, skipping")
        else:
            # Any other tag (python, env, yaml, bash, text, …) → full file replacement
            patches[fpath] = content

    if not patches:
        log.debug(f"parse_patch_response: no parseable blocks found. Raw response (first 500 chars):\n{response[:500]}")

    return patches


def apply_unified_diff(original: str, diff_text: str) -> str | None:
    """
    Apply a unified diff string to original file content.
    Returns new content or None on failure.
    """
    try:
        original_lines = original.splitlines(keepends=True)
        diff_lines = diff_text.splitlines(keepends=True)

        # Use difflib's restore approach: apply patch manually
        result_lines: list[str] = []
        orig_idx = 0

        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("@@"):
                # Parse hunk header: @@ -start,count +start,count @@
                hunk_match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if not hunk_match:
                    i += 1
                    continue
                orig_start = int(hunk_match.group(1)) - 1  # 0-indexed
                # Copy unchanged lines up to this hunk
                while orig_idx < orig_start:
                    result_lines.append(original_lines[orig_idx])
                    orig_idx += 1
            elif line.startswith("-") and not line.startswith("---"):
                orig_idx += 1  # skip removed line
            elif line.startswith("+") and not line.startswith("+++"):
                result_lines.append(line[1:])  # add new line (strip '+')
            elif line.startswith(" "):
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1
            i += 1

        # Copy remaining lines
        result_lines.extend(original_lines[orig_idx:])
        return "".join(result_lines)
    except Exception as e:
        log.error(f"Diff application error: {e}")
        return None


def validate_python_syntax(content: str, filename: str) -> bool:
    """Validate Python syntax by parsing the AST."""
    try:
        ast.parse(content)
        return True
    except SyntaxError as e:
        log.error(f"Syntax error in {filename}: {e}")
        return False


# ---------------------------------------------------------------------------
# Safe Patch Application
# ---------------------------------------------------------------------------


def apply_patches(patches: dict[str, str]) -> dict[str, str]:
    """
    Apply patches to files, returning a backup of original content.
    Validates Python syntax before writing.
    """
    backups: dict[str, str] = {}

    for fpath, new_content in patches.items():
        full_path = REPO_ROOT / fpath

        # Validate syntax for Python files
        if fpath.endswith(".py") and not validate_python_syntax(new_content, fpath):
            raise ValueError(f"Generated code has syntax errors: {fpath}")

        # Backup original
        if full_path.exists():
            backups[fpath] = full_path.read_text(encoding="utf-8")
        else:
            backups[fpath] = ""  # new file marker

        # Write new content
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(new_content, encoding="utf-8")
        log.info(f"Applied patch to {fpath} ({len(new_content)} chars)")

    return backups


def revert_patches(backups: dict[str, str]) -> None:
    """Revert files to their backed-up state."""
    for fpath, original_content in backups.items():
        full_path = REPO_ROOT / fpath
        if original_content == "":
            # File was newly created — remove it
            if full_path.exists():
                full_path.unlink()
        else:
            full_path.write_text(original_content, encoding="utf-8")
    log.info(f"Reverted {len(backups)} file(s)")


# ---------------------------------------------------------------------------
# Test & Lint Runner
# ---------------------------------------------------------------------------


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a subprocess command, returning (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout, result.stderr


def run_tests() -> tuple[bool, str]:
    """Run pytest. Returns (passed, output)."""
    code, stdout, stderr = run_command(
        [sys.executable, "-m", "pytest", "test_entwickler.py", "-v", "--tb=short", "--no-header"]
    )
    output = stdout + stderr
    passed = code == 0
    log.info(f"Tests {'PASSED' if passed else 'FAILED'}")
    return passed, output


def run_lint() -> tuple[bool, str]:
    """Run ruff linter. Returns (passed, output)."""
    code, stdout, stderr = run_command(
        [sys.executable, "-m", "ruff", "check", "entwickler.py", "--select=E,F,W", "--ignore=E501"]
    )
    output = stdout + stderr
    passed = code == 0
    log.info(f"Lint {'PASSED' if passed else 'FAILED'}")
    return passed, output


def run_format_check() -> tuple[bool, str]:
    """Run black format check. Returns (passed, output)."""
    code, stdout, stderr = run_command(
        [sys.executable, "-m", "black", "--check", "--diff", "entwickler.py"]
    )
    output = stdout + stderr
    passed = code == 0
    log.info(f"Format check {'PASSED' if passed else 'FAILED'}")
    return passed, output


def audit_source_for_secrets() -> tuple[bool, str]:
    """Scan tracked source files for accidentally hardcoded API keys.

    Returns (passed, output) where *passed* is False when a potential secret
    is detected.  The check uses lightweight regex patterns that match common
    provider key formats (Google/Gemini, OpenAI, Anthropic, AWS, etc.).
    """
    # Files to ignore (test fixtures, example configs).
    _IGNORE_GLOBS = {".env.example", "test_entwickler.py"}

    findings: list[str] = []

    for src in sorted(REPO_ROOT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(REPO_ROOT)
        # Skip hidden dirs (e.g. .git), virtual-envs, and ignored files.
        parts = rel.parts
        if any(p.startswith(".") for p in parts) or "node_modules" in parts:
            continue
        if str(rel) in _IGNORE_GLOBS:
            continue
        # Only scan text-like files
        if src.suffix not in _SCANNABLE_EXTENSIONS:
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for label, pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(f"  {rel}: potential {label} detected near char {match.start()}")

    if findings:
        detail = "\n".join(findings)
        msg = f"SECRET AUDIT FAILED — {len(findings)} potential secret(s) found:\n{detail}"
        log.error(msg)
        return False, msg

    log.info("Secret audit PASSED — no hardcoded keys detected")
    return True, "No hardcoded secrets detected"


def run_all_checks() -> tuple[bool, dict[str, tuple[bool, str]]]:
    """Run tests + lint + secret audit. Returns (all_passed, results_dict)."""
    results: dict[str, tuple[bool, str]] = {}

    tests_passed, tests_output = run_tests()
    results["tests"] = (tests_passed, tests_output)

    lint_passed, lint_output = run_lint()
    results["lint"] = (lint_passed, lint_output)

    secrets_passed, secrets_output = audit_source_for_secrets()
    results["secrets"] = (secrets_passed, secrets_output)

    all_passed = tests_passed and lint_passed and secrets_passed
    return all_passed, results


# ---------------------------------------------------------------------------
# Git Operations
# ---------------------------------------------------------------------------


def git_commit_and_push(message: str, files: list[str]) -> bool:
    """Stage files, commit, and push to origin."""
    # Stage files
    for fpath in files:
        code, _, stderr = run_command(["git", "add", fpath])
        if code != 0:
            log.error(f"Failed to git add {fpath}: {stderr}")
            return False

    # Commit
    code, _, stderr = run_command(["git", "commit", "-m", message])
    if code != 0:
        log.error(f"Failed to commit: {stderr}")
        return False

    # Push
    branch = get_current_branch()
    code, _, stderr = run_command(["git", "push", "origin", branch])
    if code != 0:
        log.warning(f"Push failed (may be ok in local mode): {stderr}")

    log.info(f"Committed: {message}")
    return True


def get_current_branch() -> str:
    """Return name of current git branch."""
    _, stdout, _ = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return stdout.strip()


def git_configure_user() -> None:
    """Set git user identity for Actions environment."""
    run_command(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run_command(["git", "config", "user.name", "github-actions[bot]"])


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def journal_entry(
    *,
    attempt_id: str,
    assessment: dict[str, Any],
    success: bool,
    check_results: dict[str, tuple[bool, str]],
    error: str = "",
    patch_summary: str = "",
) -> None:
    """Append a structured entry to JOURNAL.md."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_label = "SUCCESS" if success else "FAILURE"

    entry_lines = [
        "\n---\n",
        f"## Evolution Attempt [{status_label}] — {attempt_id}\n",
        f"**Timestamp**: {timestamp}  \n",
        f"**Status**: {'SUCCESS' if success else 'FAILURE'}  \n",
        f"**Priority**: {assessment.get('priority', '?').upper()}  \n",
        f"**Category**: {assessment.get('category', '?')}  \n",
        f"**Title**: {assessment.get('title', '?')}  \n",
        f"\n### Rationale\n{assessment.get('rationale', '?')}\n",
        f"\n### Approach\n{assessment.get('approach', '?')}\n",
    ]

    if patch_summary:
        entry_lines.append(f"\n### Patch Summary\n```\n{patch_summary}\n```\n")

    for check_name, (passed, output) in check_results.items():
        label = "PASS" if passed else "FAIL"
        entry_lines.append(f"\n### {check_name.title()} [{label}]\n```\n{output[:CHECK_OUTPUT_MAX_CHARS]}\n```\n")

    if error:
        entry_lines.append(f"\n### Error\n```\n{error}\n```\n")

    entry = "".join(entry_lines)

    # Prepend to journal (newest first), or create if missing
    if JOURNAL_FILE.exists():
        existing = JOURNAL_FILE.read_text(encoding="utf-8")
        # Ensure header exists
        if not existing.startswith("# JOURNAL.md"):
            existing = "# JOURNAL.md — Entwickler Evolution History\n\n" + existing
        # Insert after header
        header_end = existing.find("\n\n", existing.find("\n")) + 2
        new_content = existing[:header_end] + entry + existing[header_end:]
    else:
        new_content = "# JOURNAL.md — Entwickler Evolution History\n\n" + entry

    JOURNAL_FILE.write_text(new_content, encoding="utf-8")
    log.info(f"Journal updated: attempt {attempt_id} ({'success' if success else 'failure'})")


# ---------------------------------------------------------------------------
# Main Evolution Loop
# ---------------------------------------------------------------------------


def evolution_cycle() -> bool | None:
    """
    Execute one full evolution cycle:
    1. Build context (read self + environment)
    2. Self-assess (choose one improvement)
    3. Generate patch
    4. Apply patch directly on main
    5. Run tests + lint
    6. Commit and push to main (on success) or revert in-place + log (on failure)

    Returns True if evolution succeeded, False otherwise.
    Returns None if skipped due to missing configuration.
    """
    # Early check: verify at least one LLM provider is available
    provider = get_available_provider()
    if provider is None:
        key_names = ", ".join(p["env_key"] for p in LLM_PROVIDERS)
        log.warning(
            f"No LLM API key configured — skipping evolution cycle. "
            f"Set one of: {key_names}"
        )
        console.print(Panel(
            "[bold yellow]Evolution cycle skipped[/bold yellow]\n"
            "No LLM API key found. Configure at least one provider API key\n"
            f"as an environment variable (or repository secret in CI): {key_names}",
            expand=False,
        ))
        return None

    attempt_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    assessment: dict[str, Any] = {}
    check_results: dict[str, tuple[bool, str]] = {}
    backups: dict[str, str] = {}

    console.print(Panel(f"[bold green]Entwickler Evolution Cycle[/bold green]\nAttempt: {attempt_id}", expand=False))

    try:
        # Step 1: Build context
        log.info("Step 1/5: Building context...")
        context = build_context()
        selected_skill = select_skill(context["skills"], context)
        if selected_skill:
            context["selected_skill"] = selected_skill
            log.info(f"Selected skill: {selected_skill.get('name', '?')} ({selected_skill.get('priority', '?')} priority)")
        log.info(f"Context: {len(context['sources'])} source files, {len(context['skills'])} skills, {len(context['issues'])} issues")

        # Step 2: Self-assess
        log.info("Step 2/5: Self-assessing...")
        assessment = self_assess(context)

        # Step 3: Generate patch
        log.info("Step 3/5: Generating patch...")
        patches = generate_patch(assessment, context["sources"])

        if not patches:
            log.warning("No patches generated — skipping this cycle")
            journal_entry(
                attempt_id=attempt_id,
                assessment=assessment,
                success=False,
                check_results={},
                error="LLM generated no actionable patches",
            )
            return False

        patch_summary = "\n".join(f"  {f}: {len(c)} chars" for f, c in patches.items())
        log.info(f"Patches generated:\n{patch_summary}")

        # Step 4: Apply patches directly on main (in-place)
        log.info("Step 4/5: Applying patches directly on main...")
        git_configure_user()
        backups = apply_patches(patches)

        # Step 5: Run tests + lint
        log.info("Step 5/5: Running checks...")
        all_passed, check_results = run_all_checks()

        # Commit directly or revert in-place
        if all_passed:
            log.info("All checks PASSED — committing directly to main...")
            commit_msg = f"evolve({assessment.get('category', 'misc')}): {assessment.get('title', 'improvement')}"
            git_commit_and_push(commit_msg, list(patches.keys()))

            journal_entry(
                attempt_id=attempt_id,
                assessment=assessment,
                success=True,
                check_results=check_results,
                patch_summary=patch_summary,
            )

            # Commit journal update to main
            run_command(["git", "add", str(JOURNAL_FILE.relative_to(REPO_ROOT))])
            run_command(["git", "commit", "-m", f"docs: journal entry for {attempt_id}"])
            run_command(["git", "push", "origin", "main"])

            console.print(Panel(f"[bold green]Evolution {attempt_id} succeeded![/bold green]\n{assessment.get('title', '')}", expand=False))
            return True

        else:
            log.warning("Checks FAILED — reverting in-place...")
            try:
                revert_patches(backups)
            except Exception as revert_err:
                log.error(f"Revert failed: {revert_err}")

            failure_details = "\n".join(
                f"{k}: {'PASS' if v[0] else 'FAIL'}\n{v[1][:500]}"
                for k, v in check_results.items()
            )

            journal_entry(
                attempt_id=attempt_id,
                assessment=assessment,
                success=False,
                check_results=check_results,
                error=failure_details,
                patch_summary=patch_summary,
            )

            # Commit journal on main
            run_command(["git", "add", str(JOURNAL_FILE.relative_to(REPO_ROOT))])
            run_command(["git", "commit", "-m", f"docs: journal failure entry for {attempt_id}"])
            run_command(["git", "push", "origin", "main"])

            console.print(Panel(f"[bold red]Evolution {attempt_id} failed — reverted[/bold red]\n{failure_details[:200]}", expand=False))
            return False

    except Exception as e:
        error_detail = traceback.format_exc()
        log.error(f"Evolution cycle error: {e}")

        # Emergency revert
        if backups:
            try:
                revert_patches(backups)
            except Exception as revert_err:
                log.error(f"Revert also failed: {revert_err}")

        journal_entry(
            attempt_id=attempt_id,
            assessment=assessment or {"title": "Unknown", "category": "error", "priority": "unknown"},
            success=False,
            check_results=check_results,
            error=error_detail,
        )

        # Try to commit journal even on error
        try:
            run_command(["git", "add", str(JOURNAL_FILE.relative_to(REPO_ROOT))])
            run_command(["git", "commit", "-m", f"docs: journal error entry for {attempt_id}"])
            run_command(["git", "push", "origin", "main"])
        except Exception:
            pass

        console.print(Panel(f"[bold red]Evolution {attempt_id} crashed[/bold red]\n{str(e)[:200]}", expand=False))
        return False


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point — run one evolution cycle."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Entwickler — Self-evolving coding agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python entwickler.py           # Run one evolution cycle
              python entwickler.py --dry-run # Assess only, don't apply changes
              python entwickler.py --status  # Show current agent status
        """),
    )
    parser.add_argument("--dry-run", action="store_true", help="Assess and plan but don't apply patches")
    parser.add_argument("--status", action="store_true", help="Show agent status and exit")
    parser.add_argument("--version", action="version", version="Entwickler 1.0.0 (bootstrap)")
    args = parser.parse_args()

    if args.status:
        context = build_context()
        console.print(Panel(
            f"[bold]Entwickler Status[/bold]\n"
            f"Source files: {len(context['sources'])}\n"
            f"Skills loaded: {len(context['skills'])}\n"
            f"Open issues: {len(context['issues'])}\n"
            f"Journal entries: {context['journal'].count('## ')}\n"
            f"LLM provider: {provider['name'] if (provider := get_available_provider()) else 'NONE — set API key!'}",
            expand=False,
        ))
        return

    if args.dry_run:
        log.info("Dry-run mode: assessing only, no changes will be applied")
        context = build_context()
        assessment = self_assess(context)
        console.print(Panel(
            f"[bold yellow]Dry-run Assessment[/bold yellow]\n"
            f"[{assessment.get('priority', '?').upper()}] {assessment.get('title', '?')}\n\n"
            f"Rationale: {assessment.get('rationale', '?')[:300]}\n\n"
            f"Approach: {assessment.get('approach', '?')[:300]}",
            expand=False,
        ))
        return

    result = evolution_cycle()
    # None means skipped (missing config) — exit 0 since it's not a runtime failure
    # True means success, False means actual evolution failure
    if result is None:
        sys.exit(0)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
