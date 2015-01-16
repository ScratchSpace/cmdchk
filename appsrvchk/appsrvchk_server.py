"""A monitoring server that responds over HTTP.

MyHTTPRequestHandler: A custom request handler for the stdlib HTTPServer.
MonitoringServer: Configures and runs the HTTPServer.
run_server: Runs the MonitoringServer.
wrapper: Makes sure there's always a server running."""
import logging, os, pwd, signal, sys, time

from argparse import ArgumentParser
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from ConfigParser import (NoOptionError, NoSectionError, ParsingError,
                          RawConfigParser)
from logging.handlers import SysLogHandler, TimedRotatingFileHandler
from multiprocessing import Process
from subprocess import check_call, CalledProcessError

from setproctitle import setproctitle

class MyHTTPRequestHandler(BaseHTTPRequestHandler):
    """A request handler that checks the status of some processes.

    This class subclasses BaseHTTPRequestHandler and provides do_HEAD, do_GET
    and do_OPTIONS methods. It overrides log_message method and extends
    __init__."""

    def __init__(self, *args, **kwargs):
        """Create the MyHTTPRequestHandler.

        Simply sets the '_logger' and '_processes' instance variables.
        Everything else is passed to the superclass. See
        BaseHTTPRequestHandler.__init__ for details."""
        self._logger = logging.getLogger('appsrvchk')
        self._processes = False
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def _get_process_status(self):
        """The test to determine if the monitored processes are running.

        Checks the status of programs and updates the '_processes' instance
        variable for later use. Is called by _send_my_headers as the first step
        in creating a response.

        NOTE: Can't go in our __init__. Before the superclass __init__,
        self.log_message doesn't work, and after the superclass __init__ the
        request has already been dispatched."""
        try:
            # Python 3 has a constant in subprocess for this, but for now we
            # make our own.
            DEVNULL = open(os.devnull, 'wb')
            # Python 2.7 has check_output, which might be nice here. The output
            # would be stored on the exception below.
            check_call(['/etc/init.d/nginx', 'status'],
                       stdout=DEVNULL, stderr=DEVNULL)
            check_call(['/etc/init.d/php-fpm', 'status'],
                       stdout=DEVNULL, stderr=DEVNULL)
        except CalledProcessError as ex:
            self._processes = False
            self.log_message('%s failed', (ex.cmd), lvl=logging.WARNING)
        else:
            self._processes = True
        finally:
            DEVNULL.close()

    def _send_my_headers(self):
        """Handles the first part of sending a reponse.

        Calls _get_process_status first. If processing a HEAD request, this is
        the only method that needs to be called."""
        self._get_process_status()
        if self._processes:
            self.send_response(200, 'OK')
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', '37')
            self.end_headers()
        else:
            self.send_response(503, 'Service Unavailable')
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Connection', 'close')
            self.send_header('Content-Length', '42')
            self.end_headers()

    def _send_my_response(self):
        """Handles sending the body of a response.

        Calls _send_my_headers before sending the body. Call this for a GET
        request."""
        self._send_my_headers()
        if self._processes:
            self.wfile.write("Both nginx and php-fpm are running.\r\n\r\n")
        else:
            self.wfile.write("One of nginx or php-fpm are not running.\r\n\r\n")

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
        self._logger.log(lvl, "%s - - [%s] %s",
                         self.address_string(),
                         self.log_date_time_string(),
                         format_string%args)

