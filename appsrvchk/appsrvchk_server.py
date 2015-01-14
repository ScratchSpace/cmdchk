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
    and do_OPTIONS methods. It overrides the log_message method to do logging
    with the logging module and extends __init__ to store a logger instance
    variable."""

    def __init__(self, *args, **kwargs):
        """Create the MyHTTPRequestHandler.

        Simply sets the 'logger' and 'processes' instance variables. Everything
        else is passed to the superclass. See BaseHTTPRequestHandler.__init__
        for details."""
        self.logger = logging.getLogger('appsrvchk')
        self.processes = False
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def _get_process_status(self):
        """The test to determine if the monitored processes are running.

        Checks the status of programs and updates the 'processes' instance
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
            self.processes = False
            self.log_message('%s failed', (ex.cmd), lvl=logging.WARNING)
        else:
            self.processes = True
        finally:
            DEVNULL.close()

    def _send_my_headers(self):
        """Handles the first part of sending a reponse.

        Calls _get_process_status first. If processing a HEAD request, this is
        the only method that needs to be called."""
        self._get_process_status()
        if self.processes:
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
        if self.processes:
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
        self.logger.log(lvl, "%s - - [%s] %s",
                        self.address_string(),
                        self.log_date_time_string(),
                        format_string%args)

def run_server(log_location=None):
    """Set up the server details and set it running.

    Makes the server binds as root, then drops privileges, sets up the logger
    and tells the server to begin serving requests. The log_location argument
    takes a filename to log to. If it's unset, messages will be logged to
    stderr."""
    setproctitle('appsrvchk_server')
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    error = False
    lvl = logging.DEBUG

    httpd = HTTPServer(('', 9200), MyHTTPRequestHandler)

    startup_messages = ['Server started.']

    if os.getuid() == 0:
        try:
            newuser = pwd.getpwnam('nobody')
        except KeyError:
            startup_messages.append('Could not drop privileges to nobody.')
            error = True
            lvl = logging.CRITICAL
        else:
            newuid, newgid = newuser[2:4]
            os.setgroups([])
            os.setgid(newgid)
            os.setuid(newuid)
            startup_messages.append('Privileges dropped from root to nobody.')

    my_logger = logging.getLogger('appsrvchk')
    my_logger.setLevel(logging.DEBUG)
    if log_location is None:
        handler = logging.StreamHandler()
    else:
        try:
            handler = TimedRotatingFileHandler(
                log_location, when='midnight', backupCount=6)
        except IOError:
            handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON)
            startup_messages.append('Could not open logfile ' + log_location)
            error = True
            lvl = logging.CRITICAL
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    my_logger.addHandler(handler)

    for message in startup_messages:
        my_logger.log(lvl, message)

    if error:
        time.sleep(5)
        sys.exit(1)

    httpd.serve_forever()

def wrapper():
    """A simple loop to make sure there's always a serer running.

    Runs the server in a separate process and then sleeps. If the server ever
    dies, the wrapper wakes up and starts a new one. On SIGTERM, kills the
    currently running server and exits."""
    setproctitle('appsrvchk_wrapper')
    server = None

    def trap_TERM(signal, frame):
        server.terminate()
        sys.exit()

    signal.signal(signal.SIGTERM, trap_TERM)

    while True:
        server = Process(target=run_server,
                         args=('/var/log/appsrvchk/appsrvchk.log',))
        server.start()
        server.join()
