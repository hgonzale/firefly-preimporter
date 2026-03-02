"""Shared utility functions for Firefly Preimporter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from firefly_preimporter.config import FireflyPreimporterSettings

LOGGER = logging.getLogger(__name__)


def get_verify_option(settings: FireflyPreimporterSettings) -> bool | str:
    """Return the appropriate 'verify' parameter for requests library.

    Args:
        settings: Firefly settings containing optional CA certificate path.

    Returns:
        Path to CA certificate if configured and exists, otherwise True (use default verification).

    Note:
        If ca_cert_path is configured but the file doesn't exist, logs a warning
        and falls back to default verification. This is optional functionality,
        so we don't raise an error.
    """
    if settings.common.ca_cert_path:
        if settings.common.ca_cert_path.exists():
            return str(settings.common.ca_cert_path)
        LOGGER.warning(
            'CA certificate path configured but file not found: %s. Using default certificate verification.',
            settings.common.ca_cert_path,
        )
    return True
