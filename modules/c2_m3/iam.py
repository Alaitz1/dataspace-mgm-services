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
#  The software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
#  CONDITIONS OF ANY KIND, either express or implied. See the License for the
#  specific language governing permissions and limitations under the License.
#
#  AI Disclosure: This file was entirely AI-generated.
#  The AI-generated portions are made available under CC0-1.0 and not subject
#  to the project's license. The human contributor has reviewed and verified
#  that the code is correct.
#
#  SPDX-License-Identifier: Apache-2.0 AND CC0-1.0
#  Assisted-By: GitHub Copilot (GPT-5.1)
#################################################################################
from __future__ import annotations

import os
import secrets
import threading
import uuid
from urllib.parse import quote

from portal_common import http, tokens
from tools import iam_backend

_CLIENT_NOT_FOUND = "technical user client was not found"


class IAMError(RuntimeError):
    pass


class MemoryIAM:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.technical_roles = set(iam_backend.backend("c2-m3").technical_roles)
        self.clients: dict[str, dict] = {}

    def list_roles(self, _lang: str | None = None) -> list[dict]:
        return [{"name": name, "description": None} for name in sorted(self.technical_roles)]

    def ensure_roles(self, roles: list[str]) -> None:
        unknown = set(roles) - self.technical_roles
        if unknown:
            raise ValueError(f"unknown technical user roles {sorted(unknown)}")

    def client(self, client_id: str) -> dict | None:
        return self.clients.get(client_id)

    def create_or_complete(self, client_id: str, *, name: str, description: str | None,
                           company_id: str, bpn: str, roles: list[str], enabled: bool = True) -> dict:
        self.ensure_roles(roles)
        with self.lock:
            client = self.clients.get(client_id)
            if client is None:
                client = {"id": str(uuid.uuid4()), "clientId": client_id, "secret": secrets.token_urlsafe(24),
                          "serviceAccountUserId": str(uuid.uuid4()), "name": name, "description": description,
                          "companyId": company_id, "bpn": bpn, "roles": set(), "enabled": enabled}
                self.clients[client_id] = client
            client.update(name=name, description=description, companyId=company_id, bpn=bpn, enabled=enabled)
            client["roles"].update(roles)
            return dict(client)

    def roles_for(self, client_id: str) -> list[str]:
        client = self.client(client_id)
        return sorted(client["roles"]) if client else []

    def set_roles(self, client_id: str, roles: list[str]) -> tuple[list[str], list[str]]:
        self.ensure_roles(roles)
        with self.lock:
            client = self.clients[client_id]
            old = set(client["roles"])
            new = set(roles)
            client["roles"] = new
            return sorted(new - old), sorted(old - new)

    def update_client(self, client_id: str, *, name: str, description: str | None) -> None:
        self.clients[client_id].update(name=name, description=description)

    def set_enabled(self, client_id: str, enabled: bool) -> None:
        if client := self.client(client_id):
            client["enabled"] = enabled

    def secret(self, client_id: str) -> str:
        return self.clients[client_id]["secret"]

    def rotate_secret(self, client_id: str) -> str:
        with self.lock:
            self.clients[client_id]["secret"] = secrets.token_urlsafe(24)
            return self.clients[client_id]["secret"]

    def delete(self, client_id: str) -> None:
        with self.lock:
            self.clients.pop(client_id, None)


