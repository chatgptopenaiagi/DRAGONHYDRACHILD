"""Recovered analysis-only LocalAI boundary; no machine action authority."""

from .client import LocalAIClient
from .contracts import (AnalysisRequest, AnalysisResponse, Conclusion, ContractError,
                        EvidenceSummary, ForecastSummary, Snapshot, UncertaintySummary)

__all__ = ["LocalAIClient", "AnalysisRequest", "AnalysisResponse", "Conclusion", "ContractError",
           "EvidenceSummary", "ForecastSummary", "Snapshot", "UncertaintySummary"]
