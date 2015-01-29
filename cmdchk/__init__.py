"""A configurable system monitor.

run_server: Configures and runs the MonitoringServer.
wrapper: Calls run_server in a loop, in case it crashes."""
from __future__ import print_function, absolute_import, unicode_literals

import signal, sys, time

from argparse import Action, ArgumentParser
from multiprocessing import Process

from .cmdchk_server import MonitoringServer
from .version import __version__

from setproctitle import setproctitle

__all__ = ['cmdchk_server', 'run_server', 'wrapper']

def run_server(settings=None, defaults=None):
    """The entry point for running a server.

    The Settings parameter matches the MonitoringServer settings parameter, but
    may also include a config_location key, which will be passed on to
    read_configuration. It is updated by the args, if applicable."""
    setproctitle('cmdchk_server')
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    if settings is None:
        settings = {}
    settings.update(_parse_args())
    config_location = settings.pop('config_location', None)

    server = MonitoringServer(settings, defaults)
    server.read_configuration(config_location)
    if not server.run():
        # If something is wrong during configuration, don't spin the loop
        # too hard.
        time.sleep(5)
        sys.exit(1)

def wrapper(settings=None, defaults=None):
    """A simple loop to make sure there's always a server running.

    Runs the server in a separate process and then sleeps. If the server ever
    dies, the wrapper wakes up and starts a new one. On SIGTERM, kills the
    currently running server and exits. Parameters are the same as
    run_server, and will be update by provided args, if applicable."""
    setproctitle('cmdchk_wrapper')

    if defaults is None:
        defaults = {'log_location': '/var/log/cmdchk/cmdchk.log'}

    if settings is None:
        settings = {}
    settings.update(_parse_args())
    if not 'config_location' in settings:
        settings['config_location'] = '/etc/cmdchk.cfg'

    server = None

    def trap_TERM(signum, frame):
        """A callback trap for SIGTERM. Kills the child server and exits."""
        server.terminate()
        sys.exit()

    signal.signal(signal.SIGTERM, trap_TERM)

    while True:
        server = Process(target=run_server, args=(settings, defaults))
        server.start()
        server.join()

def _parse_args():
    """some common argument parsing for run_server and wrapper."""
    parser = ArgumentParser()
    parser.add_argument('--user', '-u', help='The user to run the server as.')
    parser.add_argument('--port', '-p', type=int,
                        help='The port which the server should bind to.')
    parser.add_argument('--log', '-l', dest='log_location',
                        help='The file the server should log to.')
    parser.add_argument('--config', '-c', nargs='+', dest='config_location',
                        help='A list of config files to read from.')
    parser.add_argument('--check', '-k', action=_AppendChecks, nargs='+',
                        dest='check_list', metavar=('CHECK', 'RETURN'),
                        help='A check to run followed by possible return ' +
                        'values. Eg: -k /bin/somecommand 0 5 -k /bin/other')
    parser.add_argument('--version', '-V', action='version', version=__version__)

    args = vars(parser.parse_args())
    return dict((k, v) for k, v in args.items() if v is not None)

class _AppendChecks(Action):
    """An argparse Action to handle the check_list.

    Stores the return values as a list of ints in the dest dictionary, keyed by
    the check string."""
    def __call__(self, parser, namespace, values, option_string=None):
        check = values[0]
        rets = []
        for value in values[1:]:
            rets.append(int(value))
        if getattr(namespace, self.dest, None) is None:
            setattr(namespace, self.dest, {})
        check_list = getattr(namespace, self.dest)
        check_list[check] = rets
