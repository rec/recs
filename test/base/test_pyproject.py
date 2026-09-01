from email.message import Message

from recs.base import pyproject


def test_message_uses_installed_package_metadata(monkeypatch) -> None:
    metadata = Message()
    metadata['Name'] = 'recs'
    metadata['Summary'] = '🎙 The Universal Recorder 🎙'
    monkeypatch.setattr(pyproject, 'metadata', lambda name: metadata)

    assert pyproject.message() == '🎙 recs: The Universal Recorder 🎙'
