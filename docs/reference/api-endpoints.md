# API Endpoints Reference

Complete reference for all LXC AutoScale ML API endpoints.

## Authentication

::: warning Disabled in the shipped configuration
`authentication.enabled` defaults to **false**, and `server.host` defaults to
`0.0.0.0`. Out of the box this API is reachable on every interface with no
credential, and it runs as root. See
[Configuration](/reference/configuration) before exposing it.
:::

When enabled, every endpoint except `/`, `/health/check` and `/metrics`
requires a key, supplied in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-key" http://localhost:5000/resource/lxc/status?lxc_id=104
```

The `?api_key=` query-parameter form was removed: gunicorn's access log records
the request line, so the key ended up in a log file, in shell history, and in
any proxy log in front of the API.

If you enable authentication, set `api.api_key` in the **model** configuration
to a matching value. The model has no other way to authenticate, and without it
autoscaling stops with a 401 on every call.

## Endpoints Summary

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | No | Self-documenting index |
| `/health/check` | GET | No | API health status |
| `/metrics` | GET | No | Prometheus metrics |
| `/routes` | GET | Yes | List all routes |
| `/scale/cores` | POST | Yes | Set CPU cores |
| `/scale/ram` | POST | Yes | Set RAM |
| `/scale/storage/increase` | POST | Yes | Increase storage |
| `/snapshot/create` | POST | Yes | Create snapshot |
| `/snapshot/list` | GET | Yes | List snapshots |
| `/snapshot/rollback` | POST | Yes | Rollback snapshot |
| `/clone/create` | POST | Yes | Clone container |
| `/clone/delete` | DELETE | Yes | Delete container |
| `/resource/lxc/status` | GET | Yes | Container status |
| `/resource/lxc/config` | GET | Yes | Container config |
| `/resource/node/status` | GET | Yes | Node status |
| `/resource/cluster/status` | GET | Yes | Cluster status |

---

## Naming and compatibility

These objects are LXC containers, not VMs, and the API says so. The older
`vm` spelling is deprecated but still accepted, so existing scripts keep
working without changes:

| Preferred | Deprecated alias |
|-----------|------------------|
| `/resource/lxc/status` | `/resource/vm/status` |
| `/resource/lxc/config` | `/resource/vm/config` |
| `lxc_id` | `vm_id`, `container_id` |
| `new_lxc_id` | `new_vm_id` |
| `new_lxc_name` | `new_vm_name`, `hostname` |

**GET** endpoints take their parameters from the query string. **POST** and
**DELETE** endpoints require a JSON body: accepting the query string on
mutating methods made them drivable by a cross-origin HTML form, which is a
CORS simple request and needs no preflight.

---

## Health and Monitoring

### GET /health/check

Check API server health. No authentication required.

**Request:**

```bash
curl http://localhost:5000/health/check
```

**Response (200 OK):**

```json
{
  "status": "healthy",
  "checks": {
    "lxc_commands": { "ok": true, "detail": "ok" }
  }
}

Returns **503** with the same shape when a check fails, so it can be used
directly as a systemd or load-balancer probe.
```

---

### GET /metrics

Prometheus metrics. No authentication required.

**Request:**

```bash
curl http://localhost:5000/metrics
```

**Response (200 OK):**

```
# HELP lxc_autoscale_scaling_actions_total Total scaling actions performed
# TYPE lxc_autoscale_scaling_actions_total counter
lxc_autoscale_scaling_actions_total{container_id="104",resource="cpu",action="set"} 15
...
```

---

### GET /routes

List all available API routes.

**Request:**

```bash
curl -H "X-API-Key: YOUR_KEY" http://localhost:5000/routes
```

**Response (200 OK):**

```json
[
  {
    "endpoint": "set_cores",
    "methods": "OPTIONS,POST",
    "url": "/scale/cores"
  },
  {
    "endpoint": "get_lxc_config_route",
    "methods": "GET,HEAD,OPTIONS",
    "url": "/resource/lxc/config"
  }
]
```

A bare array, not an object. `endpoint` is Flask's internal view name, `url` is
the route, and `methods` is a comma-joined string that includes the ones Flask
adds for you (`HEAD`, `OPTIONS`).

---

## Scaling Operations

### POST /scale/cores

Set the number of CPU cores for a container.

**Request:**

```bash
curl -X POST http://localhost:5000/scale/cores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 104, "cores": 4}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |
| `cores` | integer | Yes | 1-128 |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "CPU cores set to 4 for VM 104"
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 400 | Validation failed, or no JSON body |
| 401 | Authentication enabled, no `X-API-Key` header |
| 403 | `X-API-Key` sent but wrong |
| 429 | Rate limit exceeded |
| 500 | The `pct` command failed — including when the container does not exist |

---

### POST /scale/ram

Set the amount of RAM for a container.

**Request:**

```bash
curl -X POST http://localhost:5000/scale/ram \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 104, "memory": 4096}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |
| `memory` | integer | Yes | 64-1048576 (MB) |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Memory set to 4096 MB for VM 104"
}
```

---

### POST /scale/storage/increase

Increase the storage size of a container's root filesystem.

**Request:**

```bash
curl -X POST http://localhost:5000/scale/storage/increase \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 104, "disk_size": 5}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |
| `disk_size` | integer | Yes | Positive integer (GB) |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Storage increased by 5 GB for VM 104"
}
```

