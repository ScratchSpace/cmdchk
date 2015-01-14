# Appsrvchk

## Summary

This is a program that monitors that status of important cluster services. It
runs a small web server that you can query to find if things are good. There is
also a wrapper which ensures that the server is running, as well as handling
some signals.

## Server

The server listens on port 9200 and responds to GET, HEAD and OPTIONS requests.
If everything is good, it returns 200, otherwise 503. It logs all requests, as
well as what caused an error, to stderr, by default, or a file can be specified.
If it is unable to open it's logfile, it will use syslog's daemon facility to
log this error, then sleep for 5 seconds and exit. If started as root, it will
attempt to drop privileges to nobody. If this fails, it will log the failure,
sleep for 5 seconds and exit.

## Wrapper

The wrapper starts the server and then sleeps. If the server dies for whatever
reason, the wrapper will wake up and start a new one. It's a simple script, and
as such, deamonizing it is up to you. If sent a SIGTERM, it will kill the sever
it started and then exit.

## License

University Of Illinois/NCSA Open Source License. See the LICENSE file for more
information.

## Compatability

Requires python 2.6 or 2.7, and the setproctitle package from pypi.
