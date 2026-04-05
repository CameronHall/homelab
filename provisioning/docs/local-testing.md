# Local Testing

## Docker Compose setup

```bash
make init
mkdir -p data
uv sync
make start
```

The stack starts:

- `nocloud-bootstrap` on `http://127.0.0.1:8080`
- `secret-api` on `http://127.0.0.1:8081`

Both services share the same SQLite database file under `./data/provisioning.db`.

## Run pytest

```bash
make test
```

## Create a local record

```bash
uv run python scripts/create_node.py \
  --hostname local-bootstrap-01 \
  --base-url http://127.0.0.1:8080 \
  --database-url sqlite:///./data/provisioning.db
```

## QEMU test instructions

Use an Ubuntu cloud image and point QEMU at the NoCloud base URL:

```bash
make vm IMAGE_PATH=/path/to/noble-server-cloudimg-amd64.img
```

The Makefile target creates a provisioning record first, then passes:

```text
ds=nocloud;s=http://127.0.0.1:8080/seed/<token>/
```

through the SMBIOS serial number so cloud-init fetches:

- `/seed/<token>/meta-data`
- `/seed/<token>/user-data`

## Simulate approval in development

For local development, toggle the provisioning record directly in SQLite:

```bash
sqlite3 ./data/provisioning.db \
  "UPDATE provisioning_records SET approved = 1, state = 'approved' WHERE node_id = '<node id>';"
```

If you want to emulate Tailscale Serve locally, pass an app capability header manually:

```bash
curl -X POST http://127.0.0.1:8081/v1/bootstrap-secrets \
  -H 'Content-Type: application/json' \
  -H 'Tailscale-App-Capabilities: {"homelab.local/cap/bootstrap":[{"role":"bootstrap-client"}]}' \
  -d '{"node_id":"<node id>","hostname":"<hostname>","instance_id":"<instance id>"}'
```
