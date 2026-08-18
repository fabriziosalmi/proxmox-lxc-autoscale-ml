# Frequently Asked Questions

## General

### What is LXC AutoScale ML?

LXC AutoScale ML is an automated resource management daemon for Proxmox environments. It monitors LXC container resource usage and adjusts CPU and memory allocations based on real-time metrics and machine learning predictions.

### Does scaling cause container downtime?

No. CPU and memory scaling on LXC containers happens without restarting the container. Changes take effect immediately.

### What ML algorithm does it use?

The system uses IsolationForest, an unsupervised machine learning algorithm for anomaly detection. It identifies unusual resource usage patterns that may require scaling.

### How quickly does it respond to load changes?

The default monitoring interval is 60 seconds. Scaling decisions occur after the ML model processes the latest metrics. In practice, expect response times of 1-2 minutes.

## Installation

### What Proxmox versions are supported?

- Proxmox VE 8.x: Tested and fully supported
- Proxmox VE 7.x: Supported
- Proxmox VE 6.x: Supported
- Proxmox VE 5.x and earlier: Not supported

### Can I install it on a cluster?

Install LXC AutoScale ML on each Proxmox node where you want automated scaling. Each installation manages containers on that specific node.

### Does it work with VMs?

No. This tool is designed specifically for LXC containers. For VM autoscaling, consider a separate solution.

## Configuration

### How do I exclude specific containers from scaling?

Add container IDs to the `ignore_lxc` list in `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`:

```yaml
ignore_lxc:
  - "101"
  - "102"
```

### What are the default scaling thresholds?

| Threshold | Default Value |
|-----------|---------------|
| CPU scale up | 70% |
| CPU scale down | 30% |
| RAM scale up | 80% |
| RAM scale down | 40% |

### Can I set different limits per container?

Currently, resource limits (min/max CPU and RAM) are global settings. All containers share the same limits defined in configuration.

### How do I change the scaling interval?

Edit `/etc/lxc_autoscale_ml/lxc_autoscale_ml.yaml`:

```yaml
interval_seconds: 120  # Seconds between scaling cycles
```

## Security

### Is the API secure?

Only if you configure it that way. The defaults are permissive:

- **Authentication is off** (`authentication.enabled: false`). Turn it on and
  add keys before exposing the API anywhere.
- **It binds to every interface** (`server.host: 0.0.0.0`). Set `127.0.0.1`
  unless the model runs on a different host.
- **It runs as root**, because `pct` requires it, and speaks plain HTTP. Put TLS
  in front of it if it has to cross a network.

What is on by default: per-IP rate limiting at 120 requests a minute with
localhost exempt, and input validation on every parameter. Commands are handed
to the kernel as argument lists and never go through a shell.

### Where should I store my API key?

Store the API key in the configuration file `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml`. This file should be readable only by root:

```bash
chmod 600 /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml
```

### Can I use HTTPS?

The API does not include built-in TLS support. Use a reverse proxy (such as Nginx) to add HTTPS:

```nginx
server {
    listen 443 ssl;
    server_name proxmox-api.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
    }
}
```

::: warning Rate limiting does not work behind this proxy
The limiter exempts `127.0.0.1`, which is what `proxy_pass` makes every request
look like. Nothing in the API reads `X-Real-IP` or `X-Forwarded-For`, so with
nginx in front the per-IP limit is effectively disabled and the "invalid API
key" warnings all log `127.0.0.1`.

Installing a proxy-header fixer here would be **worse**, not better: with
`server.host: 0.0.0.0` any client that can reach the port directly could then
spoof `X-Forwarded-For: 127.0.0.1` and exempt itself. Until the API can be told
which proxies to trust, rate limit in nginx itself (`limit_req_zone`) and treat
the API's own limiter as covering only direct callers.
:::


## Performance

### How many containers can it handle?

Configuration reads are issued concurrently, up to `api.max_concurrent` at a
time, so the fetch stage does not grow linearly with container count. The
scaling decisions themselves are made one container at a time. No specific
upper bound has been measured.

### What is the performance overhead?

The model is retrained from the full metrics file on every cycle, so cost grows
with history length; the file is capped at `max_metrics_entries` cycles (1000 by
default), which bounds it. The monitor records its own CPU and memory use in the
`summary` block of each cycle, so you can read the real figures for your host
there rather than trusting an estimate.

### How are container configurations fetched?

Concurrently, rather than one after another, with at most `api.max_concurrent`
requests in flight (10 by default) and exponential backoff on server errors.
Each cycle logs how long the fetch took and how many succeeded, so the real
figure for your host is in the log.

## Troubleshooting

### Why isn't my container scaling?

Common reasons:
1. Container is in the `ignore_lxc` list
2. Current usage is between scale-up and scale-down thresholds
3. Container is already at min/max resource limits
4. Insufficient metrics history (need 5-10 data points)

Check the logs for details:

```bash
journalctl -u lxc_autoscale_ml -n 50
```

### What does "IsolationForest prediction: -1" mean?

A prediction of -1 indicates an anomaly (unusual resource usage pattern). A prediction of 1 indicates normal behavior. Anomaly detection triggers evaluation of scaling thresholds.

### How do I reset the metrics history?

```bash
echo "[]" > /var/log/lxc_metrics.json
systemctl restart lxc_monitor
```

### Why do I see "Circuit breaker open" in logs?

The circuit breaker opens after 5 consecutive API failures for a specific endpoint. This prevents wasted resources on failing requests. It automatically resets after 5 minutes.

## Monitoring

### Does it support Prometheus?

Yes. Metrics are available at `/metrics` endpoint without authentication:

```bash
curl http://localhost:5000/metrics
```

### What metrics are exported?

- Scaling actions (count by container, action type, resource)
- API requests (count by endpoint, method, status)
- Container resources (CPU cores, memory)
- Circuit breaker status
- Model predictions

### Can I use Grafana?

Yes. Configure Prometheus to scrape the `/metrics` endpoint, then create Grafana dashboards using the exported metrics.

## Maintenance

### How do I upgrade to a new version?

See the [Upgrading Guide](/guide/upgrading) for detailed instructions.

### How do I back up the configuration?

```bash
cp -r /etc/lxc_autoscale_ml /etc/lxc_autoscale_ml.backup
```

### Is there a dry-run mode?

Yes. Enable it in configuration:

```yaml
scaling:
  dry_run: true
```

Scaling decisions are logged but not executed.

## Contributing

### How can I contribute?

Contributions are welcome. See the repository for guidelines:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

### Where do I report bugs?

Open an issue on [GitHub Issues](https://github.com/fabriziosalmi/proxmox-lxc-autoscale-ml/issues).

### Is there a roadmap?

The project roadmap is tracked through GitHub issues and milestones.
