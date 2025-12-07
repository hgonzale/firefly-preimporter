"""Uploader helpers for sending payloads to FiDI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:  # pragma: no cover
    from firefly_preimporter.config import FireflySettings


def _verify_option(settings: FireflySettings) -> bool | str:
    if settings.ca_cert_path and settings.ca_cert_path.exists():
        return str(settings.ca_cert_path)
    return True


class FidiUploader:
    """Upload CSV/JSON payloads to the FiDI auto-upload endpoint."""

    def __init__(
        self,
        settings: FireflySettings,
        *,
        session: requests.Session | None = None,
        dry_run: bool = False,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.dry_run = dry_run

    def upload(self, csv_payload: str, json_config: dict[str, object]) -> requests.Response:
        """Post the payloads to FiDI and return the response (or a dummy response in dry-run)."""

        files = {
            'importable': ('transactions.csv', csv_payload.encode('utf-8'), 'text/csv'),
            'json': ('config.json', json.dumps(json_config).encode('utf-8'), 'application/json'),
        }
        data = {'secret': self.settings.fidi_import_secret}
        headers = {
            'Authorization': f'Bearer {self.settings.personal_access_token}',
            'Accept': 'application/json',
        }
        if self.dry_run:
            response = requests.Response()
            response.status_code = 200
            return response

        response = self.session.post(
            self.settings.fidi_autoupload_url,
            headers=headers,
            data=data,
            files=files,
            timeout=self.settings.request_timeout,
            verify=_verify_option(self.settings),
        )
        response.raise_for_status()
        return response
