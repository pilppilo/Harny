"""Errors raised by the Vharness session library."""


class AgentError(RuntimeError):
    """Base class for caller-visible session library failures."""


class ContractError(AgentError, ValueError):
    """A caller or external boundary supplied invalid data."""


class TransitionError(AgentError):
    """A requested local state transition is not currently legal."""


class PersistenceError(AgentError):
    """A durable session record could not be read or written."""


class IntegrityError(PersistenceError):
    """Required durable state or evidence is corrupt or incompatible."""