class KeycloakIAM:
    def __init__(self) -> None:
        self.base_url = f"{tokens.iam_url()}/admin/realms/{tokens.realm()}"
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        client_id = os.environ.get("C2_M3_CLIENT_ID", "svc-c2-m3")
        client_secret = os.environ.get("C2_M3_CLIENT_SECRET")
        if not client_secret:
            raise IAMError("C2_M3_CLIENT_SECRET is not configured")
        response = http.request("POST", tokens.token_endpoint(), data={
            "grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret,
        })
        if response.status_code != 200:
            raise IAMError(f"Portal IAM token endpoint answered {response.status_code}")
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _call(self, method: str, path: str, **kwargs):
        response = http.request(method, self.base_url + path,
                                headers={"Authorization": f"Bearer {self._token()}"}, **kwargs)
        if response.status_code == 401:
            self._access_token = None
            response = http.request(method, self.base_url + path,
                                    headers={"Authorization": f"Bearer {self._token()}"}, **kwargs)
        if not response.is_success:
            raise IAMError(f"Portal IAM answered {response.status_code} for {method} {path}")
        return response

    def _find_client(self, client_id: str) -> dict | None:
        response = self._call("GET", "/clients", params={"clientId": client_id})
        clients = response.json()
        return clients[0] if clients else None

    def _client(self, client_id: str) -> dict | None:
        return self._find_client(client_id)

    def _roles_client_id(self) -> str:
        configured = os.environ.get("TECHNICAL_ROLES_CLIENT", "technical_roles_management")
        client = self._find_client(configured)
        if not client:
            raise IAMError("technical roles client was not found")
        return client["id"]

    def _service_account(self, client_uuid: str) -> dict:
        return self._call("GET", f"/clients/{client_uuid}/service-account-user").json()

    def _user(self, user_id: str) -> dict:
        return self._call("GET", f"/users/{user_id}").json()

    def list_roles(self, lang: str | None = None) -> list[dict]:
        response = self._call("GET", f"/clients/{self._roles_client_id()}/roles",
                              params={"briefRepresentation": "false"})
        description_key = f"description.{lang or 'de'}"
        result = []
        for role in response.json():
            attrs = role.get("attributes") or {}
            localized = attrs.get(description_key)
            result.append({"name": role["name"],
                           "description": (localized[0] if isinstance(localized, list) and localized else None)
                           or role.get("description")})
        return sorted(result, key=lambda role: role["name"])

    def ensure_roles(self, roles: list[str]) -> None:
        available = {role["name"] for role in self.list_roles()}
        unknown = set(roles) - available
        if unknown:
            raise ValueError(f"unknown technical user roles {sorted(unknown)}")

    def client(self, client_id: str) -> dict | None:
        return self._client(client_id)

    def create_or_complete(self, client_id: str, *, name: str, description: str | None,
                           company_id: str, bpn: str, roles: list[str], enabled: bool = True) -> dict:
        self.ensure_roles(roles)
        found = self._client(client_id)
        if not found:
            scopes = [scope.strip() for scope in os.environ.get(
                "TECHNICAL_USER_CLIENT_DEFAULT_SCOPES", "basic,roles,catena,technical-roles").split(",")
                      if scope.strip()]
            representation = {
                "clientId": client_id, "name": name, "description": description, "enabled": enabled,
                "protocol": "openid-connect", "publicClient": False, "clientAuthenticatorType": "client-secret",
                "serviceAccountsEnabled": True, "standardFlowEnabled": False, "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
                "defaultClientScopes": scopes, "optionalClientScopes": [],
            }
            response = http.request("POST", f"{self.base_url}/clients", json=representation,
                                    headers={"Authorization": f"Bearer {self._token()}"})
            if response.status_code not in (201, 409):
                raise IAMError(f"Portal IAM answered {response.status_code} creating a client")
            found = self._client(client_id)
            if not found:
                raise IAMError("Portal IAM did not return the created client")
        client_uuid = found["id"]
        user = self._service_account(client_uuid)
        attributes = user.get("attributes") or {}
        attributes[os.environ.get("COMPANY_ID_ATTRIBUTE", "company_id")] = [company_id]
        attributes[os.environ.get("BPN_ATTRIBUTE", "bpn")] = [bpn]
        user["attributes"] = attributes
        self._call("PUT", f"/users/{user['id']}", json=user)
        current = set(self.roles_for(client_id))
        role_client = self._roles_client_id()
        missing = set(roles) - current
        if missing:
            reps = [self._call("GET", f"/clients/{role_client}/roles/{quote(role, safe='')}").json()
                    for role in sorted(missing)]
            self._call("POST", f"/users/{user['id']}/role-mappings/clients/{role_client}", json=reps)
        latest = self._client(client_id)
        if latest and latest.get("enabled") != enabled:
            latest["enabled"] = enabled
            self._call("PUT", f"/clients/{client_uuid}", json=latest)
        return {"id": client_uuid, "clientId": client_id, "serviceAccountUserId": user["id"],
                "name": name, "description": description, "enabled": enabled}

    def roles_for(self, client_id: str) -> list[str]:
        client = self._client(client_id)
        if not client:
            return []
        user = self._service_account(client["id"])
        role_client = self._roles_client_id()
        roles = self._call("GET", f"/users/{user['id']}/role-mappings/clients/{role_client}").json()
        return sorted(role["name"] for role in roles)

    def set_roles(self, client_id: str, roles: list[str]) -> tuple[list[str], list[str]]:
        self.ensure_roles(roles)
        client = self._client(client_id)
        if not client:
            raise IAMError(_CLIENT_NOT_FOUND)
        user = self._service_account(client["id"])
        role_client = self._roles_client_id()
        current = {role["name"]: role for role in self._call(
            "GET", f"/users/{user['id']}/role-mappings/clients/{role_client}").json()}
        target = set(roles)
        add = target - set(current)
        remove = set(current) - target
        if add:
            reps = [self._call("GET", f"/clients/{role_client}/roles/{quote(role, safe='')}").json()
                    for role in sorted(add)]
            self._call("POST", f"/users/{user['id']}/role-mappings/clients/{role_client}", json=reps)
        if remove:
            self._call("DELETE", f"/users/{user['id']}/role-mappings/clients/{role_client}",
                       json=[current[name] for name in sorted(remove)])
        return sorted(add), sorted(remove)

    def update_client(self, client_id: str, *, name: str, description: str | None) -> None:
        client = self._client(client_id)
        if not client:
            raise IAMError(_CLIENT_NOT_FOUND)
        client.update(name=name, description=description)
        self._call("PUT", f"/clients/{client['id']}", json=client)

    def set_enabled(self, client_id: str, enabled: bool) -> None:
        client = self._client(client_id)
        if client and client.get("enabled") != enabled:
            client["enabled"] = enabled
            self._call("PUT", f"/clients/{client['id']}", json=client)

    def secret(self, client_id: str) -> str:
        client = self._client(client_id)
        if not client:
            raise IAMError(_CLIENT_NOT_FOUND)
        value = self._call("GET", f"/clients/{client['id']}/client-secret").json().get("value")
        if not value:
            raise IAMError("Portal IAM returned no client secret")
        return value

    def rotate_secret(self, client_id: str) -> str:
        client = self._client(client_id)
        if not client:
            raise IAMError(_CLIENT_NOT_FOUND)
        value = self._call("POST", f"/clients/{client['id']}/client-secret").json().get("value")
        if not value:
            raise IAMError("Portal IAM returned no client secret")
        return value

    def delete(self, client_id: str) -> None:
        client = self._client(client_id)
        if client:
            self._call("DELETE", f"/clients/{client['id']}")


_memory: MemoryIAM | None = None
_keycloak: KeycloakIAM | None = None


def get() -> MemoryIAM | KeycloakIAM:
    global _memory, _keycloak
    if os.environ.get("IAM_URL"):
        if _keycloak is None:
            _keycloak = KeycloakIAM()
        return _keycloak
    if _memory is None:
        _memory = MemoryIAM()
    return _memory


def reset() -> None:
    global _memory, _keycloak
    _memory = None
    _keycloak = None