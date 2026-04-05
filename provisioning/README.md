# Bootstrap Provisioning for NoCloud

This subtree provides a bootstrap-only provisioning flow for VMs and physical
machines that fetch `meta-data` and `user-data` over cloud-init NoCloud, join a
tailnet with a short-lived one-time Tailscale auth key, wait for manual
approval, and then pull final secrets from a separate secret API over
Tailscale.

## Components

- `nocloud-bootstrap/`: FastAPI service that serves NoCloud metadata and renders bootstrap cloud-init.
- `secret-api/`: FastAPI service that returns final secrets only after a node is approved.
- `shared/`: SQLAlchemy model and JSON logging utilities shared by both services.
- `scripts/`: CLI helpers for creating nodes, expiring stale records, and booting a local QEMU test VM.
- `policy/`: Example Tailscale ACL policy for a restricted `tag:bootstrap`.
- `docs/`: Architecture, runbook, threat model, and local testing notes.
- `tests/`: pytest coverage for the critical bootstrap path.

## Quick start

1. Initialize the local environment file:

```bash
make init
```

2. Fill in `.env`, especially the Tailscale OAuth client values and `TAILNET_NAME`.

3. Create the local Python environment with `uv`:

```bash
uv sync
```

4. Create the shared local data directory:

```bash
mkdir -p data
```

5. Start the stack:

```bash
make start
```

This renders `tailscale-config/serve.json` from `tailscale-config/serve.template.json` using `TAILNET_NAME` from `.env`, then starts Docker Compose in detached mode.

6. Create a provisioning record manually if you want to inspect the seed details without booting a VM:

```bash
uv run python scripts/create_node.py --hostname vm-bootstrap-01 --base-url http://127.0.0.1:8080
```

This writes the record into `./data/provisioning.db`, which is the same file the Docker services mount at `/data/provisioning.db`.

7. Boot a VM or physical machine with the printed `ds=nocloud` seed URL, or use `make vm IMAGE_PATH=/path/to/ubuntu-cloudimg.qcow2` to create a record and boot a test VM in one step.
8. Approve the device in Tailscale, then let the VM poll `secret-api`.

For a laptop-hosted install onto a physical Intel NUC, see [`docs/nuc-provisioning.md`](../docs/nuc-provisioning.md).

## Makefile targets

The provisioning subtree includes `Makefile` as a thin wrapper around the common local workflows.

- `make init`: Creates `.env` from `.env.example` only when `.env` does not already exist.
- `make start`: Runs `make init`, renders `tailscale-config/serve.json` from the template with `TAILNET_NAME` from `.env`, and starts the Docker Compose stack with `docker compose up --build -d`.
- `make test`: Runs the Python test suite with `uv run pytest`.
- `make vm IMAGE_PATH=/path/to/image.qcow2`: Creates a fresh provisioning record with `scripts/create_node.py`, prints the generated record details including the seed token and seed URL, and then boots the local QEMU test VM using that generated seed token.
- `make clean`: Removes the generated `tailscale-config/serve.json` file and the local `bootstrap-test.qcow2` VM disk.

### `make vm` inputs

- `IMAGE_PATH` is required and must point to the cloud image to boot.
- `VM_NAME` is optional and defaults to `bootstrap-test`. It is used as the hostname passed to `create_node.py`.
- `SEED_BASE_URL` is optional and defaults to `http://127.0.0.1:8080`.

The NoCloud response never includes final secrets. It only includes a time-bounded bootstrap auth key and the bootstrap logic needed to fetch the real payload later.
