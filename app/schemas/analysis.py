from typing import Any

from pydantic import BaseModel


class SpendingAnalysisResponse(BaseModel):
    analysis: str
    source: str
    insufficient_data: bool
    currency: str
    stats: dict[str, Any]
