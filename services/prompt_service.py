"""The prompt library, versioned by insertion.

**Editing a prompt never overwrites it.** The edit inserts a new row whose ``parent_id`` points
at the previous version and whose ``version`` increments; the old row is marked
``is_current=False`` and stays in the table forever.

The reason is traceability. A conversation from last week was produced by a specific prompt, and
if that prompt has since been "improved" then re-reading the conversation with the current text
in hand is misleading. Mutating in place destroys the only record of what actually ran — and
"why did this answer change?" becomes unanswerable.

The cost is rows that accumulate. That is the cheap half of the trade: storage is inexpensive and
history is not recoverable once discarded.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PromptTemplate

CATEGORIES = ("writing", "programming", "research", "business", "education", "custom")


def list_prompts(
    db: Session, user_id: int, workspace_id: int | None, category: str | None = None
) -> list[PromptTemplate]:
    """Current versions only, newest first.

    Superseded versions are excluded here and reachable through :func:`version_history`. A
    library that lists every historical revision alongside the live one is a library nobody can
    find anything in.
    """
    statement = select(PromptTemplate).where(
        PromptTemplate.user_id == user_id,
        PromptTemplate.is_current.is_(True),
        (PromptTemplate.workspace_id == workspace_id) | (PromptTemplate.workspace_id.is_(None)),
    )
    if category:
        statement = statement.where(PromptTemplate.category == category)
    return list(db.execute(statement.order_by(PromptTemplate.created_at.desc())).scalars())


def create(
    db: Session,
    user_id: int,
    workspace_id: int | None,
    title: str,
    body: str,
    category: str = "custom",
) -> PromptTemplate:
    prompt = PromptTemplate(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title.strip(),
        body=body.strip(),
        category=category if category in CATEGORIES else "custom",
        version=1,
        is_current=True,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def edit(
    db: Session,
    current: PromptTemplate,
    title: str | None = None,
    body: str | None = None,
    category: str | None = None,
) -> PromptTemplate:
    """Create the next version. The row passed in is retired, not modified.

    A change that alters nothing returns the existing row rather than minting an identical
    version — otherwise opening and saving a prompt without touching it would inflate the
    history and make the version number meaningless.
    """
    new_title = (title if title is not None else current.title).strip()
    new_body = (body if body is not None else current.body).strip()
    new_category = category if category in CATEGORIES else current.category

    unchanged = (
        new_title == current.title
        and new_body == current.body
        and new_category == current.category
    )
    if unchanged:
        return current

    current.is_current = False
    successor = PromptTemplate(
        user_id=current.user_id,
        workspace_id=current.workspace_id,
        title=new_title,
        body=new_body,
        category=new_category,
        version=current.version + 1,
        parent_id=current.id,
        is_current=True,
        # Usage follows the prompt, not the revision: a prompt used forty times is still that
        # prompt after an edit, and resetting the count would hide how much it is relied on.
        use_count=current.use_count,
    )
    db.add(successor)
    db.commit()
    db.refresh(successor)
    return successor


def version_history(db: Session, prompt: PromptTemplate) -> list[PromptTemplate]:
    """Every version of this prompt, oldest first.

    Walks ``parent_id`` backwards from the given row and then forwards through its descendants,
    so the full chain is returned whichever version was asked about.
    """
    root = prompt
    seen: set[int] = set()
    while root.parent_id is not None and root.parent_id not in seen:
        seen.add(root.id)
        parent = db.get(PromptTemplate, root.parent_id)
        if parent is None:
            break
        root = parent

    chain = [root]
    cursor = root
    while True:
        child = db.execute(
            select(PromptTemplate).where(PromptTemplate.parent_id == cursor.id)
        ).scalar_one_or_none()
        if child is None:
            break
        chain.append(child)
        cursor = child
    return chain


def mark_used(db: Session, prompt: PromptTemplate) -> None:
    prompt.use_count += 1
    db.commit()


def delete_chain(db: Session, prompt: PromptTemplate) -> int:
    """Delete a prompt and every version of it.

    Deleting only the current version would leave orphaned history that the library cannot show
    and the user cannot reach — worse than either keeping it or removing it cleanly.
    """
    chain = version_history(db, prompt)
    # Children first: parent_id is ON DELETE SET NULL, and clearing it mid-delete would break
    # the walk for anything still to come.
    for row in reversed(chain):
        db.delete(row)
    db.commit()
    return len(chain)
