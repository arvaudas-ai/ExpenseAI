from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.schemas.analysis import SpendingAnalysisResponse
from app.services import providers
from app.services.ai_rate_limit import ai_request_limiter
from app.services.spending_analysis import build_spending_analysis_stats

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/spending", response_model=SpendingAnalysisResponse)
async def analyze_spending(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SpendingAnalysisResponse:
    ai_request_limiter.check(current_user.id)
    stats = build_spending_analysis_stats(current_user, db)
    if not stats["has_enough_data"]:
        return SpendingAnalysisResponse(
            analysis="Add at least three expenses to see a grounded spending analysis. Your analysis will compare your own monthly, category, and payment patterns.",
            source="calculated",
            insufficient_data=True,
            currency=current_user.currency,
            stats=stats,
        )

    try:
        provider = providers.get_provider()
        analysis = await asyncio.to_thread(provider.analyze, stats)
    except providers.ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Spending analysis is not configured yet. Use the local assistant provider or configure the server-side AI provider.",
        ) from exc
    except providers.ProviderRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spending analysis is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spending analysis could not be completed.",
        ) from exc

    return SpendingAnalysisResponse(
        analysis=analysis,
        source=provider.source,
        insufficient_data=False,
        currency=current_user.currency,
        stats=stats,
    )
