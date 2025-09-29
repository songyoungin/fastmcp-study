import os
import re
import json
import logging
import sys
import shutil
import tempfile
import time
import subprocess
from pathlib import Path
from typing import Literal, Any

from pydantic import BaseModel, ConfigDict, Field
from fastmcp import FastMCP

# configure logger
logger = logging.getLogger("mcp.files")
h = logging.StreamHandler(sys.stderr)
h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(h)
logger.setLevel(logging.INFO)
logger.propagate = False

# create MCP server
mcp = FastMCP("precommit")


class LintArgs(BaseModel):
    config_yaml: str | None = Field(
        None,
        description="(optional) .pre-commit-config.yaml content to use instead of repo settings",
    )
    repo_path: str = Field(
        default=..., description="Path to the local Git repository to lint"
    )
    all_files: bool = Field(
        default=True, description="Whether to check all files in the repository"
    )
    files_to_check: list[str] | None = Field(
        default=None,
        description="Specific files to check (overrides all_files if provided)",
    )
    select_hooks: list[str] | None = Field(
        default=None, description="Specific hook IDs to run"
    )
    show_diff: bool = Field(
        default=True, description="Whether to show diff output on failure"
    )
    relative_virtualenv_path: str | None = Field(
        default=None,
        description="Relative path to virtual environment directory from repo root",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "repo_path": "/Users/serena/Documents/development/socar/socar-aicc-rag",
                    "relative_virtualenv_path": ".venv",
                    "all_files": True,
                    "show_diff": True,
                },
                {
                    "repo_path": "/Users/serena/work/repo",
                    "files_to_check": ["src/app.py", "tests/test_app.py"],
                    "select_hooks": ["ruff"],
                },
            ]
        }
    )


class HookResult(BaseModel):
    id: str | None = None
    repo: str | None = None
    rev: str | None = None
    status: Literal["passed", "failed", "skipped", "unknown"] = "unknown"
    files: list[str] | None = None
    raw: dict[str, Any] | None = None


class LintSummary(BaseModel):
    hooks: list[HookResult] = []
    duration_sec: float = 0.0


class LintResponse(BaseModel):
    ok: bool
    exit_code: int
    summary: LintSummary
    stdout: str
    stderr: str


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    virtualenv_path: Path | None = None,
) -> subprocess.CompletedProcess:
    """
    Run a command and return the completed process.

    Args:
        cmd: The command to run.
        cwd: The working directory to run the command in.
        env: The environment variables to set.
        virtualenv_path: Path to virtual environment directory to activate before running.
    Returns:
        The completed process.
    """
    # Check if virtual environment should be used
    if virtualenv_path and virtualenv_path.exists():
        # Use virtual environment's Python executable
        venv_python = virtualenv_path / "bin" / "python"
        if not venv_python.exists():
            # Try Windows path
            venv_python = virtualenv_path / "Scripts" / "python.exe"

        if venv_python.exists():
            # Replace 'pre-commit' with virtualenv python and module execution
            # Handle both direct pre-commit command and pre-commit module calls
            if cmd[0] == "pre-commit":
                cmd = [str(venv_python), "-m", "pre_commit"] + cmd[1:]
            elif (
                len(cmd) >= 3
                and cmd[0] == "python"
                and cmd[1] == "-m"
                and cmd[2] == "pre_commit"
            ):
                cmd = [str(venv_python), "-m", "pre_commit"] + cmd[3:]
            elif len(cmd) >= 2 and cmd[0] == "python" and cmd[1] == "-m":
                # General case for python -m module commands
                cmd = [str(venv_python)] + cmd[1:]

    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _ensure_git_repo(root: Path, virtualenv_path: Path | None = None) -> None:
    """
    Ensure the repository is a Git repository.

    Args:
        root: The root directory of the repository.
        virtualenv_path: Path to virtual environment directory to use.
    """
    # If the repository is not a Git repository, initialize it.
    if not (root / ".git").exists():
        _run(
            ["git", "init"],
            cwd=root,
            env=os.environ.copy(),
            virtualenv_path=virtualenv_path,
        )
        _run(
            ["git", "add", "-A"],
            cwd=root,
            env=os.environ.copy(),
            virtualenv_path=virtualenv_path,
        )
        _run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=root,
            env=os.environ.copy(),
            virtualenv_path=virtualenv_path,
        )


def _find_repo_config(root: Path) -> Path | None:
    """
    Find the repository configuration file.

    Args:
        root: The root directory of the repository.
    Returns:
        The path to the repository configuration file.
    """
    # Priority: .yaml -> .yml
    c1 = root / ".pre-commit-config.yaml"
    c2 = root / ".pre-commit-config.yml"
    if c1.exists():
        return c1
    if c2.exists():
        return c2
    return None


