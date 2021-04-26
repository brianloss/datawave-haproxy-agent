# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import argparse
import logging
import signal
import sys
from functools import partial

import gevent
import yaml
from gevent.server import StreamServer

from .dwserverhealth import DatawaveWebserverHealthPoller

AGENT_STOPPING = False

def stop_services(server, status):
    """
    Stop plugin and server gracefully.
    """
    global AGENT_STOPPING
    if not AGENT_STOPPING:
        AGENT_STOPPING = True
        logging.info('stopping datawave webserver status poller')
        status.stop()
        logging.info('stopping datawave haproxy agent')
        server.stop()
    else:
        logging.info('stop is already in progress')

def setup_handlers(server, status):
    """
    Setup signal handlers to stop server gracefully.
    """
    gevent.signal_handler(signal.SIGINT, stop_services, server, status)
    gevent.signal_handler(signal.SIGTERM, stop_services, server, status)

def setup_logging(args):
    """
    Initialize logger with the requested Loglevel, and the specified logformat.
    """
    loglevel = getattr(logging, args.loglevel.upper())
    logformat = '%(asctime)s %(levelname)s [%(name)s] %(message)s'

    logging.basicConfig(format=logformat, level=loglevel)

def load_config(skip_config, config_file):
    """
    Loads the YAML configuration for the agent.
    """
    if skip_config:
        return dict()

    try:
        with open(config_file) as fd:
            config = yaml.load(fd, Loader=yaml.FullLoader)
    except FileNotFoundError as e:
        logging.critical('Configuration file %s not found.', config_file)
        sys.exit(1)
    except OSError as e:
        logging.critical('Configuration file %s could not be loaded: %s', config_file, e)
        sys.exit(2)
    
    logging.debug('loaded configuration %s', config)
    return config

def handle_requests(socket, addr, status):
    """
    Handles haproxy agent check connections
    The state to write is obtained from the passed in plugin
    using the `respond` function. The state is suffixed with
    a new line and sent to Haproxy.
    """
    logging.debug("received connect from {}".format(addr))
    logging.debug("status = {}".format(status))
    logging.debug("socket = {}".format(socket))
    state = status.respond()
    logging.debug("writing state: {}".format(state))
    socket.send((str(state)+"\n").encode())
    socket.close()

def start_server(args, config, status):
    """
    Starts the main listener for haproxy agent requests with the handler function.
    """
    listen = (config.get('bind', args.bind), config.get('port', args.port))
    handler = partial(handle_requests, status=status)
    server = StreamServer(listen, handler)

    logging.info("listening {}".format(listen))
    server.start()
    return server

def main():
    parser = argparse.ArgumentParser(description="Datawave HAProxy Agent")
    parser.add_argument("-c", "--config",
                        default="/etc/datawave_haproxy_agent/config.yml",
                        type=str,
                        help="path to YAML configuration")
    parser.add_argument("-s", "--skip-config",
                        default=False,
                        action='store_true',
                        help="don't read config file--all options are default")
    parser.add_argument("-b", "--bind",
                        default='0.0.0.0',
                        type=str,
                        help="listen address")
    parser.add_argument("-p", "--port",
                        default=5555,
                        type=int,
                        help="listen port")
    parser.add_argument("-l", "--loglevel",
                        default='info',
                        choices=['info', 'warn', 'debug', 'critical'],
                        type=str,
                        help="log level")
    
    args = parser.parse_args()
    setup_logging(args)

    config = load_config(args.skip_config, args.config)

    if not 'dw_health_poller' in config:
        config['dw_health_poller'] = dict()

    status = DatawaveWebserverHealthPoller(**config.get('dw_health_poller'))
    status.start()

    server = start_server(args, config, status)
    setup_handlers(server, status)

    gevent.wait()

if __name__ == "__main__":
    main()
