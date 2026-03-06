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

# Approximate ratio of tokens to words in typical English/code text
TOKEN_TO_WORD_RATIO: float = 1.3

# Journal compaction: if journal exceeds this length, keep only the tail
JOURNAL_MAX_LENGTH: int = 8000
JOURNAL_KEEP_LENGTH: int = 5000

# Context assembly: how many chars of source to include per file preview
MAX_SOURCE_PREVIEW_LENGTH: int = 2000

# Context assembly: max number of source files to include in the summary
MAX_FILES_IN_SUMMARY: int = 5

# Context assembly: max chars of recent journal to send to LLM
JOURNAL_RECENT_CHARS: int = 2000

# Context assembly: max chars of IDENTITY.md to include in prompt
IDENTITY_MAX_CHARS: int = 1500

# Journal: max chars of check output to log per check
CHECK_OUTPUT_MAX_CHARS: int = 1000

# ---------------------------------------------------------------------------
# LLM Provider Configuration
# ---------------------------------------------------------------------------

# Ordered by preference: fastest/cheapest first, most capable last as fallback.
LLM_PROVIDERS: list[dict[str, Any]] = [
    {
        "name": "groq-llama3",
        "model": "groq/llama-3.1-70b-versatile",
        "env_key": "GROQ_API_KEY",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.0006,
    },
    {
        "name": "gemini-flash",
        "model": "gemini/gemini-2.0-flash",
        "env_key": "GEMINI_API_KEY",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.00010,
    },
    {
        "name": "deepseek-coder",
        "model": "deepseek/deepseek-coder",
        "env_key": "DEEPSEEK_API_KEY",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.00014,
    },
    {
        "name": "anthropic-claude",
        "model": "anthropic/claude-3-5-sonnet-20241022",
        "env_key": "ANTHROPIC_API_KEY",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.003,
    },
    {
        "name": "gemini-pro",
        "model": "gemini/gemini-1.5-pro",
        "env_key": "GEMINI_API_KEY",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.00125,
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

    provider = get_available_provider()
    if provider is None:
        raise RuntimeError(
            "No LLM API key found. Set one of: "
            + ", ".join(p["env_key"] for p in LLM_PROVIDERS)
        )

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    log.info(f"Calling LLM: {provider['name']} ({provider['model']})")

    # Estimate cost using token-to-word ratio approximation
    token_estimate = len(prompt.split()) * TOKEN_TO_WORD_RATIO
    cost_estimate = (token_estimate / 1000) * provider["cost_per_1k_input"]
    log.info(f"Estimated cost: ~${cost_estimate:.4f} ({token_estimate:.0f} tokens)")

    response = litellm.completion(
        model=provider["model"],
        messages=messages,
        max_tokens=min(max_tokens, provider["max_tokens"]),
        api_key=os.environ.get(provider["env_key"]),
    )
    return response.choices[0].message.content or ""


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


def select_skill(skills: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any] | None:
    """Select the highest-priority applicable skill."""
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_skills = sorted(
        skills,
        key=lambda s: priority_order.get(s.get("priority", "low"), 99),
    )
    # For now, return first applicable skill; agent will improve this selection logic
    return sorted_skills[0] if sorted_skills else None


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
    Always think about: correctness > security > architecture > tests > performance > UX.
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

    ---

    Perform a thorough self-assessment. Identify the SINGLE most valuable improvement to make.
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

    prompt = SELF_ASSESS_PROMPT.format(
        source_summary=source_summary,
        identity=context["identity"][:IDENTITY_MAX_CHARS],
        journal_recent=journal_recent,
        issues_summary=issues_summary,
        skills_summary=skills_summary,
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
    2. If the file is large, return a unified diff (--- a/file +++ b/file format).
    3. Include proper Python 3.11+ type hints.
    4. Follow PEP 8 style.
    5. Add docstrings where missing.
    6. Always include test code if you add new functionality.
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
    Handles both complete file blocks and unified diff blocks.
    """
    patches: dict[str, str] = {}

    # Match ```python:path/to/file.py or ```diff:path/to/file.py blocks
    pattern = re.compile(
        r"```(?P<type>python|diff):(?P<path>[^\n]+)\n(?P<content>.*?)```",
        re.DOTALL,
    )

    for match in pattern.finditer(response):
        block_type = match.group("type")
        fpath = match.group("path").strip()
        content = match.group("content")

        if block_type == "python":
            # Complete file replacement
            patches[fpath] = content
        elif block_type == "diff":
            # Apply diff to existing file
            existing = ""
            full_path = REPO_ROOT / fpath
            if full_path.exists():
                existing = full_path.read_text(encoding="utf-8")
            patched = apply_unified_diff(existing, content)
            if patched is not None:
                patches[fpath] = patched
            else:
                log.warning(f"Failed to apply diff to {fpath}, skipping")

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


def run_all_checks() -> tuple[bool, dict[str, tuple[bool, str]]]:
    """Run tests + lint. Returns (all_passed, results_dict)."""
    results: dict[str, tuple[bool, str]] = {}

    tests_passed, tests_output = run_tests()
    results["tests"] = (tests_passed, tests_output)

    lint_passed, lint_output = run_lint()
    results["lint"] = (lint_passed, lint_output)

    all_passed = tests_passed and lint_passed
    return all_passed, results


# ---------------------------------------------------------------------------
# Git Operations
# ---------------------------------------------------------------------------


def git_create_branch(branch_name: str) -> bool:
    """Create and checkout a new git branch."""
    code, _, stderr = run_command(["git", "checkout", "-b", branch_name])
    if code != 0:
        log.error(f"Failed to create branch {branch_name}: {stderr}")
        return False
    log.info(f"Created branch: {branch_name}")
    return True


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


def git_merge_to_main(branch_name: str) -> bool:
    """Merge feature branch to main."""
    # Checkout main
    code, _, stderr = run_command(["git", "checkout", "main"])
    if code != 0:
        log.error(f"Failed to checkout main: {stderr}")
        return False

    # Merge
    code, _, stderr = run_command(["git", "merge", "--no-ff", branch_name, "-m", f"chore: merge {branch_name}"])
    if code != 0:
        log.error(f"Failed to merge {branch_name}: {stderr}")
        return False

    # Push main
    code, _, stderr = run_command(["git", "push", "origin", "main"])
    if code != 0:
        log.warning(f"Push to main failed: {stderr}")

    log.info(f"Merged {branch_name} to main")
    return True


def git_delete_branch(branch_name: str) -> None:
    """Delete a local branch (cleanup)."""
    run_command(["git", "branch", "-D", branch_name])


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


def evolution_cycle() -> bool:
    """
    Execute one full evolution cycle:
    1. Build context (read self + environment)
    2. Self-assess (choose one improvement)
    3. Generate patch
    4. Apply patch on feature branch
    5. Run tests + lint
    6. Merge to main (on success) or revert + log (on failure)

    Returns True if evolution succeeded, False otherwise.
    """
    attempt_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"evolve/attempt-{attempt_id}"
    assessment: dict[str, Any] = {}
    check_results: dict[str, tuple[bool, str]] = {}
    backups: dict[str, str] = {}
    original_branch = get_current_branch()

    console.print(Panel(f"[bold green]Entwickler Evolution Cycle[/bold green]\nAttempt: {attempt_id}", expand=False))

    try:
        # Step 1: Build context
        log.info("Step 1/6: Building context...")
        context = build_context()
        log.info(f"Context: {len(context['sources'])} source files, {len(context['skills'])} skills, {len(context['issues'])} issues")

        # Step 2: Self-assess
        log.info("Step 2/6: Self-assessing...")
        assessment = self_assess(context)

        # Step 3: Generate patch
        log.info("Step 3/6: Generating patch...")
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

        # Step 4: Create feature branch and apply patches
        log.info("Step 4/6: Applying patches on feature branch...")
        git_configure_user()
        if not git_create_branch(branch_name):
            raise RuntimeError(f"Could not create branch {branch_name}")

        backups = apply_patches(patches)

        # Stage and commit on feature branch
        commit_msg = f"evolve({assessment.get('category', 'misc')}): {assessment.get('title', 'improvement')}"
        git_commit_and_push(commit_msg, list(patches.keys()) + [str(JOURNAL_FILE.relative_to(REPO_ROOT))])

        # Step 5: Run tests + lint
        log.info("Step 5/6: Running checks...")
        all_passed, check_results = run_all_checks()

        # Step 6: Merge or revert
        if all_passed:
            log.info("Step 6/6: All checks PASSED — merging to main...")
            git_merge_to_main(branch_name)

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

            git_delete_branch(branch_name)
            console.print(Panel(f"[bold green]Evolution {attempt_id} succeeded![/bold green]\n{assessment.get('title', '')}", expand=False))
            return True

        else:
            log.warning("Step 6/6: Checks FAILED — reverting...")
            revert_patches(backups)

            # Switch back to original branch
            run_command(["git", "checkout", original_branch])
            git_delete_branch(branch_name)

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

            # Commit journal on original branch
            run_command(["git", "add", str(JOURNAL_FILE.relative_to(REPO_ROOT))])
            run_command(["git", "commit", "-m", f"docs: journal failure entry for {attempt_id}"])
            run_command(["git", "push", "origin", original_branch])

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

        # Return to original branch
        run_command(["git", "checkout", original_branch])
        if branch_name != original_branch:
            git_delete_branch(branch_name)

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
            run_command(["git", "push", "origin", original_branch])
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

    success = evolution_cycle()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
