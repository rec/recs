import typing as t
from contextlib import ExitStack, contextmanager


@contextmanager
def contexts(*contexts: t.ContextManager) -> t.Generator:
    with ExitStack() as stack:
        for c in contexts:
            stack.enter_context(c)
        yield
