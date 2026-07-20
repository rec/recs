from recs.base.types import Active
from recs.ui import presentation


def test_view_model_formats_recording_rows() -> None:
    view = presentation.view_model(
        [
            {
                'time': 4.143,
                'recorded': 0,
                'file_size': 1234567,
                'file_count': 2,
            },
            {
                'device': 'MacBook Pro Microphone',
                'on': Active.active,
                'buffer': 0.25,
                'dropped': 512,
            },
            {'channel': '1', 'on': Active.inactive, 'volume': 0.5},
            {'channel': '2', 'on': Active.offline, 'volume': 0.0},
            {'channel': '3', 'signal': 0.0},
            {'channel': '4', 'signal': 0.1},
            {'channel': '5', 'signal': 0.5},
            {'channel': '6', 'signal': 0.95},
        ]
    )

    assert view.columns == presentation.COLUMNS
    assert view.rows[0].cells[0].text == '      4.143'
    assert view.rows[0].cells[8].text == '  1.23 MB'
    assert view.rows[1].cells[1].text == 'MacBook Pro Microphone'
    assert view.rows[1].cells[3].text == '•'
    assert view.rows[1].cells[3].style == 'active'
    assert view.rows[1].cells[5].text == '0.250s'
    assert view.rows[1].cells[6].text == '512'
    assert view.rows[2].cells[2].text == ' 1 '
    assert view.rows[2].cells[10].text == ' 50.0%'
    assert view.rows[2].cells[10].style == 'volume-high'
    assert view.rows[3].cells[3].text == 'ˣ'
    assert view.rows[3].cells[3].style == 'offline'
    assert view.rows[4].cells[4].style == 'signal-quiet'
    assert view.rows[5].cells[4].style == 'signal-normal'
    assert view.rows[6].cells[4].style == 'signal-hot'
    assert view.rows[7].cells[4].style == 'signal-peak'
