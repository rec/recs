from pathlib import Path

from reccy import ipc

WINDOWS_PIPE = r'\\.\pipe\recs'

GuiConnection = ipc.Connection
GuiServerBackend = ipc.ServerBackend
UnixSocketServerBackend = ipc.UnixSocketServerBackend
UnixSocketConnection = ipc.UnixSocketConnection
WindowsPipeServerBackend = ipc.WindowsPipeServerBackend
WindowsPipeConnection = ipc.WindowsPipeConnection


def server_backend(endpoint: str | Path) -> GuiServerBackend:
    return ipc.server_backend(endpoint)


def client_connection(endpoint: str | Path) -> GuiConnection:
    return ipc.client_connection(endpoint)
