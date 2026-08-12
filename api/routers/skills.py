"""Skills and the prompt library.

Both live here because they are the same idea at different levels: a prompt template is text the
user reuses, and a skill is a prompt the platform ships and maintains.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from db.models import Conversation, PromptTemplate, Skill as SkillRow
from schemas.skill import (
    PromptCreate,
    PromptResponse,
    PromptUpdate,
    SkillRunRequest,
    SkillRunResponse,
    SkillSummary,
)
from services import prompt_service, skill_service
from services.llm_service import LLMError
from skills import registry

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["skills"])


# ----------------------------------------------------------------------- skills
@router.get("/skills", response_model=list[SkillSummary])
def list_skills(workspace: OwnedWorkspace, db: DbSession) -> list[SkillSummary]:
    """Every registered skill, with how often it has been run.

    Definitions come from the code registry rather than the database, so a newly added skill is
    available the moment the server restarts — no migration, no manual insert.
    """
    counts = {row.slug: row.use_count for row in db.execute(select(SkillRow)).scalars()}
    return [
        SkillSummary(
            slug=skill.slug,
            name=skill.name,
            category=skill.category,
            description=skill.description,
            icon=skill.icon,
            input_label=skill.input_label,
            input_placeholder=skill.input_placeholder,
            uses_documents=skill.uses_documents,
            structured=skill.output_schema is not None,
            examples=list(skill.examples),
            use_count=counts.get(skill.slug, 0),
        )
        for skill in registry.all_skills()
    ]


@router.post("/skills/{slug}/run", response_model=SkillRunResponse)
def run_skill(
    slug: str,
    payload: SkillRunRequest,
    workspace: OwnedWorkspace,
    user: CurrentUser,
    db: DbSession,
) -> SkillRunResponse:
    conversation = None
    if payload.conversation_id is not None:
        conversation = db.execute(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.workspace_id == workspace.id,
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )

    try:
        result = skill_service.run(
            db, workspace, slug, payload.input, user.id, conversation=conversation
        )
    except skill_service.UnknownSkill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No skill called {slug!r}. Available: {', '.join(registry.SKILLS)}",
        )
    except LLMError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))

    return SkillRunResponse(
        slug=result.slug,
        message_id=result.message_id,
        output=result.output,
        structured=result.structured,
        citations=result.citations,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        latency_ms=result.latency_ms,
    )


# --------------------------------------------------------------- prompt library
def _load_prompt(db, user_id: int, prompt_id: int) -> PromptTemplate:
    prompt = db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id, PromptTemplate.user_id == user_id
        )
    ).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    return prompt


@router.get("/prompts", response_model=list[PromptResponse])
def list_prompts(
    workspace: OwnedWorkspace, user: CurrentUser, db: DbSession, category: str | None = None
) -> list[PromptResponse]:
    rows = prompt_service.list_prompts(db, user.id, workspace.id, category)
    return [PromptResponse.model_validate(p) for p in rows]


@router.post("/prompts", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptCreate, workspace: OwnedWorkspace, user: CurrentUser, db: DbSession
) -> PromptResponse:
    prompt = prompt_service.create(
        db, user.id,
        workspace.id if payload.workspace_scoped else None,
        payload.title, payload.body, payload.category,
    )
    return PromptResponse.model_validate(prompt)


@router.patch("/prompts/{prompt_id}", response_model=PromptResponse)
def edit_prompt(
    prompt_id: int, payload: PromptUpdate, workspace: OwnedWorkspace,
    user: CurrentUser, db: DbSession,
) -> PromptResponse:
    """Editing returns the **new** version. The row you sent is retired, not changed."""
    current = _load_prompt(db, user.id, prompt_id)
    successor = prompt_service.edit(db, current, payload.title, payload.body, payload.category)
    return PromptResponse.model_validate(successor)


@router.get("/prompts/{prompt_id}/history", response_model=list[PromptResponse])
def prompt_history(
    prompt_id: int, workspace: OwnedWorkspace, user: CurrentUser, db: DbSession
) -> list[PromptResponse]:
    """Every version, oldest first — what this prompt used to say."""
    prompt = _load_prompt(db, user.id, prompt_id)
    return [PromptResponse.model_validate(p) for p in prompt_service.version_history(db, prompt)]


@router.post("/prompts/{prompt_id}/use", response_model=PromptResponse)
def use_prompt(
    prompt_id: int, workspace: OwnedWorkspace, user: CurrentUser, db: DbSession
) -> PromptResponse:
    """Record that a prompt was used, and hand back its text."""
    prompt = _load_prompt(db, user.id, prompt_id)
    prompt_service.mark_used(db, prompt)
    return PromptResponse.model_validate(prompt)


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(
    prompt_id: int, workspace: OwnedWorkspace, user: CurrentUser, db: DbSession
) -> None:
    prompt_service.delete_chain(db, _load_prompt(db, user.id, prompt_id))
