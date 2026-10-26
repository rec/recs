"""Preserve unknown capture loss without inventing missing frame counts."""

from ufor.recording import AudioDiscontinuity, AudioStream, RecordingScore

from . import session_record


def preserve_audio_losses(
    document: RecordingScore, entries: list[session_record.Record]
) -> RecordingScore:
    located: dict[str, set[int]] = {}
    unlocated: set[str] = set()
    for entry in entries:
        if (
            isinstance(entry, session_record.EventRecord)
            and entry.type == 'input_overflow_unknown'
            and entry.clock_id is not None
            and entry.frame_count is not None
        ):
            located.setdefault(entry.clock_id, set()).add(entry.frame_count)
        if isinstance(entry, session_record.WarningRecord) and entry.message.startswith(
            'Device '
        ):
            message = entry.message[len('Device ') :]
            for suffix in (
                ': Dropped frame in PortAudio',
                ': PortAudio input overflow; lost frame count unknown',
            ):
                if message.endswith(suffix):
                    unlocated.add(message[: -len(suffix)])
            source, separator, status = message.partition(' input status:')
            if separator and 'input overflow' in status:
                unlocated.add(source)
    streams = []
    for stream in document.body.streams:
        if isinstance(stream, AudioStream):
            frames = {d.frame for d in stream.discontinuities}
            frames.update(
                f for f in located.get(stream.stream.timebase, set()) if f <= stream.end
            )
            source = stream.source_name or stream.source_id
            if source.startswith('audio:'):
                source = session_record.audio_stream_parts(source)[0]
            if source in unlocated and stream.stream.timebase not in located:
                frames.add(None)
            stream = stream.model_copy(
                update={
                    'discontinuities': [
                        AudioDiscontinuity(frame=f)
                        for f in sorted(f for f in frames if f is not None)
                    ]
                    + ([AudioDiscontinuity()] if None in frames else [])
                }
            )
        streams.append(stream)
    return document.model_copy(
        update={'body': document.body.model_copy(update={'streams': streams})}
    )
