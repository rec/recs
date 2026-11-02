import os
import struct
from multiprocessing import Pipe
from time import monotonic

from recs.runtime.source_transport import SourceControlHandler


def test_partial_control_message_does_not_block_consumer_or_shutdown() -> None:
    receiver, sender = Pipe(duplex=False)
    handler = SourceControlHandler(
        receiver,
        lambda cfg, revision: None,
        lambda directory: None,
        lambda names: None,
        lambda tracks: None,
        lambda tracks, names: None,
        lambda enabled: None,
        lambda enabled, recovery: None,
    )
    try:
        os.write(sender.fileno(), struct.pack('!i', 4096) + b'partial')
        started = monotonic()
        for _ in range(100):
            handler.receive()
        handler.close()
        assert monotonic() - started < 0.5
    finally:
        sender.close()
        handler.thread.join(1)
        receiver.close()
