from pathlib import Path

from reccy import ipc

WINDOWS_PIPE = r'\\.\pipe\recs'


def server_backend(endpoint: str | Path) -> ipc.ServerBackend:
    return ipc.server_backend(endpoint)


def client_connection(endpoint: str | Path) -> ipc.Connection:
    return ipc.client_connection(endpoint)
