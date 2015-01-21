Appsrvchk
=========

Summary
-------

This is a program that monitors that status of important cluster services. It
runs a small web server that you can query to find if things are good. There is
also a wrapper which ensures that the server is running, as well as handling
some signals.

Server
------

The server listens on a specified port and responds to GET, HEAD and OPTIONS
requests. It runs some user specified checks and if everything is good, it
returns 200, otherwise 503. It logs all requests, as well as what caused an
error, to a specified file. If it is unable to open it's logfile, it will fall
back to syslog's daemon facility. If started as root, it will attempt to drop
privileges to a specified user. Any errors during startup will cause it to sleep
for 5 seconds and exit instead of serving.

It has the capability to parse config files to set the user it runs as, the
port it listens on and the logfile it writes to.

Wrapper
-------

The wrapper starts the server and then sleeps. If the server dies for whatever
reason, the wrapper will wake up and start a new one. It's a simple script, and
as such, deamonizing it is up to you. If sent a SIGTERM, it will kill the sever
it started and then exit.

Configuration
-------------

You can set the server's user, port, log file and configuration files. These can
be set (highest to lowest priority) using arguments (try '--help'), passed to
the constructor programatically, or specified in the configuration file (you
cannot specify the configuration files in the configuration file).

The configuration files are JSON formatted object, and may contain the keys
"user" (a string), "port" (an int), "log_location" (a string), "check_list" (a
list of strings) and "return_list" (a list of ints). You may specify multiple
files to pull configuration from, which will be parsed in order. Setting from
files parsed later will override earlier settings.

When run as just the server, the default settings are to listen on port 9200,
drop privileges to nobody and log to the console. It will read no other
configuration files unless told to.

When run as the wrapper, it will log to /var/log/appsrvchk/appsrvchk.log and
read /etc/appsrvchk.cfg, otherwise acting as above.

License
-------

University Of Illinois/NCSA Open Source License. See the LICENSE file for more
information.

Compatability
-------------

Requires python 2.6 or 2.7, and the setproctitle package from pypi.
