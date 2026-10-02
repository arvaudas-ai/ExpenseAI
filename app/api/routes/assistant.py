from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.ai_rate_limit import ai_request_limiter
from app.services.financial_context import build_financial_context
from app.services import providers

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    payload: AssistantChatRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssistantChatResponse:
    ai_request_limiter.check(current_user.id)
    context = build_financial_context(current_user, db)
    try:
        provider = providers.get_provider()
        answer = await asyncio.to_thread(provider.answer, payload.message, context)
    except providers.ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The financial assistant is not configured yet.",
        ) from exc
    except providers.ProviderRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The financial assistant is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The financial assistant could not complete that request.",
        ) from exc

    return AssistantChatResponse(
        answer=answer,
        source=provider.source,
        currency=str(context["currency"]),
        metrics={
            "total_spending": context["total_spending"],
            "expense_count": context["expense_count"],
            "current_month_total": context["current_month_total"],
            "top_category": context["category_totals"][0]["name"] if context["category_totals"] else None,
        },
    )
