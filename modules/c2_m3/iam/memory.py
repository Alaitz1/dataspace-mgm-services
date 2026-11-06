#################################################################################
#  Copyright (c) 2026 Contributors to the Eclipse Foundation
#
#  See the NOTICE file(s) distributed with this work for additional
#  information regarding copyright ownership.
#
#  This program and the accompanying materials are made available under the
#  terms of the Apache License, Version 2.0 which is available at
#  https://www.apache.org/licenses/LICENSE-2.0.
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.
#
#  AI Disclosure: This file was entirely AI-generated.
#  The AI-generated portions are made available under CC0-1.0 and not subject
#  to the project's license. The human contributor has reviewed and verified
#  that the code is correct.
#
#  SPDX-License-Identifier: Apache-2.0 AND CC0-1.0
#  Assisted-By: GitHub Copilot (Claude Sonnet 5.5)
#################################################################################
"""In-memory Portal IAM for runs without Keycloak (the roles are those of the scaffold's test IAM)."""
from __future__ import annotations

import secrets
import threading
import uuid

from tools import iam_backend

from .port import IamError, UnknownRole


class MemoryIAM:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.technical_roles = set(iam_backend.backend("c2-m3").technical_roles)
        self.clients: dict[str, dict] = {}

    def _require(self, client_id: str) -> dict:
        client = self.clients.get(client_id)
        if client is None:
            raise IamError(f"client {client_id} was not found")
        return client

    def list_roles(self, lang: str | None = None) -> list[dict]:
        return [{"name": name, "description": None} for name in sorted(self.technical_roles)]

    def ensure_roles(self, roles: list[str]) -> None:
        unknown = set(roles) - self.technical_roles
        if unknown:
            raise UnknownRole(f"unknown technical user roles {sorted(unknown)}")

    def client(self, client_id: str) -> dict | None:
        return self.clients.get(client_id)

    def create_or_complete(self, client_id: str, *, name: str, description: str | None, company_id: str,
                           bpn: str, roles: list[str], enabled: bool = True) -> dict:
        self.ensure_roles(roles)
        with self.lock:
            client = self.clients.get(client_id)
            if client is None:
                client = {"id": str(uuid.uuid4()), "clientId": client_id, "secret": secrets.token_urlsafe(24),
                          "serviceAccountUserId": str(uuid.uuid4()), "roles": set()}
                self.clients[client_id] = client
            client.update(name=name, description=description, companyId=company_id, bpn=bpn, enabled=enabled)
            client["roles"].update(roles)
            return dict(client)

    def roles_for(self, client_id: str) -> list[str]:
        client = self.clients.get(client_id)
        return sorted(client["roles"]) if client else []

    def set_roles(self, client_id: str, roles: list[str]) -> tuple[list[str], list[str]]:
        self.ensure_roles(roles)
        with self.lock:
            client = self._require(client_id)
            old, new = set(client["roles"]), set(roles)
            client["roles"] = new
            return sorted(new - old), sorted(old - new)

    def update_client(self, client_id: str, *, name: str, description: str | None) -> None:
        self._require(client_id).update(name=name, description=description)

    def set_enabled(self, client_id: str, enabled: bool) -> None:
        if client := self.clients.get(client_id):
            client["enabled"] = enabled

    def secret(self, client_id: str) -> str:
        return self._require(client_id)["secret"]

    def rotate_secret(self, client_id: str) -> str:
        with self.lock:
            client = self._require(client_id)
            client["secret"] = secrets.token_urlsafe(24)
            return client["secret"]

    def delete(self, client_id: str) -> None:
        with self.lock:
            self.clients.pop(client_id, None)
