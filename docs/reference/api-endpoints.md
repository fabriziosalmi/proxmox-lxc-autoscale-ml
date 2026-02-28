# API Endpoints Reference

Complete reference for all LXC AutoScale ML API endpoints.

## Authentication

All endpoints except `/health/check` and `/metrics` require authentication.

**Header authentication (recommended):**

```bash
curl -H "X-API-Key: your-key" http://localhost:5000/endpoint
```

**Query parameter authentication:**

```bash
curl "http://localhost:5000/endpoint?api_key=your-key"
```

## Endpoints Summary

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
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
  "timestamp": "2024-12-24T12:00:00Z"
}
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
# HELP lxc_scaling_actions_total Total scaling actions
# TYPE lxc_scaling_actions_total counter
lxc_scaling_actions_total{container_id="104",action="scale_up",resource="cpu"} 15
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
{
  "status": "success",
  "routes": [
    {"endpoint": "/health/check", "methods": ["GET"]},
    {"endpoint": "/scale/cores", "methods": ["POST"]},
    ...
  ]
}
```

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
  "message": "CPU cores set to 4 for LXC 104"
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 400 | Invalid parameters |
| 401 | Missing/invalid API key |
| 404 | Container not found |
| 500 | Scaling failed |

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
  "message": "Memory set to 4096 MB for LXC 104"
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
  "message": "Storage increased by 5 GB for LXC 104"
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
  "message": "Snapshot 'backup_20241224' created for LXC 104"
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
  "data": [
    {
      "name": "backup_20241224",
      "timestamp": "2024-12-24T06:00:00Z",
      "description": ""
    }
  ]
}
```

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
  "message": "Rolled back LXC 104 to snapshot 'backup_20241224'"
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
  "message": "Cloned LXC 104 to new LXC 105 (test_clone)"
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
  "message": "Deleted LXC 105"
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
  "message": "Successfully retrieved configuration for LXC 104"
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

## Error Responses

### 400 Bad Request

Invalid parameters:

```json
{
  "status": "error",
  "error": "Invalid lxc_id: must be between 100 and 999999"
}
```

### 401 Unauthorized

Missing or invalid API key:

```json
{
  "status": "error",
  "error": "Missing or invalid API key"
}
```

### 429 Too Many Requests

Rate limit exceeded:

```json
{
  "status": "error",
  "error": "Rate limit exceeded",
  "retry_after_seconds": 45,
  "limit": 120,
  "window_seconds": 60
}
```

### 500 Internal Server Error

Server error:

```json
{
  "status": "error",
  "error": "Internal server error",
  "details": "Error message"
}
```