::: warning
Storage can only be increased, not decreased.
:::

---

## Snapshot Operations

### POST /snapshot/create

Create a snapshot of a container.

**Request:**

```bash
curl -X POST http://localhost:5000/snapshot/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 104, "snapshot_name": "backup_20241224"}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |
| `snapshot_name` | string | Yes | Alphanumeric, `_`, `-` (max 100 chars) |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Snapshot 'backup_20241224' created for VM 104"
}
```

---

### GET /snapshot/list

List all snapshots for a container.

**Request:**

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:5000/snapshot/list?lxc_id=104"
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Snapshots listed for container 104",
  "data": "backup_20241224            2024-12-24 06:00:00     no-description"
}
```

::: warning
`data` is the raw stdout of `pct listsnapshot`, not a structured list. Every
endpoint that wraps a `pct` command returns its output verbatim in `data`; parse
it as text, and expect the format to follow whatever your Proxmox version emits.
:::

---

### POST /snapshot/rollback

Rollback a container to a specific snapshot.

**Request:**

```bash
curl -X POST http://localhost:5000/snapshot/rollback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 104, "snapshot_name": "backup_20241224"}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |
| `snapshot_name` | string | Yes | Alphanumeric, `_`, `-` (max 100 chars) |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Rolled back VM 104 to snapshot 'backup_20241224'"
}
```

::: warning
This operation may stop the container temporarily.
:::

---

## Clone Operations

### POST /clone/create

Clone a container.

**Request:**

```bash
curl -X POST http://localhost:5000/clone/create \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 104, "new_lxc_id": 105, "new_lxc_name": "test_clone"}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |
| `new_lxc_id` | integer | Yes | 100-999999 |
| `new_lxc_name` | string | Yes | Alphanumeric, `_`, `-` |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Cloned VM 104 to new VM 105 (test_clone)"
}
```

---

### DELETE /clone/delete

Delete a container.

**Request:**

```bash
curl -X DELETE http://localhost:5000/clone/delete \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"lxc_id": 105}'
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Deleted VM 105"
}
```

::: danger
This operation permanently deletes the container.
:::

---

## Resource Information

### GET /resource/lxc/status

Get resource allocation and usage for a container.

**Request:**

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:5000/resource/lxc/status?lxc_id=104"
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |

**Response (200 OK):**

```json
{
  "status": "success",
  "data": {
    "lxc_id": "104",
    "status": "running",
    "cpu": 4,
    "memory": 8192,
    "disk": 20,
    "uptime": 86400
  }
}
```

---

### GET /resource/lxc/config

Get min/max resource limits for a container.

**Request:**

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:5000/resource/lxc/config?lxc_id=104"
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `lxc_id` | integer | Yes | 100-999999 |

**Response (200 OK):**

```json
{
  "status": "success",
  "data": {
    "lxc_id": "104",
    "cores": 4,
    "memory_mb": 8192
  },
  "message": "Successfully retrieved configuration for VM 104"
}
```

---

### GET /resource/node/status

Get resource usage for a Proxmox node.

**Request:**

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:5000/resource/node/status?node_name=proxmox"
```

**Parameters:**

| Name | Type | Required | Validation |
|------|------|----------|------------|
| `node_name` | string | Yes | Alphanumeric, `-`, `_` (max 50 chars) |

**Response (200 OK):**

```json
{
  "status": "success",
  "data": {
    "node": "proxmox",
    "cpu_usage": 45.2,
    "memory_usage": 78.5,
    "memory_total": 65536,
    "memory_used": 51200,
    "uptime": 864000
  }
}
```

---

## Error responses

Every error body uses `message`; validation errors add `errors`. None of them
use `error` or `details`, which earlier versions of this page showed.

### 400 Bad Request

Validation failed, or a mutating request arrived without a JSON body:

```json
{
  "status": "error",
  "message": "Validation failed",
  "errors": [
    "Cores must be between 1 and 128, got 999"
  ]
}
```

`errors` lists every field that failed, not just the first.

### 401 Unauthorized

Authentication is enabled and no `X-API-Key` header was sent:

```json
{
  "status": "error",
  "message": "Missing API key. Provide it in the X-API-Key header."
}
```

### 403 Forbidden

A key was sent and it does not match. **A wrong key is 403, not 401** — 401
means the header was absent.

```json
{
  "status": "error",
  "message": "Invalid API key"
}
```

### 429 Too Many Requests

```json
{
  "status": "error",
  "error": "Rate limit exceeded. Please try again later.",
  "retry_after_seconds": 45,
  "limit": 120,
  "window_seconds": 60
}
```

Carries `Retry-After` and the `X-RateLimit-*` headers. This is the one error
body that uses `error` rather than `message`.

### 500 Internal Server Error

The `pct` command failed, timed out, or is not installed:

```json
{
  "status": "error",
  "message": "An internal error occurred. Please contact support if the issue persists."
}
```

With `error_handling.show_stack_traces: true` the message carries the exception
text and a `stack_trace` field is added. Leave it off outside debugging: the
exception text can include `pct` stderr.

::: warning There is no 404
A container that does not exist makes `pct` fail, which surfaces as **500**, not
404. Nothing in the API distinguishes "absent" from "broken".
:::
