#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.models import Base, ProvisioningRecord, ProvisioningState  # noqa: E402
from shared.util import generate_token, generate_word_token, utc_now  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a bootstrap provisioning record.")
    parser.add_argument("--hostname", required=True, help="Hostname to assign to the VM.")
    parser.add_argument("--node-id", default=None, help="Stable bootstrap node identifier.")
    parser.add_argument("--instance-id", default=None, help="Cloud-init instance-id override.")
    parser.add_argument("--expiry-hours", type=int, default=24, help="Provisioning record TTL in hours.")
    parser.add_argument("--seed-token", default=None, help="Override the generated seed token.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="Public base URL for the NoCloud bootstrap service.",
    )
    parser.add_argument(
        "--database-url",
        default="sqlite:///./data/provisioning.db",
        help="SQLAlchemy database URL for the provisioning record store.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    node_id = args.node_id or generate_token(18)
    instance_id = args.instance_id or args.hostname
    seed_token = args.seed_token or generate_word_token()
    debug_password = generate_word_token(3)
    expires_at = utc_now() + timedelta(hours=args.expiry_hours)

    connect_args = {"check_same_thread": False} if args.database_url.startswith("sqlite") else {}
    engine = create_engine(args.database_url, future=True, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        record = ProvisioningRecord(
            node_id=node_id,
            seed_token=seed_token,
            debug_password=debug_password,
            instance_id=instance_id,
            hostname=args.hostname,
            tailscale_tags=["tag:bootstrap"],
            state=ProvisioningState.CREATED.value,
            expires_at=expires_at,
        )
        session.add(record)
        session.commit()

    base_url = args.base_url.rstrip("/")
    seed_root = f"{base_url}/seed/{seed_token}/"
    print(f"node_id={node_id}")
    print(f"seed_token={seed_token}")
    print(f"debug_user=debug")
    print(f"debug_password={debug_password}")
    print(f"seed_root={seed_root}")
    print(f"meta_data_url={seed_root}meta-data")
    print(f"user_data_url={seed_root}user-data")
    print(f"boot_arg=ds=nocloud;s={seed_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
