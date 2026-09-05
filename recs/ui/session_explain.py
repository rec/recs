import sys
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field
from reccy.protocol import rpc

from recs.daemon import paths

from . import session_record


class Explanation(BaseModel):
    reason: str
    evidence: str


class ExplanationReport(BaseModel):
    target: str
    explanations: list[Explanation] = Field(default_factory=list)


def main(argv: list[str]) -> int:
    json_output = False
    if '--json' in argv:
        json_output = True
        argv = [arg for arg in argv if arg != '--json']
    report = explain(Path(argv[0])) if argv else explain_daemon()
    if json_output:
        print(report.model_dump_json(indent=2))
    else:
        for explanation in report.explanations:
            print(f'{explanation.reason}: {explanation.evidence}')
    return int(not report.explanations)


def explain(path: Path) -> ExplanationReport:
    try:
        record = session_record.read(path)
    except OSError as e:
        return ExplanationReport(
            target=path.as_posix(),
            explanations=[Explanation(reason='record unreadable', evidence=str(e))],
        )
    explanations: list[Explanation] = []
    if not record.started_at:
        explanations.append(
            Explanation(reason='record header is missing', evidence=path.as_posix())
        )
    if not any(f.type == 'file_finished' for f in record.files):
        explanations.extend(_no_file_explanations(record))
    explanations.extend(_warning_explanations(record))
    explanations.extend(_event_explanations(record))
    if not explanations:
        explanations.append(
            Explanation(
                reason='no obvious recording problem found',
                evidence=path.as_posix(),
            )
        )
    return ExplanationReport(target=path.as_posix(), explanations=explanations)


def explain_daemon() -> ExplanationReport:
    try:
        status = rpc.Client(paths.external_control_endpoint(), role='explain').call(
            'status_snapshot'
        )
    except (BrokenPipeError, ConnectionError, OSError, TimeoutError) as e:
        return ExplanationReport(
            target='daemon',
            explanations=[
                Explanation(reason='daemon status unavailable', evidence=str(e))
            ],
        )
    explanations: list[Explanation] = []
    if isinstance(status, dict):
        recording = status.get('recording')
        if isinstance(recording, dict):
            recording = cast(dict[str, object], recording)
            if recording.get('paused'):
                explanations.append(
                    Explanation(
                        reason='recording is paused',
                        evidence='status_snapshot recording.paused is true',
                    )
                )
        errors = status.get('errors', [])
        if isinstance(errors, list):
            errors = cast(list[object], errors)
        else:
            errors = []
        for error in errors:
            if not isinstance(error, dict):
                continue
            error = cast(dict[str, object], error)
            if message := error.get('message'):
                explanations.append(
                    Explanation(
                        reason='daemon reported an error',
                        evidence=str(message),
                    )
                )
    if not explanations:
        explanations.append(
            Explanation(
                reason='no obvious recording problem found',
                evidence='status_snapshot returned without errors',
            )
        )
    return ExplanationReport(target='daemon', explanations=explanations)


def _no_file_explanations(
    record: session_record.SessionRecord,
) -> list[Explanation]:
    if any(f.type == 'file_started' for f in record.files):
        return [
            Explanation(
                reason='files started but did not finish',
                evidence=(
                    'record has file_started records without ' 'file_finished records'
                ),
            )
        ]
    if not record.ended_at:
        return [
            Explanation(
                reason='session did not finish cleanly',
                evidence='record footer is missing',
            )
        ]
    return [
        Explanation(
            reason='no files were recorded',
            evidence=(
                'record has no file_finished records; audio may have stayed below '
                'noise floor or files may have been shorter than shortest_file_time'
            ),
        )
    ]


def _warning_explanations(
    record: session_record.SessionRecord,
) -> list[Explanation]:
    explanations: list[Explanation] = []
    for message in record.warnings + record.errors:
        if 'No input devices detected' in message:
            reason = 'no matching input devices'
        elif 'offline' in message:
            reason = 'selected device went offline'
        elif 'input channels' in message:
            reason = 'selected channels were unavailable'
        elif 'lagging behind' in message:
            reason = 'source process lagged'
        else:
            reason = 'record warning'
        explanations.append(Explanation(reason=reason, evidence=message))
    return explanations


def _event_explanations(
    record: session_record.SessionRecord,
) -> list[Explanation]:
    explanations: list[Explanation] = []
    for event in record.events:
        if event.type == 'recording_paused':
            explanations.append(
                Explanation(
                    reason='recording paused',
                    evidence=event.reason or event.label or event.timestamp,
                )
            )
        elif event.type == 'disk_emergency':
            explanations.append(
                Explanation(reason='disk emergency occurred', evidence=event.timestamp)
            )
        elif event.type == 'disk_switch_failed':
            explanations.append(
                Explanation(reason='disk switch failed', evidence=event.timestamp)
            )
        elif event.type == 'buffer_overflow':
            explanations.append(
                Explanation(reason='audio buffer overflowed', evidence=event.timestamp)
            )
        elif event.type == 'midi_source_failed':
            explanations.append(
                Explanation(
                    reason='MIDI input failed',
                    evidence=event.value
                    if isinstance(event.value, str)
                    else event.timestamp,
                )
            )
        elif event.type == 'midi_source_stopped':
            explanations.append(
                Explanation(
                    reason='MIDI input disconnected',
                    evidence=event.midi_port or event.timestamp,
                )
            )
    return explanations


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
