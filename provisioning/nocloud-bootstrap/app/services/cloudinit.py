from __future__ import annotations

from functools import lru_cache

from shared.models import ProvisioningRecord

from ..config import Settings, get_settings
from ..templates import build_template_environment


class CloudInitService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.environment = build_template_environment(settings.templates_dir)

    def render_meta_data(self, record: ProvisioningRecord) -> str:
        template = self.environment.get_template("meta-data.yaml.j2")
        return template.render(instance_id=record.instance_id, hostname=record.hostname).strip() + "\n"

    def render_user_data(self, record: ProvisioningRecord) -> str:
        template = self.environment.get_template("user-data.yaml.j2")
        return (
            template.render(
                hostname=record.hostname,
                instance_id=record.instance_id,
                node_id=record.node_id,
                tailscale_auth_key=record.tailscale_auth_key or "",
                advertise_tags_csv=",".join(record.tailscale_tags or [self.settings.bootstrap_tag]),
                ssh_import_id=self.settings.bootstrap_ssh_import_id.strip(),
                secret_api_url=self.settings.secret_api_url,
            ).strip()
            + "\n"
        )


@lru_cache(maxsize=1)
def get_cloudinit_service() -> CloudInitService:
    return CloudInitService(get_settings())
