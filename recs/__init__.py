from .recs import RECS

__all__ = 'RECS', 'RecsError'


class RecsError(ValueError):
    pass
