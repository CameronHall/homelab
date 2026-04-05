# Architecture

## Overview

The bootstrap flow is intentionally split into two planes:

1. `nocloud-bootstrap` serves cloud-init NoCloud `meta-data` and `user-data`.
2. `secret-api` returns the final secrets and config only after a node is approved in Tailscale.

Cloud-init is treated as a bootstrap channel only. Its job is to get the machine online in a tightly-scoped bootstrap identity, not to deliver long-lived secrets.

## Flow

1. An operator creates a provisioning record with `scripts/create_node.py`.
2. The VM boots with `ds=nocloud;s=http(s)://.../seed/<token>/`.
3. The first successful `GET /seed/<token>/user-data` causes `nocloud-bootstrap` to:
   - load the provisioning record
   - reject expired tokens
   - create a fresh one-time Tailscale auth key through the OAuth-backed Tailscale API
   - persist the auth key metadata
   - render bootstrap-only cloud-init
4. Cloud-init installs Tailscale, calls `tailscale up --advertise-tags=tag:bootstrap`, and starts `bootstrap.sh`.
5. `bootstrap.sh` waits for manual machine approval and Tailscale connectivity.
6. After the node is approved, `bootstrap.sh` calls `POST /v1/bootstrap-secrets` on `secret-api`.
7. `secret-api` checks:
   - `Tailscale-App-Capabilities` from Tailscale Serve, when present
   - LocalAPI / `tailscale whois` fallback if Serve capabilities are absent
   - the provisioning record for that node
   - record expiry
   - approval state
8. Only then does `secret-api` return the final env/files/config payload.

## Trust boundaries

### NoCloud endpoint

The NoCloud service is sensitive because it issues the short-lived bootstrap auth key. It should bind only to trusted interfaces and use short per-node random seed tokens. The seed token is an authorization secret for obtaining bootstrap-only credentials.

### Tailscale OAuth client

The Tailscale OAuth client secret lives only in service environment configuration. It is never returned to the VM and never logged. The bootstrap service uses it only to mint short-lived one-off auth keys.

### Bootstrap identity

`secret-api` must not trust the request body by itself. The implementation now treats Tailscale Serve app capabilities as the primary authorization signal and falls back to Tailscale LocalAPI / `tailscale whois` when the capability header is absent. The backend is intended to listen on `127.0.0.1` only so callers cannot spoof Serve headers by reaching it directly.

### Final secrets

Final secrets never appear in NoCloud responses. They are delivered only after:

- the node has joined the tailnet
- the node identity matches the provisioning record
- the node is approved

## Why cloud-init is bootstrap only

Cloud-init data is easy to inspect locally on the target machine and is commonly preserved in cloud-init state, logs, and instance metadata history. That makes it a poor place for long-lived secrets.

In this design, cloud-init contains only:

- the short-lived one-time bootstrap auth key
- the bootstrap hostname/node metadata
- the logic needed to fetch the final payload later

This reduces the blast radius if the seed channel is exposed or the VM image is inspected after first boot.
