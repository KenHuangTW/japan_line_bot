from __future__ import annotations


class LodgingDecisionSummaryError(RuntimeError):
    pass


class LodgingDecisionSummaryConfigurationError(LodgingDecisionSummaryError):
    pass


class LodgingDecisionSummaryEmptyTripError(LodgingDecisionSummaryError):
    pass


class LodgingDecisionSummaryProviderError(LodgingDecisionSummaryError):
    pass


class LodgingDecisionSummaryTimeoutError(LodgingDecisionSummaryProviderError):
    pass


class LodgingDecisionSummaryInvalidResponseError(LodgingDecisionSummaryError):
    pass
