# Homelab

A reproducible homelab Kubernetes cluster on Ubuntu 24.04 using microk8s,
ArgoCD, External Secrets Operator, Tailscale, and Infisical.

No secrets are committed to git. Every node is provisioned from scratch via
an automated cloud-init + bootstrap flow with zero manual secret handling.

## How it works

### Provisioning flow

```
Operator                nocloud-bootstrap       secret-api (on Tailscale)
   |                          |                        |
   |-- create_node.py ------->|                        |
   |                          |                        |
   |        VM boots with ds=nocloud;s=http://.../seed/<token>/
   |                          |                        |
   |                 cloud-init fetches                |
   |                 meta-data + user-data             |
   |                          |                        |
   |              cloud-init runs bootstrap.sh         |
   |                          |                        |
   |              Tailscale joins tailnet              |
   |-- approve device in Tailscale Admin UI            |
   |                          |                        |
   |              bootstrap.sh calls POST /v1/bootstrap-secrets
   |                          |                        |
   |                          |-- Infisical: fetch secrets -->
   |                          |<- secrets + INFISICAL credentials -
   |                          |                        |
   |              node seeds infisical-universal-auth k8s Secret
   |              node wipes /etc/bootstrap/secrets.env
   |                          |                        |
   |              microk8s bootstraps or joins cluster |
   |                          |                        |
   |-- apply bootstrap/argocd-bootstrap-manifests/ --->|
   |                                                   |
   |              ArgoCD reconciles apps/              |
   |              ESO syncs secrets from Infisical     |
```

### Secret delivery

Secrets never appear in git or in cloud-init responses. They are delivered
only after the node has joined the tailnet and been manually approved.
`secret-api` fetches secrets from Infisical Cloud at request time using
Universal Auth, injects them into the bootstrap payload, and the node
discards the credentials file immediately after seeding ESO.

### GitOps reconciliation

Once ArgoCD is bootstrapped it takes ownership of the cluster state from this
repo. Everything under `apps/` is reconciled automatically — operators,
workloads, and secrets configuration.

## Repository layout

```
bootstrap/
  argocd-bootstrap-manifests/   # One-time bootstrap: ArgoCD + ESO CRDs
argocd/
  app-of-apps.yaml              # Root ArgoCD Application watching apps/
apps/
  other-operators/
    external-secrets/           # ESO Helm Application + ClusterSecretStore
  tailscale-operator/           # Tailscale operator + ExternalSecret
  workloads/
helm-values/                    # Helm value overrides referenced by ArgoCD apps
provisioning/                   # Provisioning services (see provisioning/README.md)
  nocloud-bootstrap/            # Serves cloud-init seed data over HTTP
  secret-api/                   # Delivers secrets post-Tailscale-approval
  scripts/                      # create_node.py, qemu_test.sh
  docs/                         # Architecture, runbooks, threat model
```

## Prerequisites

- Docker + Docker Compose (for provisioning services)
- `qemu-system-aarch64` + `qemu-img` (for local VM testing)
- EDK2 AARCH64 firmware (`/opt/homebrew/share/qemu/edk2-aarch64-code.fd`)
- A Tailscale account with an OAuth client and ACL tag `tag:bootstrap`
- An Infisical Cloud account with a Machine Identity (Universal Auth)

## Quick start

### 1. Configure provisioning services

```bash
cd provisioning
make init          # copies .env.example → .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `TAILNET_NAME` | Your tailnet name (e.g. `example.ts.net`) |
| `TS_API_CLIENT_ID` | Tailscale OAuth client ID |
| `TS_API_CLIENT_SECRET` | Tailscale OAuth client secret |
| `INFISICAL_CLIENT_ID` | Infisical Machine Identity client ID |
| `INFISICAL_CLIENT_SECRET` | Infisical Machine Identity client secret |
| `INFISICAL_PROJECT_ID` | Infisical project ID |
| `INFISICAL_ENVIRONMENT` | Infisical environment (e.g. `prod`) |
| `BOOTSTRAP_SSH_IMPORT_ID` | `gh:username` to import SSH keys from GitHub |

### 2. Start provisioning services

```bash
cd provisioning
make start
```

This starts `nocloud-bootstrap` (port 8080) and `secret-api` (Tailscale-only,
served via `tailscale serve`).

### 3. Provision a node

```bash
cd provisioning
python scripts/create_node.py --hostname k8s-01
```

For local VM testing:

```bash
IMAGE_PATH=~/Downloads/ubuntu-24.04-server-cloudimg-arm64.img make vm
```

### 4. Approve the device

The node boots, joins the tailnet with `tag:bootstrap`, and waits.
Approve it in the [Tailscale Admin console](https://login.tailscale.com/admin/machines).
The bootstrap script then fetches secrets and completes automatically.

### 5. Bootstrap ArgoCD

After the first node finishes bootstrapping:

```bash
microk8s kubectl apply -k bootstrap/argocd-bootstrap-manifests/
```

ArgoCD installs itself, then reconciles `apps/` — deploying ESO, Tailscale
operator, and any workloads. ESO reads the `infisical-universal-auth` secret
seeded during bootstrap to sync secrets from Infisical.

## Secrets management

| Layer | Mechanism |
|---|---|
| Bootstrap credentials | Delivered by `secret-api` at first boot, wiped immediately after use |
| ESO auth | `infisical-universal-auth` k8s Secret seeded by bootstrap node |
| Application secrets | `ExternalSecret` resources pull from Infisical via ESO |
| Git | No secrets ever committed |

To rotate the ESO credentials:

1. Generate a new client secret in Infisical for the Machine Identity.
2. Update `INFISICAL_CLIENT_SECRET` in `.env` and restart the provisioning services.
3. On the cluster: `kubectl create secret generic infisical-universal-auth -n external-secrets --from-literal=clientId=... --from-literal=clientSecret=... --dry-run=client -o yaml | kubectl apply -f -`

## Adding nodes

1. `python scripts/create_node.py --hostname k8s-02`
2. Boot the new node with the seed URL (or `make vm` for local testing).
3. Approve in Tailscale Admin.
4. The node bootstraps and joins the existing cluster automatically via
   `microk8s join`.

## ArgoCD app structure

```
homelab-system (argocd/)
  └── app-of-apps watches apps/

homelab-apps (apps/)
  ├── external-secrets        ESO Helm chart + ClusterSecretStore (Infisical)
  ├── tailscale-operator      Tailscale operator + ExternalSecret
  └── workloads/whoami        Example workload
```

## Cluster access

The cluster API is not exposed publicly. Access is via Tailscale MagicDNS.
ArgoCD UI is available after bootstrap at the node's Tailscale address.

## Running tests

```bash
cd provisioning
make test
```

21 tests covering secret delivery, cluster bootstrap role assignment,
cloud-init rendering, and Tailscale auth key generation.
