from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

SENSITIVE_FIELD_NAMES = {
    "authorization",
    "authkey",
    "auth_key",
    "bootstrap_env_json",
    "bootstrap_files_json",
    "client_secret",
    "content",
    "env",
    "file_content",
    "files",
    "key",
    "oauth_secret",
    "secret",
    "secret_payload",
    "tailscale_auth_key",
    "token",
    "ts_api_client_secret",
}

STANDARD_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)[:length]


_WORD_LIST = [
    "amber", "anchor", "anvil", "apple", "arch", "arrow", "atlas", "autumn",
    "axle", "azure", "badge", "basin", "beam", "birch", "blade", "blaze",
    "bloom", "brace", "brake", "branch", "brave", "briar", "brick", "bridge",
    "brook", "brush", "burst", "cable", "cairn", "canoe", "cargo", "cedar",
    "chain", "chalk", "chart", "chase", "chest", "cider", "cinch", "circa",
    "civic", "clamp", "clasp", "cliff", "cloak", "cloud", "clove", "coast",
    "comet", "coral", "crank", "creek", "crest", "crisp", "cross", "crown",
    "crush", "crust", "curve", "cycle", "delta", "depot", "depth", "derby",
    "digit", "diode", "disco", "ditch", "dixie", "dolmen", "drake", "drift",
    "drive", "drone", "drops", "dross", "dunes", "eagle", "earth", "edge",
    "elder", "emery", "ember", "epoch", "equip", "erode", "event", "exert",
    "fable", "fault", "feast", "fence", "ferry", "field", "fjord", "flame",
    "flask", "flint", "flood", "flora", "flume", "flute", "focal", "forge",
    "forte", "forum", "frame", "frank", "frond", "front", "frost", "fulcrum",
    "gamma", "gauge", "ghost", "glade", "glare", "glaze", "gleam", "globe",
    "gloom", "gloss", "gorge", "grace", "grade", "grain", "grand", "grant",
    "graph", "grasp", "gravel", "grove", "graze", "great", "green", "grid",
    "grind", "groan", "grout", "growl", "guild", "guise", "gulch", "haven",
    "hawk", "hazel", "hedge", "helix", "helm", "heron", "hinge", "holly",
    "horse", "hound", "hover", "hunch", "ingot", "inlet", "inset", "ionic",
    "ivory", "jaunt", "joust", "karst", "kelp", "kinetic", "knoll", "kraken",
    "lance", "larch", "laser", "latch", "lava", "layer", "ledge", "lemon",
    "level", "light", "limit", "linen", "links", "locket", "lodge", "lofty",
    "logic", "lumen", "lunar", "lustre", "magma", "maple", "march", "marsh",
    "mast", "match", "mauve", "meander", "merge", "merit", "metal", "metro",
    "might", "mirth", "mocha", "model", "moose", "morse", "mossy", "mount",
    "mural", "musket", "nadir", "nexus", "nickel", "noble", "notch", "nymph",
    "oaken", "octet", "olive", "onyx", "optic", "orbit", "order", "outer",
    "oxide", "ozone", "pagoda", "parch", "parse", "patch", "pause", "petal",
    "pilot", "pinch", "pixel", "pivot", "plank", "plaza", "plume", "plunge",
    "polar", "porch", "prism", "probe", "proxy", "pulse", "quartz", "quest",
    "queue", "quick", "quota", "rabbet", "radial", "radio", "rally", "ramp",
    "rapid", "reach", "realm", "resin", "ridge", "rivet", "robin", "rocky",
    "roman", "roost", "rotor", "rouge", "rover", "rowel", "rudder", "runic",
    "sabre", "saddle", "salon", "salve", "sandy", "scarp", "screw", "seam",
    "serge", "servo", "shade", "shaft", "shale", "shelf", "shell", "shift",
    "shore", "siege", "sigma", "skiff", "slate", "sleek", "sleet", "slick",
    "slope", "sloth", "smart", "smoke", "solar", "solid", "solve", "sonic",
    "spool", "spore", "spray", "stack", "stave", "steam", "steel", "steep",
    "steer", "stern", "stone", "stork", "storm", "stout", "strap", "stray",
    "stream", "strut", "surge", "swamp", "swath", "sweep", "swift", "synod",
    "talon", "taupe", "thorn", "thyme", "tidal", "tilde", "timber", "titan",
    "token", "topaz", "torch", "tower", "track", "trail", "train", "trait",
    "tramp", "trench", "trial", "trout", "trove", "truce", "trunk", "trust",
    "tudor", "tuned", "tundra", "tunic", "turbo", "ultra", "umbra", "unity",
    "uplift", "valve", "vault", "venom", "verge", "viaduct", "vigor", "viola",
    "viral", "visor", "vista", "vortex", "wagon", "waltz", "watch", "water",
    "wedge", "wheat", "wheel", "whirl", "winds", "winch", "wraith", "wrench",
    "yield", "yonder", "zenith", "zonal",
]


def generate_word_token(num_words: int = 4) -> str:
    return "-".join(secrets.choice(_WORD_LIST) for _ in range(num_words))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return isoformat_z(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return str(value)


def redact_structure(value: Any, key_name: str | None = None) -> Any:
    lowered_key = key_name.lower() if key_name else None
    if lowered_key and lowered_key in SENSITIVE_FIELD_NAMES:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {key: redact_structure(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_structure(item, key_name) for item in value]
    if isinstance(value, tuple):
        return [redact_structure(item, key_name) for item in value]
    return value


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_RECORD_KEYS and not key.startswith("_")
        }
        record.redacted_message = redact_structure(record.msg)
        record.redacted_extras = redact_structure(extras)
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        message = getattr(record, "redacted_message", record.getMessage())
        if isinstance(message, dict):
            rendered_message = json.dumps(message, default=_json_default, sort_keys=True)
        else:
            rendered_message = str(message)

        payload: dict[str, Any] = {
            "timestamp": isoformat_z(datetime.fromtimestamp(record.created, tz=timezone.utc)),
            "service": self.service_name,
            "logger": record.name,
            "level": record.levelname.lower(),
            "message": rendered_message,
        }
        payload.update(getattr(record, "redacted_extras", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_json_default, separators=(",", ":"))


def configure_json_logging(service_name: str, level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(JsonFormatter(service_name=service_name))
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())
