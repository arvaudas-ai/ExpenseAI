from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import Settings, get_settings


class ProviderConfigurationError(Exception):
    """Raised when an optional external provider is not configured safely."""


class ProviderRequestError(Exception):
    """Raised when an external provider cannot answer a request."""


class FinancialAssistantProvider(ABC):
    source = "provider"

    @abstractmethod
    def answer(self, question: str, context: dict[str, Any]) -> str:
        raise NotImplementedError

    def analyze(self, statistics: dict[str, Any]) -> str:
        raise ProviderRequestError("This provider does not support spending analysis.")


class LocalFinancialAssistant(FinancialAssistantProvider):
    source = "calculated"

    def _money(self, amount: float, currency: str) -> str:
        return f"{currency} {amount:,.2f}"

    def answer(self, question: str, context: dict[str, Any]) -> str:
        normalized = question.lower()
        currency = context["currency"]
        current_month = context["current_month"]

        if "compare" in normalized or "last month" in normalized or "month over month" in normalized:
            current = self._money(context["current_month_total"], currency)
            previous = self._money(context["previous_month_total"], currency)
            change = context["month_over_month_change_percent"]
            if change is None:
                return f"You spent {current} in {current_month} and {previous} in {context['previous_month']}. There is not enough prior spending to calculate a percentage change."
            direction = "more" if change > 0 else "less" if change < 0 else "the same amount"
            return f"You spent {current} in {current_month} versus {previous} in {context['previous_month']}, which is {direction} ({abs(change):.2f}% change)."

        if "most" in normalized or "highest" in normalized or "top categor" in normalized:
            categories = context["category_totals"]
            if not categories:
                return "There is not enough expense data to identify a highest-spending category yet."
            top = categories[0]
            return f"Your highest-spending category is {top['name']} at {self._money(top['total'], currency)}."

        if "biggest" in normalized or "largest" in normalized:
            expenses = context["highest_expenses"]
            if not expenses:
                return "You do not have any recorded expenses yet."
            top = expenses[0]
            return f"Your largest expense is {top['description']} for {self._money(top['amount'], currency)} on {top['date']} in {top['category']}."

        if "summary" in normalized or "summarize" in normalized:
            category = context["category_totals"][0]["name"] if context["category_totals"] else "No category yet"
            largest = context["highest_expenses"][0] if context["highest_expenses"] else None
            largest_text = f" Your largest expense was {largest['description']} at {self._money(largest['amount'], currency)}." if largest else ""
            change = context["month_over_month_change_percent"]
            change_text = f" Month over month, spending changed by {change:.2f}%." if change is not None else ""
            return f"You have spent {self._money(context['total_spending'], currency)} across {context['expense_count']} expenses. Your top category is {category}.{largest_text}{change_text}"

        if "this month" in normalized or "spent" in normalized or "spending" in normalized:
            return f"You spent {self._money(context['current_month_total'], currency)} in {current_month} across {context['current_month_count']} expense(s)."

        return "I can help analyze your ExpenseAI spending. Ask about this month's total, your top category, biggest expenses, a summary, or a comparison with last month."

    def analyze(self, statistics: dict[str, Any]) -> str:
        if not statistics["expense_count"]:
            return "There is not enough expense history to identify spending patterns yet."
        currency = statistics["currency"]
        categories = statistics["category_totals"]
        top_category = ""
        if categories:
            top = categories[0]
            top_category = f" Your largest category is {top['category']} at {currency} {top['total']:,.2f} ({top['share_percent']:.1f}% of tracked spending)."
        comparison = statistics["month_over_month"]
        if comparison["change_percent"] is None:
            month_change = " There is not enough prior-month spending to calculate a percentage change."
        else:
            change = comparison["change_percent"]
            direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
            month_change = f" Spending is {direction} {abs(change):.1f}% versus last month ({currency} {comparison['previous_total']:,.2f} to {currency} {comparison['current_total']:,.2f})."
        spike = statistics["current_month_spike"]
        spike_text = (
            f" This month's total is {spike['multiple_of_average']:.1f} times your average in prior active months."
            if spike else " No unusual current-month spike was detected against your available active-month history."
        )
        recurring_text = (
            f" Repeated patterns appeared in {len(statistics['recurring_patterns'])} group(s); these are signals, not confirmed subscriptions."
            if statistics["recurring_patterns"] else " There is not enough repeated activity across months to flag recurring-looking spending."
        )
        return (
            f"Across {statistics['expense_count']} expenses from {statistics['period_start']} to {statistics['period_end']}, "
            f"tracked spending is {currency} {statistics['total_spending']:,.2f}, averaging {currency} {statistics['average_expense']:,.2f} per expense."
            f"{top_category}{month_change}{spike_text}{recurring_text} These are observations from your recorded expenses, not financial advice."
        )


class OpenAICompatibleAssistant(FinancialAssistantProvider):
    source = "provider"

    def __init__(self, settings: Settings) -> None:
        if not settings.ai_api_key:
            raise ProviderConfigurationError("The configured AI provider is missing its API key.")
        self.settings = settings

    def answer(self, question: str, context: dict[str, Any]) -> str:
        payload = {
            "model": self.settings.ai_model,
            "messages": [
                {"role": "system", "content": "You are an ExpenseAI spending-analysis assistant. Use only the supplied financial context. State calculations as facts, do not provide investment advice, and never invent numbers."},
                {"role": "user", "content": json.dumps({"question": question, "financial_context": context}, ensure_ascii=True)},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            self.settings.ai_base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.settings.ai_api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.ai_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            answer = body["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ProviderRequestError("The AI provider returned an empty response.")
            return answer.strip()
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderRequestError("The AI provider could not complete the request.") from exc

    def analyze(self, statistics: dict[str, Any]) -> str:
        return self.answer(
            "Explain these computed spending patterns concisely. Separate measured facts from observations, state when history is insufficient, do not call repeated patterns confirmed subscriptions, and do not provide financial advice.",
            statistics,
        )


def get_provider(settings: Settings | None = None) -> FinancialAssistantProvider:
    current_settings = settings or get_settings()
    if current_settings.ai_provider == "local":
        return LocalFinancialAssistant()
    if current_settings.ai_provider == "openai_compatible":
        return OpenAICompatibleAssistant(current_settings)
    raise ProviderConfigurationError("The configured AI provider is not supported.")