class MonitoringServer(object):
    """Holds a stdlib HTTPServer and the configuration for it.

    Only provides a run method, which can be called after the class is
    instantiated and will run the internal HTTPServer."""

    def __init__(self, user=None, port=None, log_location=None, defaults=None):
        """Creates the MonitoringServer.

        Sets up a number of internal variables, including the HTTPServer. Takes
        a filename as the log_location parameter to determine where logs should
        go."""
        self._startup_messages = ['Server started.']
        self._error_messages = []
        self._logger = None
        self._log_location = log_location
        self._port = port
        self._user = user
        base_defaults = {'user': 'nobody',
                         'port': 9200,
                         'log_location': ''}
        if defaults is not None:
            base_defaults.update(defaults)
        self._defaults = base_defaults

    def run(self):
        """Sets up the environment and runs the internal HTTPServer."""
        self._set_defaults()
        self._drop_privileges()
        self._setup_logging()
        for message in self._startup_messages:
            self._logger.debug(message)

        if self._error_messages:
            for message in self._error_messages:
                self._logger.critical(**message)
            return False

        httpd = HTTPServer(('', self._port), MyHTTPRequestHandler)
        httpd.serve_forever()

    def _set_defaults(self):
        """Set default values for variables that are still None."""
        for name, value in self._defaults.items():
            if getattr(self, '_'+name) is None:
                setattr(self, '_'+name, value)

    def _drop_privileges(self):
        """If running as root, will attempt to drop privileges to nobody."""
        if os.getuid() == 0:
            try:
                newuser = pwd.getpwnam(self._user)
            except KeyError:
                self._error_messages.append({
                    'msg':
                        'Could not drop privileges to {0}.'.format(self._user),
                    'exc_info': sys.exc_info()})
                self._logger.exception('Error getting user')
            else:
                newuid, newgid = newuser[2:4]
                os.setgroups([])
                os.setgid(newgid)
                os.setuid(newuid)
                self._startup_messages.append(
                    'Privileges dropped from root to {0}.'.format(self._user))
        else:
            self._startup_messages.append('Not root, privileges unchanged.')

    def _setup_logging(self):
        """Creates the logger used by the rest of the program.

        Logs to the console by default. If a log_location was specified, will
        attempt to log there. If the fails, will log the error to syslog's
        daemon facility."""
        self._logger = logging.getLogger('appsrvchk')
        self._logger.setLevel(logging.DEBUG)
        if self._log_location == '':
            handler = logging.StreamHandler()
        else:
            try:
                handler = TimedRotatingFileHandler(
                    self._log_location, when='midnight', backupCount=6)
            except IOError:
                handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON)
                self._error_messages.append({
                    'msg': 'Could not open logfile ' + self._log_location,
                    'exc_info': sys.exc_info()})
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    def read_configuration(self, config_location=None):
        """Reads in the previously specified configurations.

        Attempts to read in the configuration files specified during object
        construction. Bails out on errors in any of them. Sets values on the
        instance. Does not try to set values that already exist via other
        methods of configuration."""
        if config_location is None:
            config_location = []
        config = RawConfigParser()
        try:
            files = config.read(config_location)
            if files:
                self._startup_messages.append(
                    'Read config files: {0}'.format(files))
            else:
                config.add_section('appsrvchk')
                self._startup_messages.append(
                    'No config files read. Using defaults.')

            parameters = {'user': None,
                          'port': int,
                          'log_location': None}

            for name, transform in parameters.items():
                if getattr(self, '_'+name) is None:
                    # If the option isn't there, we just move on, it will be
                    # defaulted later. For other errors, we except out of the
                    # loop.
                    try:
                        value = config.get('appsrvchk', name)
                    except NoOptionError:
                        continue
                    if transform:
                        value = transform(value)
                    setattr(self, '_'+name, value)

        except (NoSectionError, ParsingError, ValueError):
            self._error_messages.append({'msg': 'Error parsing config',
                                         'exc_info': sys.exc_info()})

def run_server(user=None, port=None, log_location=None, config_location=None,
               defaults=None):
    """The entry point for running a server. Does some process bookkeeping."""
    setproctitle('appsrvchk_server')
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    parameters = dict(vars())
    parameters.update(parse_args())

    server = MonitoringServer(user=parameters['user'],
                              port=parameters['port'],
                              log_location=parameters['log_location'],
                              defaults=parameters['defaults'])
    server.read_configuration(config_location=parameters['config_location'])
    if not server.run():
        # If something is wrong during configuration, don't spin the loop
        # too hard.
        time.sleep(5)
        sys.exit(1)

def wrapper():
    """A simple loop to make sure there's always a server running.

    Runs the server in a separate process and then sleeps. If the server ever
    dies, the wrapper wakes up and starts a new one. On SIGTERM, kills the
    currently running server and exits. Parses exactly one command line
    argument, which is passed on as the log_location."""
    setproctitle('appsrvchk_wrapper')
    server = None

    def trap_TERM(signum, frame):
        """A callback trap for SIGTERM. Kills the child server and exits."""
        server.terminate()
        sys.exit()

    signal.signal(signal.SIGTERM, trap_TERM)

    args = {'config_location': '/etc/appsrvchk.cfg',
            'defaults': {'log_location': '/var/log/appsrvchk/appsrvchk.log'}}
    args.update(parse_args())

    while True:
        server = Process(target=run_server, kwargs=args)
        server.start()
        server.join()

def parse_args():
    """some common argument parsing."""
    parser = ArgumentParser()
    parser.add_argument('--user', '-u', help='The user to run the server as.')
    parser.add_argument('--port', '-p', type=int,
                        help='The port which the server should bind to.')
    parser.add_argument('--log', '-l', dest='log_location',
                        help='The file the server should log to.')
    parser.add_argument('--config', '-c', nargs='*', dest='config_location',
                        help='A list of config files to read from.')

    return dict((k, v) for k, v in vars(parser.parse_args()).items()
                if v is not None)
