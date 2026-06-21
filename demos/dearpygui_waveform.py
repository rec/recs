import collections.abc as cabc

import dearpygui.dearpygui as dpg
from waveform_source import WINDOW_HEIGHT, WINDOW_WIDTH, WaveformSource


def main() -> None:
    source = WaveformSource()

    dpg.create_context()
    dpg.create_viewport(
        title='Dear PyGui waveform demo',
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
    )

    with dpg.window(
        label='Recording waveform',
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        no_resize=True,
    ):
        with dpg.plot(
            label='',
            width=WINDOW_WIDTH - 24,
            height=WINDOW_HEIGHT - 52,
            no_title=True,
        ):
            dpg.add_plot_axis(dpg.mvXAxis, label='seconds', tag='x_axis')
            dpg.add_plot_axis(dpg.mvYAxis, label='amplitude', tag='y_axis')
            dpg.set_axis_limits('y_axis', -1.1, 1.1)
            dpg.add_line_series([], [], parent='y_axis', tag='waveform')

    _style_waveform()
    dpg.set_frame_callback(1, _refresh(source))
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


def _refresh(source: WaveformSource) -> cabc.Callable[..., None]:
    def callback(*args: object) -> None:
        del args
        x_values, y_values, left, right = source.read()
        dpg.set_value('waveform', [x_values, y_values])
        dpg.set_axis_limits('x_axis', left, right)
        dpg.set_frame_callback(dpg.get_frame_count() + 1, callback)

    return callback


def _style_waveform() -> None:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvLineSeries):
            dpg.add_theme_color(
                dpg.mvPlotCol_Line,
                (90, 220, 255),
                category=dpg.mvThemeCat_Plots,
            )
            dpg.add_theme_style(
                dpg.mvPlotStyleVar_LineWeight,
                2.0,
                category=dpg.mvThemeCat_Plots,
            )
    dpg.bind_item_theme('waveform', theme)


if __name__ == '__main__':
    main()
