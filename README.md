# Appsrvchk

## Summary

This is a program that monitors that status of important cluster services. It
runs a small web server that you can query to find if things are good. There is
also a wrapper which ensures that the server is running, as well as handling
some signals.

## Server

The server listens on port 9200 and responds to GET, HEAD and OPTIONS requests.
If everything is good, it returns 200, otherwise 503. It logs all requests, as
well as what caused an error, to stderr.

## Wrapper

The wrapper starts the server and then sleeps. If the server dies for whatever
reason, the wrapper will wake up and start a new one. It redirects the output
from the server onto /var/log/appsrvchk.log. This location is not currently
configurable. It's a simple script, and as such, deamonizing it is up to you.
If sent a SIGTERM, it will kill the sever it started and then exit. If sent a
SIGUSR1, it will kill the server it started and then start a new one. This can
be useful for log rotation.

## License

University Of Illinois/NCSA Open Source License. See the LICENSE file for more
information.
