"""Typed errors. Every failure in the app is one of these."""


class HealthCoachError(Exception):
    """Base class for everything this app raises."""
    user_message = "Something went wrong. Please try again."


class ValidationError(HealthCoachError):
    """A logged value was outside a plausible range."""
    def __init__(self, message: str, field: str = "", value=None):
        super().__init__(message)
        self.user_message = message
        self.field = field
        self.value = value


class AgentError(HealthCoachError):
    """An agent failed while handling a request."""
    def __init__(self, agent: str, message: str):
        super().__init__(f"[{agent}] {message}")
        self.agent = agent
        self.user_message = (
            "I had trouble with that one. Could you rephrase it?"
        )


class ServiceUnavailable(HealthCoachError):
    """An external service (Azure) could not be reached after retries."""
    def __init__(self, service: str, detail: str = ""):
        super().__init__(f"{service} unavailable: {detail}")
        self.service = service
        self.user_message = (
            "I'm running in offline mode right now, so my answer is based on "
            "your logged data only."
        )
