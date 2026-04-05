#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.models import Base, ProvisioningRecord, ProvisioningState  # noqa: E402
from shared.util import ensure_utc, utc_now  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expire stale bootstrap provisioning records.")
    parser.add_argument(
        "--database-url",
        default="sqlite:///./data/provisioning.db",
        help="SQLAlchemy database URL for the provisioning record store.",
    )
    parser.add_argument(
        "--abandoned-key-minutes",
        type=int,
        default=30,
        help="Clear bootstrap auth keys that have been abandoned longer than this.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    now = utc_now()
    abandoned_deadline = now - timedelta(minutes=args.abandoned_key_minutes)
    connect_args = {"check_same_thread": False} if args.database_url.startswith("sqlite") else {}
    engine = create_engine(args.database_url, future=True, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)

    expired = 0
    cleared = 0
    with Session(engine) as session:
        records = session.execute(select(ProvisioningRecord)).scalars().all()
        for record in records:
            if record.is_expired(now):
                previous_state = record.state
                record.state = ProvisioningState.EXPIRED.value
                if previous_state != ProvisioningState.SECRETS_DELIVERED.value:
                    record.tailscale_auth_key = None
                    record.tailscale_auth_key_created_at = None
                    record.tailscale_auth_key_expires_at = None
                    cleared += 1
                expired += 1
                session.add(record)
                continue

            if (
                record.tailscale_auth_key
                and record.tailscale_auth_key_created_at
                and ensure_utc(record.tailscale_auth_key_created_at) <= abandoned_deadline
                and not record.approved
                and record.state in {ProvisioningState.USER_DATA_ISSUED.value, ProvisioningState.WAITING_FOR_APPROVAL.value}
            ):
                record.tailscale_auth_key = None
                record.tailscale_auth_key_created_at = None
                record.tailscale_auth_key_expires_at = None
                record.state = ProvisioningState.CREATED.value
                cleared += 1
                session.add(record)

        session.commit()

    print(f"expired_records={expired}")
    print(f"cleared_auth_keys={cleared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
