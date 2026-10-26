#!/usr/bin/env python3

from pathlib import Path

# CHANGE THIS
REPO_ROOT = r"."

OUTFILE = "repo_dump.txt"

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".pytest_cache",
    "node_modules",
}

SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pyc",
}

root = Path(REPO_ROOT)

with open(OUTFILE, "w", encoding="utf-8") as out:

    out.write(f"REPOSITORY ROOT: {root}\n\n")

    files = sorted(
        f
        for f in root.rglob("*")
        if f.is_file()
        and not any(part in SKIP_DIRS for part in f.parts)
        and f.suffix.lower() not in SKIP_EXTENSIONS
    )

    for file in files:

        rel = file.relative_to(root)

        out.write("\n")
        out.write("=" * 100 + "\n")
        out.write(f"FILE: {rel}\n")
        out.write("=" * 100 + "\n\n")

        try:
            content = file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            out.write(content)

        except Exception as ex:
            out.write(f"[ERROR READING FILE: {ex}]")

        out.write("\n")

print(
    f"Dumped {len(files)} files to {OUTFILE}"
)
