"""A monitoring server that responds over HTTP.

MonitoringServer: Configures and runs the HTTPServer.
run_server: Runs the MonitoringServer.
wrapper: Makes sure there's always a server running."""
from __future__ import print_function, unicode_literals

import json, logging, os, pwd, signal, sys, time

from argparse import Action, ArgumentParser
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from logging.handlers import SysLogHandler, TimedRotatingFileHandler
from multiprocessing import Process
from subprocess import CalledProcessError, Popen, PIPE, STDOUT

from setproctitle import setproctitle

class _MyHTTPRequestHandler(BaseHTTPRequestHandler):
    """A request handler that checks the status of some processes.

    This class subclasses BaseHTTPRequestHandler and provides do_HEAD, do_GET
    and do_OPTIONS methods. It overrides log_message method and extends
    __init__."""

    def __init__(self, *args, **kwargs):
        """Create the _MyHTTPRequestHandler.

        Simply sets the '_processes' instance variable. Everything else is
        passed to the superclass. See BaseHTTPRequestHandler.__init__ for
        details."""
        self._processes = False
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def _get_process_status(self):
        """The test to determine if the monitored processes are running.

        Checks the status of programs and updates the '_processes' instance
        variable for later use. Is called by _send_my_headers as the first step
        in creating a response."""
        try:
            for check, rets in self.server.check_list.items():
                proc = Popen(check, shell=True, stdout=PIPE, stderr=STDOUT)
                output, _ = proc.communicate()
                ret = proc.returncode
                if ret not in (rets or [0]):
                    raise CalledProcessError(ret, check, output)
        except CalledProcessError as ex:
            self._processes = False
            self.log_message("\n%s failed: %s\n%s",
                             ex.cmd, ex.returncode, ex.output,
                             lvl=logging.WARNING)
        else:
            self._processes = True

    def _send_my_headers(self):
        """Handles the first part of sending a reponse.

        Calls _get_process_status first. If processing a HEAD request, this is
        the only method that needs to be called. Is called by _send_my_response
        as part of a full request."""
        self._get_process_status()
        if self._processes:
            self.send_response(200, 'OK')
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', '23')
            self.end_headers()
        else:
            self.send_response(503, 'Service Unavailable')
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', '31')
            self.end_headers()

    def _send_my_response(self):
        """Handles sending the body of a response.

        Calls _send_my_headers before sending the body. Called for a GET or
        OPTIONS request."""
        self._send_my_headers()
        if self._processes:
            self.wfile.write("All checks succeeded.\r\n\r\n")
        else:
            self.wfile.write("Check failed, please see log.\r\n\r\n")

    def do_HEAD(self):
        """Required by the superclass. Handles HEAD requests."""
        self._send_my_headers()

    def do_OPTIONS(self):
        """Required by the superclass. Handles OPTIONS requests."""
        self._send_my_response()

    def do_GET(self):
        """Required by the superclass. Handles GET requests."""
        self._send_my_response()

    def log_message(self, format_string, *args, **kwargs):
        """Overridden to send messages to the logger, instead of stderr."""
        # Python 3 has keyword only arguments, which lvl should use.
        lvl = kwargs.pop('lvl', logging.INFO)
        self.server.logger.log(lvl, "%s - - [%s] %s",
                               self.address_string(),
                               self.log_date_time_string(),
                               format_string%args)

