"""Domain profile loader.

A *domain profile* bundles the Datasource-specific knowledge the engine needs:
the Thai-term hints injected into the prompt and the few-shot Example set. It is
selected by ``settings.DOMAIN_PROFILE`` and lives under ``profiles/<name>/``.
"""

import os
import logging

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(_ROOT, "profiles")


def profile_dir(profile: str) -> str:
    return os.path.join(PROFILES_DIR, profile)


def examples_path(profile: str) -> str:
    """Path to the profile's Example set (few-shot corpus)."""
    return os.path.join(profile_dir(profile), "examples.json")


def load_hints(profile: str) -> str:
    """The prompt hints block for this profile. Empty string if the file is absent."""
    path = os.path.join(profile_dir(profile), "hints.md")
    if not os.path.exists(path):
        logger.warning("Profile hints not found: %s", path)
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()
