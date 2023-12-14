from .conftest import BLOCK_SIZE


def run_streams(test_case):
    # Send data to the streams, setting time accordingly
    assert BLOCK_SIZE
