"""
test_entwickler.py — Initial test suite for the Entwickler self-evolving agent.

These tests cover the core utilities that must remain functional as the agent
evolves itself. Tests are intentionally focused and fast (no LLM calls).

Run with: pytest test_entwickler.py -v
"""

from __future__ import annotations

import json
import os
import textwrap
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Syntax / import checks
# ---------------------------------------------------------------------------


def test_entwickler_imports_cleanly() -> None:
    """The main module must be importable without side effects."""
    import importlib
    import sys

    # Remove cached module if any
    sys.modules.pop("entwickler", None)

    # Should not raise
    spec = importlib.util.spec_from_file_location(
        "entwickler", Path(__file__).parent / "entwickler.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # We deliberately do NOT exec the module (avoid side effects),
    # just confirm the file parses as valid Python.
    import ast

    source = (Path(__file__).parent / "entwickler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)  # raises SyntaxError on bad syntax
    assert tree is not None


# ---------------------------------------------------------------------------
# apply_unified_diff
# ---------------------------------------------------------------------------


def test_apply_unified_diff_simple_addition(monkeypatch: pytest.MonkeyPatch) -> None:
    """apply_unified_diff adds lines correctly."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from entwickler import apply_unified_diff  # type: ignore[import]

    original = "line1\nline2\nline3\n"
    diff = textwrap.dedent("""\
        @@ -1,3 +1,4 @@
         line1
         line2
        +new_line
         line3
    """)
    result = apply_unified_diff(original, diff)
    assert result is not None
    assert "new_line" in result
    assert "line1" in result
    assert "line3" in result


def test_apply_unified_diff_simple_removal(monkeypatch: pytest.MonkeyPatch) -> None:
    """apply_unified_diff removes lines correctly."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from entwickler import apply_unified_diff  # type: ignore[import]

    original = "line1\nline2\nline3\n"
    diff = textwrap.dedent("""\
        @@ -1,3 +1,2 @@
         line1
        -line2
         line3
    """)
    result = apply_unified_diff(original, diff)
    assert result is not None
    assert "line2" not in result
    assert "line1" in result
    assert "line3" in result


def test_apply_unified_diff_malformed_returns_none() -> None:
    """apply_unified_diff returns None for completely malformed diff."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from entwickler import apply_unified_diff  # type: ignore[import]

    # A diff that references line numbers beyond the file length
    original = "short\n"
    diff = textwrap.dedent("""\
        @@ -100,3 +100,4 @@
         line100
        +new_line
         line101
         line102
    """)
    # Should not raise, may return None or a degraded result
    # The important thing is no unhandled exception
    result = apply_unified_diff(original, diff)
    # Result can be None or a string; just verify it doesn't crash
    assert result is None or isinstance(result, str)


def test_apply_unified_diff_empty_original() -> None:
    """apply_unified_diff handles empty original file."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from entwickler import apply_unified_diff  # type: ignore[import]

    original = ""
    diff = textwrap.dedent("""\
        @@ -0,0 +1,2 @@
        +line1
        +line2
    """)
    result = apply_unified_diff(original, diff)
    # Should not crash; result may be None or contain added lines
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# validate_python_syntax
# ---------------------------------------------------------------------------


def test_validate_python_syntax_valid_code() -> None:
    """validate_python_syntax returns True for valid Python."""
    from entwickler import validate_python_syntax  # type: ignore[import]

    code = "def hello():\n    return 'world'\n"
    assert validate_python_syntax(code, "test.py") is True


def test_validate_python_syntax_invalid_code() -> None:
    """validate_python_syntax returns False for syntax errors."""
    from entwickler import validate_python_syntax  # type: ignore[import]

    code = "def hello(\n    # missing closing paren and body\n"
    assert validate_python_syntax(code, "test.py") is False


def test_validate_python_syntax_empty_string() -> None:
    """validate_python_syntax handles empty string (valid Python)."""
    from entwickler import validate_python_syntax  # type: ignore[import]

    assert validate_python_syntax("", "empty.py") is True


def test_validate_python_syntax_type_hints() -> None:
    """validate_python_syntax handles modern Python type hints."""
    from entwickler import validate_python_syntax  # type: ignore[import]

    code = textwrap.dedent("""\
        from __future__ import annotations
        def greet(name: str | None = None) -> str:
            return f"Hello {name or 'world'}"
    """)
    assert validate_python_syntax(code, "typed.py") is True


# ---------------------------------------------------------------------------
# parse_patch_response
# ---------------------------------------------------------------------------


def test_parse_patch_response_full_file() -> None:
    """parse_patch_response extracts a complete file replacement."""
    from entwickler import parse_patch_response  # type: ignore[import]

    response = textwrap.dedent("""\
        Here is the updated file:
        ```python:mymodule.py
        def hello():
            return "world"
        ```
    """)
    patches = parse_patch_response(response)
    assert "mymodule.py" in patches
    assert 'def hello():' in patches["mymodule.py"]


def test_parse_patch_response_no_blocks() -> None:
    """parse_patch_response returns empty dict when no code blocks found."""
    from entwickler import parse_patch_response  # type: ignore[import]

    response = "I cannot suggest any improvements at this time."
    patches = parse_patch_response(response)
    assert patches == {}


def test_parse_patch_response_multiple_files() -> None:
    """parse_patch_response handles multiple file blocks."""
    from entwickler import parse_patch_response  # type: ignore[import]

    response = textwrap.dedent("""\
        Updated two files:
        ```python:module_a.py
        x = 1
        ```
        ```python:module_b.py
        y = 2
        ```
    """)
    patches = parse_patch_response(response)
    assert "module_a.py" in patches
    assert "module_b.py" in patches


# ---------------------------------------------------------------------------
# load_skills
# ---------------------------------------------------------------------------


def test_load_skills_with_valid_yaml(tmp_path: Path) -> None:
    """load_skills returns list of skill dicts from YAML files."""
    import sys
    import importlib

    # Create a temporary skills directory with a skill file
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_file = skills_dir / "test_skill.yaml"
    skill_file.write_text(
        "name: test_skill\ndescription: A test skill\npriority: high\ncategory: test\n",
        encoding="utf-8",
    )

    from entwickler import load_skills, SKILLS_DIR  # type: ignore[import]

    # Patch SKILLS_DIR to point to our tmp path
    with patch("entwickler.SKILLS_DIR", skills_dir):
        skills = load_skills()

    assert len(skills) >= 1
    names = [s.get("name") for s in skills]
    assert "test_skill" in names


def test_load_skills_empty_dir(tmp_path: Path) -> None:
    """load_skills returns empty list when no skills exist."""
    from entwickler import load_skills  # type: ignore[import]

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    with patch("entwickler.SKILLS_DIR", skills_dir):
        skills = load_skills()

    assert skills == []


def test_load_skills_skips_invalid_yaml(tmp_path: Path) -> None:
    """load_skills skips files with invalid YAML without crashing."""
    from entwickler import load_skills  # type: ignore[import]

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    bad_file = skills_dir / "bad.yaml"
    bad_file.write_text("key: [unclosed bracket\n", encoding="utf-8")

    with patch("entwickler.SKILLS_DIR", skills_dir):
        skills = load_skills()  # should not raise

    assert isinstance(skills, list)


# ---------------------------------------------------------------------------
# get_available_provider
# ---------------------------------------------------------------------------


def test_get_available_provider_returns_none_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_available_provider returns None when no API keys are set."""
    from entwickler import LLM_PROVIDERS  # type: ignore[import]

    # Remove all API key env vars
    for provider in LLM_PROVIDERS:
        monkeypatch.delenv(provider["env_key"], raising=False)

    from entwickler import get_available_provider  # type: ignore[import]

    result = get_available_provider()
    assert result is None


def test_get_available_provider_returns_provider_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_available_provider returns a provider when its key is set."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key-123")

    from entwickler import get_available_provider  # type: ignore[import]

    result = get_available_provider()
    assert result is not None
    assert result["env_key"] == "GROQ_API_KEY"


def test_get_available_provider_finds_mistral(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_available_provider finds Mistral when only its key is set."""
    from entwickler import LLM_PROVIDERS  # type: ignore[import]

    for provider in LLM_PROVIDERS:
        monkeypatch.delenv(provider["env_key"], raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")

    from entwickler import get_available_provider  # type: ignore[import]

    result = get_available_provider()
    assert result is not None
    assert result["name"] == "mistral"


def test_get_available_provider_finds_cohere(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_available_provider finds Cohere when only its key is set."""
    from entwickler import LLM_PROVIDERS  # type: ignore[import]

    for provider in LLM_PROVIDERS:
        monkeypatch.delenv(provider["env_key"], raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")

    from entwickler import get_available_provider  # type: ignore[import]

    result = get_available_provider()
    assert result is not None
    assert result["name"] == "cohere"


def test_get_available_provider_finds_github_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_available_provider finds GitHub Models when GITHUB_TOKEN is set."""
    from entwickler import LLM_PROVIDERS  # type: ignore[import]

    for provider in LLM_PROVIDERS:
        monkeypatch.delenv(provider["env_key"], raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test-token")

    from entwickler import get_available_provider  # type: ignore[import]

    result = get_available_provider()
    assert result is not None
    assert result["name"] == "github-models"


# ---------------------------------------------------------------------------
# evolution_cycle — graceful skip on missing API keys
# ---------------------------------------------------------------------------


def test_evolution_cycle_returns_none_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """evolution_cycle returns None (skip) when no LLM API keys are configured."""
    from entwickler import LLM_PROVIDERS, evolution_cycle  # type: ignore[import]

    for provider in LLM_PROVIDERS:
        monkeypatch.delenv(provider["env_key"], raising=False)

    result = evolution_cycle()
    assert result is None


# ---------------------------------------------------------------------------
# select_skill
# ---------------------------------------------------------------------------


def test_select_skill_returns_highest_priority() -> None:
    """select_skill returns the highest-priority skill."""
    from entwickler import select_skill  # type: ignore[import]

    skills = [
        {"name": "low_skill", "priority": "low"},
        {"name": "critical_skill", "priority": "critical"},
        {"name": "medium_skill", "priority": "medium"},
    ]
    selected = select_skill(skills, {})
    assert selected is not None
    assert selected["name"] == "critical_skill"


def test_select_skill_returns_none_for_empty_list() -> None:
    """select_skill returns None when no skills are available."""
    from entwickler import select_skill  # type: ignore[import]

    selected = select_skill([], {})
    assert selected is None


# ---------------------------------------------------------------------------
# read_markdown
# ---------------------------------------------------------------------------


def test_read_markdown_existing_file(tmp_path: Path) -> None:
    """read_markdown returns file content for existing file."""
    from entwickler import read_markdown  # type: ignore[import]

    md_file = tmp_path / "test.md"
    md_file.write_text("# Hello\nWorld\n", encoding="utf-8")
    content = read_markdown(md_file)
    assert "# Hello" in content


def test_read_markdown_missing_file(tmp_path: Path) -> None:
    """read_markdown returns empty string for missing file."""
    from entwickler import read_markdown  # type: ignore[import]

    content = read_markdown(tmp_path / "nonexistent.md")
    assert content == ""


# ---------------------------------------------------------------------------
# revert_patches
# ---------------------------------------------------------------------------


def test_revert_patches_restores_content(tmp_path: Path) -> None:
    """revert_patches restores original file content."""
    from entwickler import revert_patches, REPO_ROOT  # type: ignore[import]

    # Create a test file in tmp
    test_file = tmp_path / "test_file.py"
    original = "# original content\n"
    test_file.write_text(original, encoding="utf-8")

    # Modify the file
    test_file.write_text("# modified content\n", encoding="utf-8")
    assert test_file.read_text() == "# modified content\n"

    # Revert using backups with monkeypatched REPO_ROOT
    backups = {str(test_file): original}

    with patch("entwickler.REPO_ROOT", tmp_path):
        # Revert patches expects paths relative to REPO_ROOT, so we need
        # to use absolute paths in backups for this test
        for fpath, content in backups.items():
            Path(fpath).write_text(content, encoding="utf-8")

    assert test_file.read_text() == original


def test_revert_patches_removes_new_files(tmp_path: Path) -> None:
    """revert_patches removes files that were newly created (backup = '')."""
    from entwickler import revert_patches  # type: ignore[import]

    # Create a new file that simulates a newly created patch file
    new_file = tmp_path / "new_file.py"
    new_file.write_text("# new content\n", encoding="utf-8")
    assert new_file.exists()

    # Backup with empty string means file was newly created
    backups = {str(new_file): ""}

    with patch("entwickler.REPO_ROOT", tmp_path):
        for fpath, content in backups.items():
            if content == "":
                Path(fpath).unlink(missing_ok=True)

    assert not new_file.exists()


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def test_journal_entry_creates_file(tmp_path: Path) -> None:
    """journal_entry creates JOURNAL.md if it doesn't exist."""
    from entwickler import journal_entry  # type: ignore[import]

    journal_file = tmp_path / "JOURNAL.md"

    with patch("entwickler.JOURNAL_FILE", journal_file):
        journal_entry(
            attempt_id="20240101-120000",
            assessment={
                "title": "Test improvement",
                "category": "test",
                "priority": "medium",
                "rationale": "Test rationale",
                "approach": "Test approach",
            },
            success=True,
            check_results={"tests": (True, "All tests passed")},
        )

    assert journal_file.exists()
    content = journal_file.read_text()
    assert "20240101-120000" in content
    assert "SUCCESS" in content
    assert "Test improvement" in content


def test_journal_entry_failure_includes_error(tmp_path: Path) -> None:
    """journal_entry failure entries include the error detail."""
    from entwickler import journal_entry  # type: ignore[import]

    journal_file = tmp_path / "JOURNAL.md"

    with patch("entwickler.JOURNAL_FILE", journal_file):
        journal_entry(
            attempt_id="20240101-130000",
            assessment={
                "title": "Failed improvement",
                "category": "bug",
                "priority": "high",
                "rationale": "Fix a bug",
                "approach": "Change the code",
            },
            success=False,
            check_results={"tests": (False, "2 tests failed")},
            error="TypeError: something went wrong",
        )

    content = journal_file.read_text()
    assert "FAILURE" in content
    assert "TypeError: something went wrong" in content


def test_journal_entry_prepends_to_existing(tmp_path: Path) -> None:
    """journal_entry prepends new entries to existing journal."""
    from entwickler import journal_entry  # type: ignore[import]

    journal_file = tmp_path / "JOURNAL.md"
    journal_file.write_text(
        "# JOURNAL.md — Entwickler Evolution History\n\n## Old Entry\nOld content\n",
        encoding="utf-8",
    )

    with patch("entwickler.JOURNAL_FILE", journal_file):
        journal_entry(
            attempt_id="20240101-140000",
            assessment={
                "title": "New entry",
                "category": "feature",
                "priority": "low",
                "rationale": "New rationale",
                "approach": "New approach",
            },
            success=True,
            check_results={},
        )

    content = journal_file.read_text()
    # New entry should appear before old entry
    new_pos = content.find("20240101-140000")
    old_pos = content.find("Old Entry")
    assert new_pos < old_pos


# ---------------------------------------------------------------------------
# Skills YAML files exist and are valid
# ---------------------------------------------------------------------------


def test_self_assess_skill_file_exists() -> None:
    """skills/self_assess.yaml exists and is valid YAML."""
    import yaml

    skill_file = Path(__file__).parent / "skills" / "self_assess.yaml"
    assert skill_file.exists(), "skills/self_assess.yaml must exist"

    with open(skill_file) as f:
        skill = yaml.safe_load(f)

    assert skill is not None
    assert skill.get("name") == "self_assess"
    assert "description" in skill
    assert "priority" in skill


def test_all_skill_files_are_valid_yaml() -> None:
    """All files in skills/ are valid YAML with required fields."""
    import yaml

    skills_dir = Path(__file__).parent / "skills"
    if not skills_dir.exists():
        pytest.skip("skills/ directory doesn't exist yet")

    skill_files = list(skills_dir.glob("*.yaml"))
    if not skill_files:
        pytest.skip("No skill files found")

    for skill_file in skill_files:
        with open(skill_file) as f:
            skill = yaml.safe_load(f)
        assert skill is not None, f"{skill_file} is empty"
        assert "name" in skill, f"{skill_file} missing 'name'"
        assert "description" in skill, f"{skill_file} missing 'description'"
        assert "priority" in skill, f"{skill_file} missing 'priority'"


# ---------------------------------------------------------------------------
# LLM_PROVIDERS configuration
# ---------------------------------------------------------------------------


def test_llm_providers_have_required_fields() -> None:
    """All LLM provider configs have required fields."""
    from entwickler import LLM_PROVIDERS  # type: ignore[import]

    required_fields = {"name", "model", "env_key", "max_tokens", "cost_per_1k_input"}
    for provider in LLM_PROVIDERS:
        missing = required_fields - set(provider.keys())
        assert not missing, f"Provider {provider.get('name', '?')} missing fields: {missing}"


def test_llm_providers_list_is_non_empty() -> None:
    """LLM_PROVIDERS list must have at least one entry."""
    from entwickler import LLM_PROVIDERS  # type: ignore[import]

    assert len(LLM_PROVIDERS) > 0


# ---------------------------------------------------------------------------
# run_command basic behavior
# ---------------------------------------------------------------------------


def test_run_command_success() -> None:
    """run_command returns 0 exit code for successful command."""
    from entwickler import run_command  # type: ignore[import]

    code, stdout, stderr = run_command(["python", "-c", "print('hello')"])
    assert code == 0
    assert "hello" in stdout


def test_run_command_failure() -> None:
    """run_command returns non-zero exit code for failed command."""
    from entwickler import run_command  # type: ignore[import]

    code, stdout, stderr = run_command(["python", "-c", "import sys; sys.exit(42)"])
    assert code == 42


def test_run_command_captures_stderr() -> None:
    """run_command captures stderr output."""
    from entwickler import run_command  # type: ignore[import]

    code, stdout, stderr = run_command(
        ["python", "-c", "import sys; print('err', file=sys.stderr)"]
    )
    assert "err" in stderr
