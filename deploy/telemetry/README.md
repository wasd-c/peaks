# Peaks diagnostics relay

The installed app sends optional technical diagnostics to
`https://metrics.gemstud.io/peaks/v1/events`. Sharing starts **off** and can be
enabled in Settings → Privacy & security → Share app diagnostics.

The payload contains only a fixed event name, public app version, platform,
allowlisted command name, success/failure, and rounded duration. No account,
player, match, machine, persistent installation identifier, exception text,
cookies, credentials, or local paths are collected. Events are sampled per
category per minute and held in a bounded memory-only queue. Opting out drops
the queue and aborts delivery. Development and demo builds never transmit.

`ingest.py` validates the same fixed schema a second time, limits batches and
request rates, and sends records to the `peaks` log stream in OpenObserve.
Source addresses are used in memory for rate limiting but are not forwarded.
The gateway must overwrite `X-Peaks-Source` from its trusted network source
and disable request access logging for this route. This public write-only
endpoint is appropriate for anonymous diagnostics; it is not an authenticated
measurement of individual installs and must not be used for billing.

Deployment requires an existing OpenObserve service on the Docker telemetry
network. Create a server-only, mode-600 `telemetry.env` containing
`OPENOBSERVE_AUTH_TOKEN` and `OPENOBSERVE_ORGANIZATION`. Use a dedicated ingestion
identity where available. Never put these credentials in Peaks or Git.
Run `docker compose up -d --build` and proxy only `/peaks/v1/events` to
`peaks-telemetry-ingest:3009`. The relay exposes no host port, has no read API,
and uses the server's existing OpenObserve retention policy.

Example gateway handler inside the existing Caddy `route`:

```caddyfile
@peaks path /peaks/v1/events
log_skip @peaks
handle @peaks {
    request_body { max_size 16KB }
    reverse_proxy peaks-telemetry-ingest:3009 {
        header_up X-Peaks-Source {http.request.header.Cf-Connecting-Ip}
        header_up -Authorization
        header_up -Cookie
    }
}
```

Only trust `Cf-Connecting-Ip` when this gateway is reached exclusively through
your Cloudflare tunnel. Otherwise use a validated proxy configuration and the
actual client IP instead. The internal network must not contain untrusted
workloads.
