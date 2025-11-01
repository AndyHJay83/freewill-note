#!/usr/bin/env python3
"""
Outline Repo — generates PROJECT_SUMMARY.md with:
- Repo basics (name, path)
- Git remotes, default branch (best-effort), last 10 commits
- Directory tree (depth-limited, ignores heavy folders)
- Language breakdown by extension
- Detected manifests (package managers / build tools)
- Top folders/files by size
Usage:
    python outline_repo.py [path_to_repo] [--depth 3] [--ignore node_modules,.git,dist,build,venv,.venv]
"""
from __future__ import annotations
import argparse
import os
import sys
import subprocess
from pathlib import Path
from collections import Counter, defaultdict
import textwrap

DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", ".DS_Store",
    "node_modules", "dist", "build", ".next", ".expo",
    ".venv", "venv", ".env", "__pycache__", ".pytest_cache",
    ".parcel-cache", ".turbo", ".cache", "target", "out", ".gradle",
    ".idea", ".vscode", ".pnpm-store"
}

EXT_LANG = {
    # Web
    ".js": "JavaScript", ".jsx": "JavaScript/React", ".ts": "TypeScript", ".tsx": "TypeScript/React",
    ".vue": "Vue", ".svelte": "Svelte", ".astro": "Astro",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SASS", ".less": "LESS",
    ".html": "HTML", ".htm": "HTML",
    # Python
    ".py": "Python",
    # Java / Kotlin
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    # C/C++
    ".c": "C", ".h": "C Header", ".hpp": "C++ Header", ".hh": "C++ Header", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    # C#
    ".cs": "C#",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # Swift
    ".swift": "Swift",
    # PHP
    ".php": "PHP",
    # Ruby
    ".rb": "Ruby",
    # Shell
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    # Data / Infra
    ".sql": "SQL", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON", ".toml": "TOML", ".ini": "INI", ".env": "ENV",
    ".md": "Markdown", ".rst": "reStructuredText",
    # Misc
    ".gradle": "Gradle", ".groovy": "Groovy",
    ".dart": "Dart",
    ".r": "R",
    ".pl": "Perl",
    ".hs": "Haskell",
    ".scala": "Scala",
    ".lua": "Lua"
}

MANIFESTS = [
    "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json",
    "pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock",
    "setup.cfg", "setup.py",
    "go.mod", "go.sum",
    "Cargo.toml", "Cargo.lock",
    "build.gradle", "settings.gradle", "pom.xml",
    "composer.json",
    "Gemfile",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "CMakeLists.txt",
    "Procfile",
    "netlify.toml", "vercel.json", "project.json", "nx.json",
]

def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for u in units:
        if size < 1024.0 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024.0

def scan_tree(root: Path, depth: int, ignores: set[str]) -> list[str]:
    lines = []
    def helper(path: Path, prefix: str, current_depth: int):
        if current_depth > depth:
            return
        try:
            entries = sorted([p for p in path.iterdir()], key=lambda p: (p.is_file(), p.name.lower()))
        except Exception:
            return
        entries = [e for e in entries if e.name not in ignores]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                helper(entry, prefix + extension, current_depth + 1)
    lines.append(root.name + "/")
    helper(root, "", 1)
    return lines

def gather_stats(root: Path, ignores: set[str]):
    lang_counts = Counter()
    total_files = 0
    total_bytes = 0
    file_sizes = []
    folder_sizes = defaultdict(int)

    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored directories
        dirnames[:] = [d for d in dirnames if d not in ignores]
        rel_dir = Path(dirpath).relative_to(root)
        for f in filenames:
            if f in ignores: 
                continue
            p = Path(dirpath) / f
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            total_files += 1
            total_bytes += sz
            file_sizes.append((str(p.relative_to(root)), sz))
            parts = rel_dir.parts
            for i in range(1, len(parts)+1):
                folder_sizes[Path(*parts[:i]).as_posix()] += sz
            ext = p.suffix.lower()
            lang = EXT_LANG.get(ext)
            if lang:
                lang_counts[lang] += 1

    top_files = sorted(file_sizes, key=lambda x: x[1], reverse=True)[:15]
    top_folders = sorted(folder_sizes.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        "total_files": total_files,
        "total_bytes": total_bytes,
        "lang_counts": lang_counts,
        "top_files": top_files,
        "top_folders": top_folders
    }

def detect_manifests(root: Path):
    found = []
    for m in MANIFESTS:
        p = root / m
        if p.exists():
            found.append(m)
    return found

