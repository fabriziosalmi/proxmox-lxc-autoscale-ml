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
sleep_interval: 120  # Seconds between scaling cycles
```

## Security

### Is the API secure?

Yes. Version 2.0 includes:
- API key authentication on all sensitive endpoints
- Rate limiting (120 requests per minute)
- Input validation on all parameters
- Localhost bypass for internal services

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

## Performance

### How many containers can it handle?

The system has been tested with up to 200 containers. The batch async API client maintains consistent performance regardless of container count.

### What is the performance overhead?

Minimal. The ML model training typically uses less than 5% CPU during training cycles. Memory usage is bounded by the metrics file size limit (default: 1000 entries, approximately 2 MB).

### Why is configuration fetching 10x faster in version 2.0?

Version 2.0 uses asynchronous batch API requests. Instead of fetching container configurations sequentially, all configurations are fetched concurrently. For 60 containers, this reduces fetch time from approximately 6 seconds to 0.6 seconds.

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