def _write_override_config(root: Path, yaml_text: str) -> Path:
    """
    Write the override configuration file.

    Args:
        root: The root directory of the repository.
        yaml_text: The text of the configuration file.
    Returns:
        The path to the override configuration file.
    """
    cfg = root / ".pre-commit-config.override.yaml"
    cfg.write_text(yaml_text, encoding="utf-8")
    return cfg


def _build_base_cmd(cfg_path: Path, req: LintArgs) -> list[str]:
    """
    Build the base command.

    Args:
        cfg_path: The path to the configuration file.
        req: The request.
    Returns:
        The base command.
    """
    cmd = ["pre-commit", "run", "--config", str(cfg_path)]
    if req.show_diff:
        cmd.append("--show-diff-on-failure")
    if req.select_hooks and len(req.select_hooks) == 1:
        cmd.append(req.select_hooks[0])
    if req.all_files and not req.files_to_check:
        cmd.append("--all-files")
    if req.files_to_check:
        cmd += ["--files", *req.files_to_check]
    return cmd


def _parse_text_summary(out: str) -> list[HookResult]:
    """
    Parse the text summary.

    Args:
        out: The text summary.
    Returns:
        The list of hook results.
    """
    # "hookid ....... Passed/Failed/Skipped" pattern summary
    results: dict[str, HookResult] = {}
    for line in out.splitlines():
        m = re.match(
            r"^(-|\s)*(\S+)\s+\.+\s+(Passed|Failed|Skipped)$",
            line.strip(),
            re.IGNORECASE,
        )
        if m:
            hook_id = m.group(2)
            status = m.group(3).lower()
            results[hook_id] = HookResult(
                id=hook_id,
                status=(
                    "passed"
                    if status == "passed"
                    else "failed"
                    if status == "failed"
                    else "skipped"
                ),
            )
    return list(results.values())


@mcp.tool()
def lint_with_pre_commit(request: LintArgs) -> LintResponse:
    """
    Lint the repository with pre-commit.

    Args:
        request: The request.

    Returns:
        The lint response.
    """
    start = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="mcp-precommit-"))
    cache = Path(tempfile.mkdtemp(prefix="mcp-precommit-cache-"))

    try:
        workdir = tmp / "work"
        workdir.mkdir(parents=True, exist_ok=True)

        # Copy the repository (isolated execution)
        src = Path(request.repo_path).expanduser().resolve()
        if not src.exists():
            raise ValueError(f"repo_path does not exist: {src}")
        shutil.copytree(src, workdir, dirs_exist_ok=True)

        # Determine virtual environment path
        virtualenv_path: Path | None = None
        if request.relative_virtualenv_path:
            virtualenv_path = workdir / request.relative_virtualenv_path

        # Ensure Git
        _ensure_git_repo(workdir, virtualenv_path)

        # Determine the configuration file: override first, then repo's default settings
        if request.config_yaml:
            cfg_path = _write_override_config(workdir, request.config_yaml)
        else:
            cfg_in_repo = _find_repo_config(workdir)
            if not cfg_in_repo:
                return LintResponse(
                    ok=False,
                    exit_code=2,
                    summary=LintSummary(hooks=[], duration_sec=time.time() - start),
                    stdout="",
                    stderr="Repository does not have a .pre-commit-config.yaml(.yml) file.",
                )
            cfg_path = cfg_in_repo

        # Isolated cache & environment
        env = os.environ.copy()
        env["PRE_COMMIT_HOME"] = str(cache)
        env["PYTHONUTF8"] = "1"
        env["TERM"] = "dumb"

        # Run command
        precommit_cmd = _build_base_cmd(cfg_path, request)

        # 1st try: JSON format
        p = _run(precommit_cmd, cwd=workdir, env=env, virtualenv_path=virtualenv_path)
        stdout, stderr = p.stdout, p.stderr
        hooks: list[HookResult] = []
        try:
            payload = json.loads(stdout) if stdout.strip() else {}
            for item in payload.get("results", []):
                hooks.append(
                    HookResult(
                        id=item.get("hook_id"),
                        repo=item.get("repo"),
                        rev=item.get("rev"),
                        status=(
                            "passed"
                            if item.get("status") == "passed"
                            else "failed"
                            if item.get("status") == "failed"
                            else "skipped"
                            if item.get("status") == "skipped"
                            else "unknown"
                        ),
                        files=item.get("files") or None,
                        raw=item,
                    )
                )
        except Exception:
            # JSON parsing failed → parse text summary
            hooks = _parse_text_summary(stdout)

        return LintResponse(
            ok=(p.returncode == 0),
            exit_code=p.returncode,
            summary=LintSummary(hooks=hooks, duration_sec=time.time() - start),
            stdout=stdout,
            stderr=stderr,
        )

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(cache, ignore_errors=True)


if __name__ == "__main__":
    mcp.run(transport="stdio")
