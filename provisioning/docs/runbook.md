# Runbook

## Create a node

```bash
uv run python scripts/create_node.py \
  --hostname vm-bootstrap-01 \
  --base-url http://127.0.0.1:8080 \
  --database-url sqlite:///./data/provisioning.db
```

Record the printed seed URL and `ds=nocloud` string.

## Boot a VM

Use either a cloud image or an installer workflow that supports NoCloud. For
local QEMU testing:

```bash
make vm IMAGE_PATH=/path/to/ubuntu-cloudimg.qcow2
```

## Approve the device in Tailscale

1. Wait for the new machine to appear with `tag:bootstrap`.
2. Manually approve the machine in the Tailscale admin console.
3. If you are using local development only, toggle the record manually:

```sql
UPDATE provisioning_records
SET approved = 1, state = 'approved'
WHERE node_id = '<node id>';
```

## Confirm secrets fetch

1. Check the VM logs:

```bash
sudo tail -f /var/log/bootstrap/bootstrap.log
```

2. Confirm the payload landed:

```bash
sudo ls -l /etc/bootstrap
sudo stat /etc/bootstrap/secrets.env
sudo stat /etc/bootstrap/config.json
```

3. Confirm the database state:

```sql
SELECT node_id, state, approved, user_data_rendered_at, secrets_retrieved_at
FROM provisioning_records;
```

Expected end state:

- `approved = 1`
- `state = secrets_delivered`
- `secrets_retrieved_at` populated

## Cleanup

1. Remove unused or expired records:

```bash
uv run python scripts/expire_stale_records.py --database-url sqlite:///./data/provisioning.db
```

2. Delete old machines from the Tailscale admin console if they are no longer needed.
3. Rotate any downstream secret material returned by `secret-api` if the machine is discarded.

## Troubleshooting

- `GET /seed/<token>/user-data` returns `410`: the seed record expired. Create a new one.
- The machine sits in `NeedsMachineAuth`: approve the device in Tailscale.
- `bootstrap.sh` keeps receiving `425`: the record exists, but approval is still false.
- `bootstrap.sh` receives `403`: either the caller lacked the bootstrap Serve capability, lacked `tag:bootstrap` in whois fallback, or the caller identity did not match the provisioning record.
- The machine cannot reach `secret-api`: verify the ACL policy allows `tag:bootstrap` to reach only `secret-api:443` and that the secret API is actually exposed on Tailscale.
