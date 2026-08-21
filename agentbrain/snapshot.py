from __future__ import annotations

import subprocess
from pathlib import Path

_GITIGNORE = ".vault.lock\n*.tmp\n"


class Snapshot:
    """Git-based point-in-time recovery for the vault.

    Each vault gets its own repo-local git history so every content write can
    be rolled back. Repo-local identity (user.name/user.email) is configured at
    init time — the user's global git config is never touched. If git is not
    installed, snapshots are silently disabled and everything else keeps
    working.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def enabled(self) -> bool:
        return (self.root / ".git").exists()

    def _git(self, *args: str, timeout: float = 20.0) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def ensure(self) -> bool:
        """Create the repo-local snapshot repo if absent. Idempotent."""
        if self.enabled:
            return True
        if self._git("init") is None or not self.enabled:
            return False
        gi = self.root / ".gitignore"
        if not gi.exists():
            gi.write_text(_GITIGNORE, encoding="utf-8")
        # repo-local identity only — commits work without any global git config
        self._git("config", "user.name", "agentbrain")
        self._git("config", "user.email", "agentbrain@localhost")
        return True

    def commit(self, message: str) -> bool:
        """Commit all vault changes. True if a new commit was created."""
        if not self.enabled:
            return False
        self._git("add", "-A")
        r = self._git("commit", "-m", message)
        return r is not None and r.returncode == 0

    def status(self) -> dict:
        """Best-effort info for `agentbrain doctor` (read-only)."""
        info: dict = {"enabled": self.enabled}
        if not self.enabled:
            return info
        r = self._git("log", "-1", "--pretty=format:%s|%cd", "--date=local")
        if r is not None and r.returncode == 0 and r.stdout.strip():
            subject, _, when = r.stdout.strip().partition("|")
            info["last_commit"] = f"{when.strip()} — {subject.strip()}"
        r = self._git("status", "--porcelain")
        if r is not None and r.returncode == 0:
            info["pending"] = len([ln for ln in r.stdout.splitlines() if ln.strip()])
        return info
