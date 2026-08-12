"""The skill registry.

=======================================================================================
 ADDING A SKILL
 ---------------------------------------------------------------------------------------
 1. Create ``skills/builtin/<your_skill>.py`` with a module-level ``SKILL = Skill(...)``.
 2. Add its module name to ``MODULES`` below.

 That is the whole procedure. No new route, no new test, no execution path to write —
 the shared runner in ``services/skill_service.py`` handles every skill the same way,
 and the parameterised tests in ``tests/test_skills.py`` pick up the new one
 automatically.
=======================================================================================

Registration is explicit rather than scanning the directory. Auto-discovery would save this one
line and cost the ability to see, in one place, exactly what the platform offers — and it fails
silently when a module is misnamed, which is precisely when you want a loud error.
"""
from __future__ import annotations

from importlib import import_module

from skills.base import Skill

# One line per skill. Order is the order they appear in the UI.
MODULES = (
    "summarize",
    "research",
    "meeting_notes",
    "task_planner",
    "swot",
    "report",
    "email_draft",
    "code_review",
    "idea_generator",
)


def _load() -> dict[str, Skill]:
    registry: dict[str, Skill] = {}
    for module_name in MODULES:
        module = import_module(f"skills.builtin.{module_name}")
        skill = getattr(module, "SKILL", None)
        if not isinstance(skill, Skill):
            raise TypeError(
                f"skills/builtin/{module_name}.py must define a module-level "
                f"SKILL = Skill(...)"
            )
        if skill.slug in registry:
            raise ValueError(
                f"Two skills claim the slug {skill.slug!r}: "
                f"{registry[skill.slug].name} and {skill.name}"
            )
        registry[skill.slug] = skill
    return registry


SKILLS: dict[str, Skill] = _load()


def get(slug: str) -> Skill | None:
    return SKILLS.get(slug)


def all_skills() -> list[Skill]:
    return list(SKILLS.values())


def by_category() -> dict[str, list[Skill]]:
    grouped: dict[str, list[Skill]] = {}
    for skill in SKILLS.values():
        grouped.setdefault(skill.category, []).append(skill)
    return grouped