def git_info(root: Path):
    info = {}
    code, out, _ = run(["git", "rev-parse", "--is-inside-work-tree"], root)
    if code != 0 or out.strip() != "true":
        return {"is_git_repo": False}

    info["is_git_repo"] = True
    code, out, _ = run(["git", "remote", "-v"], root)
    info["remotes"] = out.splitlines() if out else []
    code, out, _ = run(["git", "branch", "--show-current"], root)
    info["current_branch"] = out.strip()
    code, out, _ = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes"], root)
    info["remote_branches"] = out.splitlines() if out else []
    code, out, _ = run(["git", "log", "--oneline", "-n", "10"], root)
    info["recent_commits"] = out.splitlines() if out else []
    return info

def make_markdown(
    root: Path,
    depth: int,
    ignores: set[str],
    stats: dict,
    manifests: list[str],
    git: dict,
    tree_lines: list[str]
) -> str:
    md = []
    md.append(f"# Project Summary — `{root.name}`\n")
    md.append(f"**Path:** `{root.as_posix()}`\n")
    md.append("## Git\n")
    if git.get("is_git_repo"):
        md.append(f"- Current branch: `{git.get('current_branch') or 'unknown'}`")
        if git.get("remotes"):
            md.append("- Remotes:")
            for r in git["remotes"]:
                md.append(f"  - `{r}`")
        if git.get("remote_branches"):
            md.append("- Remote branches (truncated):")
            for rb in git["remote_branches"][:10]:
                md.append(f"  - `{rb}`")
        if git.get("recent_commits"):
            md.append("- Recent commits:")
            for c in git["recent_commits"]:
                md.append(f"  - {c}")
    else:
        md.append("_Not a Git repository (or Git not available)._")
    md.append("")
    md.append("## Manifests & Config")
    if manifests:
        for m in manifests:
            md.append(f"- `{m}`")
    else:
        md.append("_None detected from common manifests._")
    md.append("")
    md.append("## Languages (by file count)")
    if stats["lang_counts"]:
        total_lang_files = sum(stats["lang_counts"].values())
        for lang, count in stats["lang_counts"].most_common():
            pct = (count / total_lang_files) * 100 if total_lang_files else 0
            md.append(f"- **{lang}**: {count} files ({pct:.1f}%)")
    else:
        md.append("_No recognized language extensions found._")
    md.append("")
    md.append("## Size & Files")
    md.append(f"- Total files scanned: **{stats['total_files']}**")
    md.append(f"- Total size: **{human_readable(stats['total_bytes'])}**")
    md.append("")
    if stats["top_folders"]:
        md.append("### Heaviest folders")
        for folder, sz in stats["top_folders"]:
            md.append(f"- `{folder or '.'}` — {human_readable(sz)}")
        md.append("")
    if stats["top_files"]:
        md.append("### Largest files")
        for path, sz in stats["top_files"]:
            md.append(f"- `{path}` — {human_readable(sz)}")
        md.append("")
    md.append(f"## Directory tree (depth ≤ {depth})")
    md.append(f"_Ignored: {', '.join(sorted(ignores))}_\n")
    md.append("```")
    md.extend(tree_lines)
    md.append("```\n")
    md.append("> Generated by `outline_repo.py`. Share this markdown to get a tailored walkthrough.")
    return "\n".join(md)

def human_readable(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024

def main():
    parser = argparse.ArgumentParser(description="Generate a Markdown summary of a repository/project.")
    parser.add_argument("path", nargs="?", default=".", help="Path to repo root (default: current directory).")
    parser.add_argument("--depth", type=int, default=3, help="Tree depth (default: 3).")
    parser.add_argument("--ignore", type=str, default=",".join(sorted(DEFAULT_IGNORES)),
                        help="Comma-separated names to ignore (dirs/files).")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists() or not root.is_dir():
        print(f"Path does not exist or is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    ignores = set([s.strip() for s in args.ignore.split(",") if s.strip()])
    stats = gather_stats(root, ignores)
    manifests = detect_manifests(root)
    git = git_info(root)
    tree_lines = scan_tree(root, args.depth, ignores)

    md = make_markdown(root, args.depth, ignores, stats, manifests, git, tree_lines)
    out_path = root / "PROJECT_SUMMARY.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}")
    print("\n--- Preview ---\n")
    print(md[:2000])  # preview first ~2000 chars

if __name__ == "__main__":
    main()
