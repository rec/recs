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
            },
            {'channel': '1', 'on': Active.inactive, 'volume': 0.5},
            {'channel': '2', 'on': Active.offline, 'volume': 0.0},
        ]
    )

    assert view.columns == presentation.COLUMNS
    assert view.rows[0].cells[0].text == '      4.143'
    assert view.rows[0].cells[5].text == '  1.23 MB'
    assert view.rows[1].cells[1].text == 'MacBook Pro Microphone'
    assert view.rows[1].cells[3].text == '•'
    assert view.rows[1].cells[3].style == 'active'
    assert view.rows[2].cells[2].text == ' 1 '
    assert view.rows[2].cells[7].text == ' 50.0%'
    assert view.rows[2].cells[7].style == 'volume-high'
    assert view.rows[3].cells[3].text == 'ˣ'
    assert view.rows[3].cells[3].style == 'offline'
