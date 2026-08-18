# API Component

The API component provides a RESTful interface for managing LXC containers on Proxmox.

## Overview

| Property | Value |
|----------|-------|
| Service | `lxc_autoscale_api` |
| Configuration | `/etc/lxc_autoscale_ml/lxc_autoscale_api.yaml` |
| Default Port | 5000 |
| Log File | `/var/log/lxc_autoscale_api.log` |

## Features

- **Scaling Operations**: Set CPU cores, memory, and storage
- **Snapshot Management**: Create, list, and rollback snapshots
- **Container Cloning**: Clone and delete containers
- **Resource Monitoring**: Query container and node status
- **Prometheus Metrics**: Export metrics at `/metrics`
- **Security**: API key authentication, rate limiting, input validation

## Security

### API Key Authentication

All endpoints except `/health/check` and `/metrics` require authentication.

**Configuration:**

```yaml
authentication:
  enabled: true
  api_keys:
    - "your-secret-api-key"
```

**Usage:**

```bash
# Header authentication (recommended)
curl -H "X-API-Key: your-key" http://localhost:5000/routes

# Query parameter authentication
curl -H "X-API-Key: your-key" http://localhost:5000/routes
```

**Error response (401 Unauthorized):**

```json
{
  "status": "error",
  "error": "Missing or invalid API key"
}
```

### Rate Limiting

Protects the API from abuse while allowing internal services unlimited access.

**Configuration:**

```yaml
rate_limiting:
  enabled: true
  max_requests_per_minute: 120
  time_window_seconds: 60
```

**Features:**
- Localhost bypass: Requests from `127.0.0.1` are never rate limited
- Per-IP tracking: Each client IP has its own request counter
- Sliding window: 60-second rolling window

**Response headers:**

```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1703436789
```

**Error response (429 Too Many Requests):**

```json
{
  "status": "error",
  "error": "Rate limit exceeded",
  "retry_after_seconds": 45,
  "limit": 120,
  "window_seconds": 60
}
```

### Input Validation

All parameters are validated to prevent injection attacks.

| Parameter | Validation |
|-----------|------------|
| `lxc_id` | Integer between 100 and 999999 |
| `cores` | Integer between 1 and 128 |
| `memory` | Integer between 64 (MB) and 1048576 (1 TB) |
| `disk_size` | Positive integer (GB) |
| `snapshot_name` | Alphanumeric, underscore, hyphen (max 100 chars) |
| `node_name` | Alphanumeric, hyphen, underscore (max 50 chars) |

## Endpoints

### Health Check

```
GET /health/check
```

No authentication required.

```bash
curl http://localhost:5000/health/check
```

### Prometheus Metrics

```
GET /metrics
```

No authentication required.

```bash
curl http://localhost:5000/metrics
```

### Scale CPU Cores

```
POST /scale/cores
```

**Request:**

```bash
curl -X POST http://localhost:5000/scale/cores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "cores": 4}'
```

**Response:**

```json
{
  "status": "success",
  "message": "CPU cores set to 4 for VM 104"
}
```

### Scale RAM

```
POST /scale/ram
```

**Request:**

```bash
curl -X POST http://localhost:5000/scale/ram \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "memory": 4096}'
```

### Increase Storage

```
POST /scale/storage/increase
```

**Request:**

```bash
curl -X POST http://localhost:5000/scale/storage/increase \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "disk_size": 5}'
```

### Create Snapshot

```
POST /snapshot/create
```

**Request:**

```bash
curl -X POST http://localhost:5000/snapshot/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "snapshot_name": "backup_20241224"}'
```

### List Snapshots

```
GET /snapshot/list?lxc_id=<id>
```

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:5000/snapshot/list?lxc_id=104"
```

### Rollback Snapshot

```
POST /snapshot/rollback
```

```bash
curl -X POST http://localhost:5000/snapshot/rollback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "snapshot_name": "backup_20241224"}'
```

### Clone Container

```
POST /clone/create
```

```bash
curl -X POST http://localhost:5000/clone/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "test_clone"}'
```

### Delete Clone

```
DELETE /clone/delete
```

```bash
curl -X DELETE http://localhost:5000/clone/delete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"lxc_id": 105}'
```

### Get VM Status

```
GET /resource/lxc/status?lxc_id=<id>
```

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:5000/resource/lxc/status?lxc_id=104"
```

### Get VM Configuration

```
GET /resource/lxc/config?lxc_id=<id>
```

Returns min/max resource limits for a container.

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:5000/resource/lxc/config?lxc_id=104"
```

### Get Node Status

```
GET /resource/node/status?node_name=<name>
```

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:5000/resource/node/status?node_name=proxmox"
```

### List Routes

```
GET /routes
```

```bash
curl -H "X-API-Key: your-key" http://localhost:5000/routes
```

## Configuration Reference

```yaml
# /etc/lxc_autoscale_ml/lxc_autoscale_api.yaml

# Server settings
server:
  host: "0.0.0.0"
  port: 5000

# Authentication
authentication:
  enabled: true
  api_keys:
    - "your-secret-api-key"

# Rate limiting
rate_limiting:
  enabled: true
  max_requests_per_minute: 120
  time_window_seconds: 60

# Logging
logging:
  level: "INFO"
  # log_file: "/var/log/lxc_autoscale_api.log"  # unset: stdout only
  rotate: true
  max_log_size_mb: 100
  backup_count: 5

# HTTP access and error logs belong to gunicorn
gunicorn:
  access_log_file: "/var/log/lxc_autoscale_api_access.log"
  error_log_file: "/var/log/lxc_autoscale_api_error.log"
```

## Log Files

| File | Content |
|------|---------|
| `/var/log/lxc_autoscale_api.log` | Main API logs |
| `/var/log/lxc_autoscale_api_access.log` | All incoming requests |
| `/var/log/lxc_autoscale_api_error.log` | Error logs |

## HTTPS Setup

Use a reverse proxy for HTTPS. Example Nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name proxmox-api.example.com;

    ssl_certificate /etc/ssl/certs/proxmox-api.crt;
    ssl_certificate_key /etc/ssl/private/proxmox-api.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
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


## Next Steps

- [API Endpoints Reference](/reference/api-endpoints): Complete endpoint documentation
- [Metrics Reference](/reference/metrics): Prometheus metrics details
- [Model Component](/components/model): ML engine documentation
