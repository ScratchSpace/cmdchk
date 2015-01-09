import os, pwd, signal, sys

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Process
from subprocess import check_call, CalledProcessError

from setproctitle import setproctitle

class myHTTPRequestHandler(BaseHTTPRequestHandler):

    def get_process_status(self):
        try:
            DEVNULL = open(os.devnull, 'wb')
            check_call(['/etc/init.d/nginx', 'status'], stdout=DEVNULL, stderr=DEVNULL)
            check_call(['/etc/init.d/php-fpm', 'status'], stdout=DEVNULL, stderr=DEVNULL)
        except CalledProcessError as ex:
            processes = False
            self.log_message('%s failed', (ex.cmd))
        else:
            processes = True
        finally:
            DEVNULL.close()
        return processes

    def send_my_headers(self, status):
        if status:
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

    def send_my_response(self, status):
        if status:
            self.wfile.write("Both nginx and php-fpm are running.\r\n\r\n")
        else:
            self.wfile.write("One of nginx or php-fpm are not running.\r\n\r\n")

    def do_HEAD(self):
        status = self.get_process_status()
        self.send_my_headers(status)

    def do_OPTIONS(self):
        status = self.get_process_status()
        self.send_my_headers(status)
        self.send_my_response(status)

    def do_GET(self):
        status = self.get_process_status()
        self.send_my_headers(status)
        self.send_my_response(status)

def run_server():
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)
    setproctitle('appsrvchk_server')
    httpd = HTTPServer(('', 9200), myHTTPRequestHandler)
    if os.getuid() == 0:
        newid = pwd.getpwnam('nobody')
        newuid, newgid = newid[2:4]
        os.setgroups([])
        os.setgid(newgid)
        os.setuid(newuid)
    httpd.serve_forever()

def wrapper():
    setproctitle('appsrvchk_wrapper')
    server = None

    def trap_TERM(signal, frame):
        server.terminate()
        server.join()
        sys.exit()

    def trap_USR1(signal, frame):
        server.terminate()
        server.join()

    signal.signal(signal.SIGTERM, trap_TERM)
    signal.signal(signal.SIGUSR1, trap_USR1)

    while True:
        server = Process(target=run_server)
        server.start()
        server.join()
