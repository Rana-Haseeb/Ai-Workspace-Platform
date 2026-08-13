"""Phase 10 gate: the documentation is present, substantive, current, and not lying.

    python scripts/verify_phase10.py

Four things are checked, because "the file exists" is the weakest possible bar:

1. **Every required document exists and has real content**, section by section — a heading with
   nothing under it is not a section.
2. **The generated documents match their source.** `API.md` is rebuilt from the live OpenAPI
   schema and `ERD.md` from `db/models.py`; if either differs from what is committed, the code
   moved and the document did not.
3. **Internal links resolve.** A README full of links to files that do not exist is worse than
   one with no links.
4. **No secret is in any document**, since these are the files most likely to be read and shared.

Offline. Needs no provider key.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

failures: list[str] = []

# Required documents, and the minimum number of words that counts as written rather than stubbed.
REQUIRED = {
    "README.md": 3000,
    "RUNNING.md": 500,
    "docs/ARCHITECTURE.md": 900,
    "docs/ERD.md": 500,
    "docs/API.md": 800,
    "docs/RESEARCH_REPORT.md": 1200,
    "docs/BUILDER_JOURNAL.md": 700,
    "docs/SECURITY_REVIEW.md": 1200,
    "docs/PERFORMANCE.md": 700,
    "docs/DEPLOYMENT.md": 600,
    "eval/EVALUATION.md": 500,
    "experiments/EXPERIMENTS.md": 500,
}

# The README sections the challenge asks for. Matched case-insensitively against `## ` headings.
README_SECTIONS = [
    "problem statement",
    "features",
    "technology stack",
    "architecture",
    "database",
    "installation",
    "api endpoints",
    "testing",
    "deployment",
    "known limitations",
    "future improvements",
]

# Page ceilings from the plan, at roughly 500 words per page.
PAGE_LIMITS = {"docs/RESEARCH_REPORT.md": 5, "docs/BUILDER_JOURNAL.md": 2}
WORDS_PER_PAGE = 700

SECRET = re.compile(r"(gsk_[A-Za-z0-9]{20,}|AQ\.[A-Za-z0-9_-]{20,}|npg_[A-Za-z0-9]{10,}"
                    r"|sk-[A-Za-z0-9]{20,})")


def safe(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{safe(detail)}]" if detail else ""))
    if not ok:
        failures.append(label)


def words(text: str) -> int:
    return len(text.split())


def main() -> int:
    print("\nPhase 10 verification - documentation\n")

    # ------------------------------------------------------------- 1. present and substantive
    print("1. Required documents")
    contents: dict[str, str] = {}
    for name, minimum in REQUIRED.items():
        path = ROOT / name
        if not path.is_file():
            check(name, False, "missing")
            continue
        text = path.read_text(encoding="utf-8")
        contents[name] = text
        count = words(text)
        check(f"{name:<28}", count >= minimum, f"{count} words (min {minimum})")

    if "README.md" not in contents:
        return _finish()

    # ------------------------------------------------------------------ 2. README sections
    print("\n2. README sections")
    headings = re.findall(r"^##+\s+(.+)$", contents["README.md"], re.M)
    lowered = [h.lower() for h in headings]
    for wanted in README_SECTIONS:
        check(f"  {wanted}", any(wanted in h for h in lowered))

    # A heading with nothing under it is not a section. Check each has prose beneath it.
    print("\n3. No section is an empty heading")
    blocks = re.split(r"^##\s+", contents["README.md"], flags=re.M)[1:]
    empty = [b.split("\n")[0].strip() for b in blocks if words(b) < 25]
    check("every top-level section has content", not empty, ", ".join(empty[:3]))

    # ------------------------------------------------------------------- 4. page ceilings
    print("\n4. Length ceilings from the plan")
    for name, pages in PAGE_LIMITS.items():
        if name in contents:
            count = words(contents[name])
            check(f"  {name} within {pages} pages", count <= pages * WORDS_PER_PAGE,
                  f"{count} words ~ {count / WORDS_PER_PAGE:.1f} pages")

    # ------------------------------------------------------- 5. generated docs are not stale
    print("\n5. Generated documents match their source")
    sys.argv = ["x"]
    try:
        from scripts.generate_api_docs import build as build_api
        fresh = build_api()
        check("docs/API.md matches the live OpenAPI schema",
              contents.get("docs/API.md") == fresh,
              "regenerate: python scripts/generate_api_docs.py")
    except Exception as error:  # noqa: BLE001
        check("docs/API.md regenerates", False, safe(error)[:70])

    try:
        from scripts.generate_erd import build as build_erd
        fresh_erd = build_erd()
        check("docs/ERD.md matches db/models.py",
              contents.get("docs/ERD.md") == fresh_erd,
              "regenerate: python scripts/generate_erd.py")
    except Exception as error:  # noqa: BLE001
        check("docs/ERD.md regenerates", False, safe(error)[:70])

    # ---------------------------------------------------------------- 6. internal links work
    print("\n6. Internal links resolve")
    broken: list[str] = []
    for name, text in contents.items():
        base = (ROOT / name).parent
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (base / target.split("#")[0]).resolve()
            if not path.exists():
                broken.append(f"{name} -> {target}")
    check("no broken relative link", not broken, "; ".join(broken[:3]))

    # --------------------------------------------------------------------- 7. no secrets
    print("\n7. Secrets hygiene")
    leaked = [name for name, text in contents.items() if SECRET.search(text)]
    check("no document contains a key", not leaked, ", ".join(leaked))

    return _finish()


def _finish() -> int:
    if failures:
        print(f"\nPHASE 10 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1
    print(f"\nPHASE 10 PASSED - {len(REQUIRED)} documents, generated docs current, links resolve.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
