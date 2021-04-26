# Datawave HAProxy Agent

Datawave HAProxy Agent is an agent for HAProxy intended to work with the
Datawave web service.

This agent polls the [health endpoint](https://github.com/NationalSecurityAgency/datawave/blob/master/web-services/common/src/main/java/datawave/webservice/common/health/HealthBean.java#L93)
of the Datawave web service either on a regular interval or on-demand when the
haproxy agent is interrogated, and converts the response into an HAProxy
[agent response](http://cbonte.github.io/haproxy-dconv/2.2/configuration.html#agent-check).

This agent calculates both a status and a weight. The status defaults to the
status returned by the Datawave webserver health endpoint. If the webserver
cannot be contacted, then the status reports as down. If the health endpoint
returns a 503 (Service Unavailable), then a "drain" status is returned. When
used with cookie-based server affinity for queries (via the query-session-id
cookie that is set with Datawave query calls), this allows for two scenarios:

1. Don't send new queries to servers that are overloaded. The Datawave health
   endpoint returns a 503 when the number of active queries (plus query calls
   where the call is hung waiting for an Accumulo connection) exceeds a
   configurable threshold (typically 2x the number of query slots meaning all
   queries active and the same number waiting for connections). At this point,
   it might be more beneficial to not send queries to the server, especially if
   other servers have availablity. If all servers are overloaded, then the
   system as a whole is overloaded and queries would be denied since haproxy
   would return a 503 at this point. This could be an indication to auto-scale
   new web servers, or at least a client can know that the system is overloaded
   and decide when to try again (vs having a potentially very long wait if all
   connections continued to queue up).
2. Allow graceful shutdown of a web server, giving active queries on it a
   chance to complete. The Datawave health endpoint returns a 503 after the
   shutdown endpoint has been called. By having the agent switch the server to
   drain mode, new queries won't be sent to the server, but calls for existing
   queries will be sent due to the cookie-based affinity. This approach is
   necessary since Datawave query calls come over multiple connections (via
   create/next/close calls), and the typical graceful shutdown method of
   waiting for all open connections to the server to close won't work.

The weight calculation is intended to direct balancing to servers having a
lower load. In particular, since Datawave queries can run over several HTTP
calls involving several TCP connections, the typical load-balancing method of
looking at the least number of connections to a server isn't always accurate.
The weight calculation starts out with a weight of 100%. That weight is then
reduced by several configurable factors to calculate a final weight. That final
weight is clipped to a minimum of 1% (since a 0% weight would change the server
status to drain). The weight reductions are:

1. Query usage percent. The Datawave health endpoint returns a query slot usage
   percent in its results, indicating how "full" the server is. This percentage
   is multiplied by the reduction factor and the resulting reduction is taken
   off the weight.
2. OS load. The Datawave health endpoint returns the current OS load in a
   `[0.0, 1.0]` range. This percentage is multiplied by the load reduction
   factor and the resulting reduction is taken off the weight.
3. Swap usage. If there is any swap in use, the reduction is taken off the
   weight.

Any of these factors can be configured to be 0 to disable the adjustment.

## Install

Install using pip.

```bash
$ pip install datawave_haproxy_agent
```

The use of a virtual environment is recommended:

```bash
$ python3 -m venv ~/agent-env
$ source ~/agent-env/bin/activate
$ pip3 install datawave_haproxy_agent
```

## Configure

Once installed, the agent can be run with the `datawave-haproxy-agent` command.
To see available command-line options, execute:
```bash
$ datawave-haproxy-agent -h
```

By default, the agent expects a YAML configuration file to exist in
`/etc/datawave_haproxy_agent/config.yml`. The location of this file can be
changed with the `--config` argument, or the config file can be skipped
entirely (if default values are sufficient) with `--skip-config`. An example
configuration file can be found in [example_config.yml](./example_config.yml).

HAProxy must be configured to poll the haproxy agent. See
[this documentation](http://cbonte.github.io/haproxy-dconv/2.2/configuration.html#agent-check)
for details.
