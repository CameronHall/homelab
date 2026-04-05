# Threat Model

## Primary risks

### Exposed NoCloud endpoint

If the NoCloud endpoint is reachable from an untrusted network, anyone with a valid seed token can obtain the bootstrap cloud-init and the short-lived one-time auth key.

Mitigations:

- bind `nocloud-bootstrap` only to trusted interfaces
- use long random per-node seed tokens
- enforce short record TTLs
- expire or clear stale records aggressively

### Stolen bootstrap auth key

The generated Tailscale auth key is still sensitive while it is valid. If stolen before use, an attacker may attempt to join the tailnet with `tag:bootstrap`.

Why manual approval matters:

- the auth key is one-off
- the auth key is not pre-approved
- the joining machine still requires manual approval before it can retrieve final secrets
- ACLs limit `tag:bootstrap` to the secret API only

### Secret API abuse

If the secret API trusted only the JSON body, a hostile bootstrap node could ask for another node's secrets.

Mitigations:

- require trusted identity headers from a Tailscale-connected ingress
- match the trusted node identity to the provisioning record
- reject mismatched `hostname`, `instance_id`, or `node_id`

## Residual risks

- A stolen seed token plus fast use before operator approval still yields the bootstrap script and one-time key.
- The bootstrap VM itself can leak the auth key locally if the guest is already compromised before first boot.
- Tailscale identity headers are only trustworthy if the secret API is deployed behind a trusted Tailscale-facing proxy or tsnet listener.

## Additional mitigations

- prefer HTTPS on the NoCloud endpoint when practical
- keep auth key expiry very short
- monitor for stale bootstrap devices in Tailscale
- rotate downstream secrets if a bootstrap record is suspected to be exposed
- keep the bootstrap ACL surface minimal
