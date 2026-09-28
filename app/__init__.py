"""PDF tablature to Guitar Pro 5 converter."""

__version__ = "0.5.0"


def _git_revision() -> str | None:
    """Short commit of a git checkout (read from .git, no subprocess), to tell builds apart."""
    from pathlib import Path

    git = Path(__file__).resolve().parent.parent / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="ascii").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            ref_file = git / ref
            if ref_file.is_file():
                head = ref_file.read_text(encoding="ascii").strip()
            else:  # packed refs
                packed = (git / "packed-refs").read_text(encoding="ascii")
                head = next(line.split()[0] for line in packed.splitlines() if line.endswith(" " + ref))
        return head[:7] if len(head) >= 7 and all(c in "0123456789abcdef" for c in head[:7]) else None
    except (OSError, StopIteration):
        return None


__revision__ = _git_revision()
