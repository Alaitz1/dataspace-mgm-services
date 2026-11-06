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
"""The in-memory Portal IAM of the installation (`tools/test_iam`) as the IAM of C2-M3.

The clients live in the installation's IAM, so the token endpoint of that IAM authenticates them: the credentials
that C2-M3 hands out work at the returned token URL. A disabled client keeps its secret but is refused.
Limit: the test IAM tells a technical user from a service account by its roles, so an account without any role
in the Portal IAM (a customer account that only has the wallet role) gets a token without roles."""
from __future__ import annotations

import secrets
import threading
import uuid

from tools import test_iam

from .port import IamConflict, IamError, UnknownRole


class MemoryIAM:
    def __init__(self) -> None:
        self.lock = threading.RLock()

    @property
    def _store(self) -> dict[str, dict]:
        return test_iam.iam().clients

    @property
    def technical_roles(self) -> set[str]:
        return test_iam.iam().technical_roles

    @property
    def clients(self) -> dict[str, dict]:
        """The technical user clients of this module (not the service accounts of the installation)."""
        return {client_id: client for client_id, client in self._store.items() if "owner" in client}

    def clear(self) -> None:
        with self.lock:
            for client_id in list(self.clients):
                del self._store[client_id]

    def _require(self, client_id: str) -> dict:
        client = self.clients.get(client_id)
        if client is None:
            raise IamError(f"client {client_id} was not found")
        return client

    @staticmethod
    def _apply_enabled(client: dict, enabled: bool) -> None:
        """A disabled client keeps its secret; without an active one the token endpoint refuses it."""
        client["enabled"] = enabled
        client["secret"] = client["_secret"] if enabled else None

    @staticmethod
    def _view(client: dict) -> dict:
        return {"id": client["id"], "clientId": client["clientId"], "enabled": client["enabled"],
                "owner": client.get("owner"), "roles": sorted(client["technicalRoles"])}

    def list_roles(self, lang: str | None = None) -> list[dict]:
        return [{"name": name, "description": None} for name in sorted(self.technical_roles)]

    def ensure_roles(self, roles: list[str]) -> None:
        unknown = set(roles) - self.technical_roles
        if unknown:
            raise UnknownRole(f"unknown technical user roles {sorted(unknown)}")

    def client(self, client_id: str) -> dict | None:
        with self.lock:
            found = self._store.get(client_id)
            if found is None:
                return None
            return self._view(found) if "owner" in found else {"id": client_id, "clientId": client_id, "owner": None}

    def create_or_complete(self, client_id: str, *, owner_id: str, name: str, description: str | None,
                           company_id: str, bpn: str, roles: list[str], enabled: bool = True) -> dict:
        self.ensure_roles(roles)
        with self.lock:
            client = self._store.get(client_id)
            if client is None:
                secret = secrets.token_urlsafe(24)
                client = {"id": str(uuid.uuid4()), "clientId": client_id, "owner": owner_id, "_secret": secret,
                          "secret": secret, "permissions": set(), "technicalRoles": set(),
                          "serviceAccountUserId": str(uuid.uuid4()), "enabled": True}
                self._store[client_id] = client
            elif client.get("owner") != owner_id:
                raise IamConflict(f"client {client_id} belongs to another account")
            client.update(name=name, description=description, companyId=company_id, bpn=bpn)
            client["technicalRoles"].update(roles)
            self._apply_enabled(client, enabled)
            return {"id": client["id"], "clientId": client_id, "serviceAccountUserId": client["serviceAccountUserId"],
                    "name": name, "description": description, "enabled": enabled}

    def roles_for(self, client_id: str) -> list[str]:
        client = self.clients.get(client_id)
        return sorted(client["technicalRoles"]) if client else []

    def set_roles(self, client_id: str, roles: list[str]) -> tuple[list[str], list[str]]:
        self.ensure_roles(roles)
        with self.lock:
            client = self._require(client_id)
            old, new = set(client["technicalRoles"]), set(roles)
            client["technicalRoles"].clear()
            client["technicalRoles"].update(new)
            return sorted(new - old), sorted(old - new)

    def update_client(self, client_id: str, *, name: str, description: str | None) -> None:
        self._require(client_id).update(name=name, description=description)

    def set_enabled(self, client_id: str, enabled: bool) -> None:
        with self.lock:
            if client := self.clients.get(client_id):
                self._apply_enabled(client, enabled)

    def secret(self, client_id: str) -> str:
        return self._require(client_id)["_secret"]

    def rotate_secret(self, client_id: str) -> str:
        with self.lock:
            client = self._require(client_id)
            client["_secret"] = secrets.token_urlsafe(24)
            self._apply_enabled(client, client["enabled"])
            return client["_secret"]

    def delete(self, client_id: str, *, owner_id: str) -> None:
        with self.lock:
            client = self._store.get(client_id)
            if client is None:
                return
            if client.get("owner") != owner_id:
                raise IamConflict(f"client {client_id} belongs to another account")
            del self._store[client_id]