class MonitoringServer(object):
    """Holds a stdlib HTTPServer and the configuration for it.

    Provides a read_configuration and a run method. When run is called, will
    start the internal HTTPServer, so any calls to read_configuration should go
    first."""

    def __init__(self, settings=None, defaults=None):
        """Creates the MonitoringServer.

        Sets up a number of internal variables. Takes two similarly structured
        dictionaries, one for settings and one for defaults. Values from the
        settings hash are used. If a value in the settings hash is not
        specified, it may come from a configuration file, and finally will be
        supplied by the defaults hash. Values in the defaults hash override the
        "default" defaults."""
        self._startup_messages = ['Server started.']
        self._error_messages = []
        self._logger = None
        self._settings = {'user': None,
                          'port': None,
                          'log_location': None,
                          'check_list': None}
        if settings:
            self._settings.update(settings)
        self._defaults = {'user': 'nobody',
                          'port': 9200,
                          'log_location': '',
                          'check_list': {'/bin/true': []}}
        if defaults:
            self._defaults.update(defaults)

    def run(self):
        """Sets up the environment and runs the internal HTTPServer.

        This function does NOT call read_configuration. That's up to the user
        of the class."""
        self._set_defaults()
        self._drop_privileges()
        self._setup_logging()
        for message in self._startup_messages:
            self._logger.debug(message)

        if self._error_messages:
            for message in self._error_messages:
                self._logger.critical(**message)
            return False

        httpd = HTTPServer(('', self._settings['port']), _MyHTTPRequestHandler)
        httpd.check_list = self._settings['check_list']
        httpd.logger = self._logger
        httpd.serve_forever()

    def _set_defaults(self):
        """Set default values for variables that are still None."""
        for name, value in self._defaults.items():
            try:
                if self._settings[name] is None:
                    self._settings[name] = value
            except KeyError:
                self._error_messages.append({'msg': 'Bad default Value',
                                             'exc_info': sys.exc_info()})

    def _drop_privileges(self):
        """If root, will attempt to drop privileges to the specified user."""
        if os.getuid() == 0:
            try:
                newuser = pwd.getpwnam(self._settings['user'])
            except KeyError:
                self._error_messages.append({
                    'msg': 'Could not drop privileges to {0}.'.format(
                        self._settings['user']),
                    'exc_info': sys.exc_info()})
                self._logger.exception('Error getting user')
            else:
                newuid, newgid = newuser[2:4]
                os.setgroups([])
                os.setgid(newgid)
                os.setuid(newuid)
                self._startup_messages.append(
                    'Privileges dropped from root to {0}.'.format(
                        self._settings['user']))
        else:
            self._startup_messages.append('Not root, privileges unchanged.')

    def _setup_logging(self):
        """Creates the logger used by the rest of the program.

        Logs to the console by default. If a log_location was specified, will
        attempt to log there. If the fails, will log the error to syslog's
        daemon facility."""
        self._logger = logging.getLogger('appsrvchk')
        self._logger.setLevel(logging.DEBUG)
        if self._settings['log_location'] == '':
            handler = logging.StreamHandler()
        else:
            try:
                handler = TimedRotatingFileHandler(
                    self._settings['log_location'], when='midnight',
                    backupCount=6)
            except IOError:
                handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON)
                self._error_messages.append({
                    'msg': 'Could not open logfile {1}'.format(
                        self._settings['log_location']),
                    'exc_info': sys.exc_info()})
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    def read_configuration(self, config_location=None):
        """Reads in the specified configurations.

        Attempts to read in the given JSON formatted configuration files. Takes
        a single filename or a list of filenames. Bails out on errors in any of
        them. Sets values on the instance. Does not try to set values that
        already exist via other methods of configuration."""
        if config_location is None:
            config_location = []
        config = {}
        read_files = []
        if isinstance(config_location, basestring):
            config_location = [config_location]
        try:
            for location in config_location:
                try:
                    with open(location) as config_file:
                        config.update(json.load(config_file))
                except IOError:
                    self._startup_messages.append(
                        'Could not open file: ' + location)
                else:
                    read_files.append(location)
            for key, value in config.items():
                if self._settings[key] is None:
                    self._settings[key] = value
        except (KeyError, ValueError):
            self._error_messages.append({'msg': 'Error parsing config',
                                         'exc_info': sys.exc_info()})
        else:
            if read_files:
                self._startup_messages.append(
                    'Read config files: {0}'.format(read_files))
            else:
                self._startup_messages.append(
                    'No config files read. Using defaults.')

def run_server(settings=None, defaults=None):
    """The entry point for running a server.

    The Settings parameter matches the MonitoringServer settings parameter, but
    may also include a config_location key, which will be passed on to
    read_configuration. It is updated by the args, if applicable."""
    setproctitle('appsrvchk_server')
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    if settings is None:
        settings = {}
    settings.update(parse_args())
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
    setproctitle('appsrvchk_wrapper')

    if defaults is None:
        defaults = {'log_location': '/var/log/appsrvchk/appsrvchk.log'}

    if settings is None:
        settings = {}
    settings.update(parse_args())
    if not 'config_location' in settings:
        settings['config_location'] = '/etc/appsrvchk.cfg'

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

def parse_args():
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
