# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import time
import logging
import gevent
import urllib3
import json

class DatawaveWebserverHealthPoller(object):
    """
    A utility to poll the Datawave web server's health endpoint on a regular
    basis, and convert the response (or lack of response) into a string to be
    returned by an HAProxy agent.
    """

    DOWN_RESPONSE = "__SERVER_DOWN__"
    UNAVAILABLE_RESPONSE = "__SERVER_UNAVAILABLE__"

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger('DatawaveWebserverHealthPoller')
        self.state = {'timestamp': time.time(), 'agent_response': ''}

        self.check_url = kwargs.get('check_url', 'http://localhost:8080/DataWave/Common/Health/health')
        self.down_response = kwargs.get('down_response', 'down')
        self.unavailable_response = kwargs.get('unavailable_response', '0% drain')
        self.staleness_response = kwargs.get('staleness_response', '')

        self.check_timeout = kwargs.get('check_timeout', 10.0)
        assert isinstance(self.check_timeout, float), \
            'check_timeout is not a floating point number: {}'.format(self.check_timeout)
        
        self.interval = kwargs.get('interval', 1.0)
        assert isinstance(self.interval, float), \
            'interval is not a float: {}'.format(self.interval)
        assert self.interval >= 0.0, \
            'interval {} is not >= 0'.format(self.interval)
        
        self.connection_usage_reduction = kwargs.get('connection_usage_reduction', 0.7)
        assert isinstance(self.connection_usage_reduction, float), \
            'connection_usage_reduction is not a floating point number: {}'.format(self.connection_usage_reduction)
        assert self.connection_usage_reduction >= 0 and self.connection_usage_reduction <= 1.0, \
            'connection_usage_reduction {} is not in the range [0.0,1.0]'.format(self.connection_usage_reduction)

        self.os_load_reduction = kwargs.get('os_load_reduction', 0.4)
        assert isinstance(self.os_load_reduction, float), \
            'os_load_reduction is not a floating point number: {}'.format(self.os_load_reduction)
        assert self.os_load_reduction >= 0 and self.os_load_reduction <= 1.0, \
            'os_load_reduction {} is not in the range [0.0,1.0]'.format(self.os_load_reduction)
        
        self.swap_usage_reduction = kwargs.get('swap_usage_reduction', 0.3)
        assert isinstance(self.swap_usage_reduction, float), \
            'swap_usage_reduction is not a floating point number: {}'.format(self.swap_usage_reduction)
        assert self.swap_usage_reduction >= 0 and self.swap_usage_reduction <= 1.0, \
            'swap_usage_reduction {} is not in the range [0.0,1.0]'.format(self.swap_usage_reduction)
        
        self.staleness_interval = kwargs.get('staleness_interval', 0)
        assert isinstance(self.staleness_interval, int), \
            'staleness_interval is not an integer: {}'.format(self.staleness_interval)
        
        self.stop_timeout = kwargs.get('stop_timeout', 10)
        assert isinstance(self.stop_timeout, int), \
            'stop_timeout is not an integer: {}'.format(self.stop_timeout)
                
        self.http = urllib3.PoolManager()

        self.enabled = True
    
    def start(self):
        """
        Starts running with the specified interval. If the interval of 0
        is supplied, then no background polling will take place and each
        request will result in an immediate call to the web server.
        """
        if not self.interval == 0.0:
            self.logger.debug("running with interval of {} seconds".format(self.interval))
            self.g = gevent.spawn(self.run_with_interval)
    
    def process_response(self, response):
        """
        Converts the datawave health endpoint response into an HAProxy agent response.
        """
        if response == self.DOWN_RESPONSE:
            self.logger.debug("Processing down response \"%s\"", self.down_response)
            self.state['agent_response'] = self.down_response
            self.state['timestamp'] = time.time()
        elif response == self.UNAVAILABLE_RESPONSE:
            self.logger.debug("Processing unavailable response \"%s\"", self.down_response)
            self.state['agent_response'] = self.unavailable_response
            self.state['timestamp'] = time.time()
        elif response:
            # Start with full weight and whatever status was reported by the health endpoint
            weight = 1.0
            status = response['Status']

            # Subtract for connection used percentage
            connection_used_percentage = min(1.0,response['ConnectionUsagePercent'] / 100.0)
            connection_reduction = connection_used_percentage * self.connection_usage_reduction
            weight = weight - connection_reduction

            # Subtract for OS load
            load_reduction = response['SystemLoad'] * self.os_load_reduction
            weight = weight - load_reduction

            # Subtract for swap usage
            swap_reduction = 0
            if response['SwapBytesUsed'] > 0:
                swap_reduction = self.swap_usage_reduction
                weight = weight - swap_reduction
            
            self.logger.debug("Computed weight %s, cnxn%% reduction %s, load reduction %s, swap reduction %s, orig response %s", \
                weight, connection_reduction, load_reduction, swap_reduction, response)

            # Set the weight to 0% when the status is drain, since it is the same effect, but will
            # also cause the server line to be rendered with a blue background in the stats UI.
            # Otherwise, limit the weight at 1% so that we don't mark the server as in drain mode
            # if the status does not indicate it should be in drain mode.
            if status == "drain":
                weight = 0.0
            else:
                weight = max(0.01, weight)

            # Recover from a down/maint status by taking up on to the end of the final status
            if status == "ready" or status == "drain":
                status = status + " up"

            self.state['agent_response'] = "{weight}% {status}".format(status=status, weight=int(weight*100))
            self.state['timestamp'] = time.time()

    def run_with_interval(self):
        """
        Helper to run the `run` function in a gevent loop.
        """

        while self.enabled:
            try:
                self.run()
            except Exception as e:
                self.logger.critical('Run failed with %s' % e)
            
            gevent.sleep(self.interval)
    
    def run(self):
        """
        Do the actual work to retrieve a health status from Datawave.
        """
        result = None
        try:
            resp = self.http.request('GET', self.check_url, timeout=self.check_timeout)
            if resp.status == 200:
                result = json.loads(resp.data.decode('utf-8'))
            elif resp.status == 503:
                result = self.UNAVAILABLE_RESPONSE
            else:
                self.logger.warning("Unexpected response %s from health endpoint.", resp.status)
        except urllib3.exceptions.MaxRetryError as e:
            if isinstance(e.reason, urllib3.exceptions.NewConnectionError):
                self.logger.info('Unable to retrieve datawave health status: %s', e.reason)
                result = self.DOWN_RESPONSE
            else:
                self.logger.warning('Unable to retrieve datawave health status: %s', e)
        except urllib3.exceptions.HTTPError as e:
            self.logger.warning('Unable to retrieve datawave health status: %s', e)
        
        self.process_response(result)
    
    def is_stale(self):
        """
        Determine if the current state is stale.
        """
        if self.staleness_interval:
            now = time.time()
            state_age = now - self.state['timestamp']
            stale = state_age > self.staleness_interval
            if stale:
                self.logger.warn('state is stale as its age {} is greater than {}'.format(state_age,self.staleness_interval))
            return stale
        else:
            return False
    
    def respond(self):
        """
        Respond with the final value to sent to HAProxy.

        If we're running without a background interval, then we must also
        query the Datawave web service.
        """
        if self.interval == 0.0:
            self.run()
        
        if self.is_stale():
            if self.staleness_response:
                self.logger.warn('returning staleness response %s', self.staleness_response)
                return self.staleness_response
            else:
                self.logger.warn('no staleness response, returning empty string')
                return ''
        else:
            return self.state['agent_response']
    
    def stop(self):
        """
        Shutdown the background poller event.
        """
        if self.interval == 0:
            return
        else:
            self.enabled = False
            try:
                self.logger.info("attempting shut down")
                t = gevent.Timeout(self.stop_timeout)
                t.start()
                self.g.join()
                self.logger.info("stopped")
            except gevent.Timeout:
                self.logger.warn('unable to stop within %s. Terminating.', self.stop_timeout)
                self.g.kill()
            finally:
                t.cancel()