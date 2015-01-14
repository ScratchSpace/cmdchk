"""A monitoring server that responds over HTTP.

MyHTTPRequestHandler: A custom request handler for the stdlib HTTPServer.
run_server: Configures and runs the HTTPServer.
wrapper: Makes sure there's always a server running."""
import logging, os, pwd, signal, sys, time

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
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

        Simply sets the '_logger' and '_processes' instance variables. Everything
        else is passed to the superclass. See BaseHTTPRequestHandler.__init__
        for details."""
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
            self.send_header('Connection','close')
            self.send_header('Content-Length', '37')
            self.end_headers()
        else:
            self.send_response(503, 'Service Unavailable')
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Connection','close')
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

    def __init__(self, log_location=None):
        """Creates the MonitoringServer.

        Sets up a number of internal variables, including the HTTPServer. Takes
        a filename as the log_location parameter to determine where logs should
        go."""
        self._httpd = HTTPServer(('', 9200), MyHTTPRequestHandler)
        self._startup_messages = ['Server started.']
        self._error_messages = []
        self._log_location = log_location
        self._logger = None

    def run(self):
        """Sets up the environment and runs the internal HTTPServer."""
        self._drop_privileges()
        self._setup_logging()
        for message in self._startup_messages:
            self._logger.debug(message)

        if self._error_messages:
            for message in self._error_messages:
                self._logger.critical(message)
            time.sleep(5)
            sys.exit(1)

        self._httpd.serve_forever()


    def _drop_privileges(self):
        """If running as root, will attempt to drop privileges to nobody."""
        if os.getuid() == 0:
            try:
                newuser = pwd.getpwnam('nobody')
            except KeyError:
                self._error_messages.append('Could not drop privileges to nobody.')
            else:
                newuid, newgid = newuser[2:4]
                os.setgroups([])
                os.setgid(newgid)
                os.setuid(newuid)
                self._startup_messages.append('Privileges dropped from root to nobody.')
        else:
            self._startup_messages.append('Not root, privileges unchanged.')

    def _setup_logging(self):
        """Creates the logger used by the rest of the program.

        Logs to the console by default. If a log_location was specified, will
        attempt to log there. If the fails, will log the error to syslog's
        daemon facility."""
        self._logger = logging.getLogger('appsrvchk')
        self._logger.setLevel(logging.DEBUG)
        if self._log_location is None:
            handler = logging.StreamHandler()
        else:
            try:
                handler = TimedRotatingFileHandler(
                    self._log_location, when='midnight', backupCount=6)
            except IOError:
                handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON)
                self._error_messages.append('Could not open logfile ' + self._log_location)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

def run_server(log_location=None):
    """The entry point for running a server. Does some process bookkeeping."""
    setproctitle('appsrvchk_server')
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    server = MonitoringServer(log_location)
    server.run()

def wrapper():
    """A simple loop to make sure there's always a serer running.

    Runs the server in a separate process and then sleeps. If the server ever
    dies, the wrapper wakes up and starts a new one. On SIGTERM, kills the
    currently running server and exits."""
    setproctitle('appsrvchk_wrapper')
    server = None

    def trap_TERM(signal, frame):
        """A callback trap for SIGTERM. Kills the child server and exits."""
        server.terminate()
        sys.exit()

    signal.signal(signal.SIGTERM, trap_TERM)

    while True:
        server = Process(target=run_server,
                         args=('/var/log/appsrvchk/appsrvchk.log',))
        server.start()
        server.join()
