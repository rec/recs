from .models import ServiceSpec

RECS_SERVICE = ServiceSpec(
    name='recs',
    display_name='recs',
    description='recs background recorder',
    launchd_label='com.swirly.recs',
    daemon_env_var='RECS_DAEMON',
    windows_pipe=r'\\.\pipe\recs',
)
