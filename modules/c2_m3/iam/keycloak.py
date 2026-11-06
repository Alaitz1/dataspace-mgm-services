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
"""Keycloak Admin REST API of the Portal IAM (README 6.6 and 11.1), with the module's service account."""
from __future__ import annotations

import os
import threading
import time
from urllib.parse import quote

import httpx

from portal_common import http, tokens

from .port import IamError, UnknownRole


class KeycloakIAM:
    def __init__(self) -> None:
        self.base_url = f"{tokens.iam_url()}/admin/realms/{tokens.realm()}"
        self._lock = threading.Lock()
        self._token: tuple[str, float] | None = None
        self._client_uuids: dict[str, str] = {}
        self._service_accounts: dict[str, str] = {}
        self._roles_client_uuid: str | None = None

    # -- transport -------------------------------------------------------------------------
    def _access_token(self, *, fresh: bool = False) -> str:
        with self._lock:
            if not fresh and self._token and self._token[1] > time.time() + 30:
                return self._token[0]
        secret = (os.environ.get("C2_M3_CLIENT_SECRET") or os.environ.get("SERVICE_CLIENT_SECRET")
                  or tokens.DEFAULT_SERVICE_SECRET)   # the default is the test installation's secret
        response = http.request("POST", tokens.token_endpoint(), data={
            "grant_type": "client_credentials",
            "client_id": os.environ.get("C2_M3_CLIENT_ID", "svc-c2-m3"), "client_secret": secret})
        if response.status_code != 200:
            raise IamError(f"Portal IAM token endpoint answered {response.status_code}")
        body = response.json()
        with self._lock:
            self._token = (body["access_token"], time.time() + int(body.get("expires_in", 60)))
        return body["access_token"]

    def _call(self, method: str, path: str, *, accept: tuple[int, ...] = (), **kwargs) -> httpx.Response:
        def send(fresh: bool) -> httpx.Response:
            return http.request(method, self.base_url + path,
                                headers={"Authorization": f"Bearer {self._access_token(fresh=fresh)}"}, **kwargs)
        response = send(False)
        if response.status_code == 401:
            response = send(True)
        if not response.is_success and response.status_code not in accept:
            raise IamError(f"Portal IAM answered {response.status_code} for {method} {path}")
        return response

    # -- lookups ---------------------------------------------------------------------------
    def _find_client(self, client_id: str) -> dict | None:
        found = self._call("GET", "/clients", params={"clientId": client_id}).json()
        if found:
            self._client_uuids[client_id] = found[0]["id"]
        return found[0] if found else None

    def _client_uuid(self, client_id: str) -> str | None:
        if client_id in self._client_uuids:
            return self._client_uuids[client_id]
        client = self._find_client(client_id)
        return client["id"] if client else None

    def _require_uuid(self, client_id: str) -> str:
        client_uuid = self._client_uuid(client_id)
        if client_uuid is None:
            raise IamError(f"client {client_id} was not found")
        return client_uuid

    def _roles_client(self) -> str:
        if self._roles_client_uuid is None:
            name = os.environ.get("TECHNICAL_ROLES_CLIENT", "technical_roles_management")
            client = self._find_client(name)
            if client is None:
                raise IamError("technical roles client was not found")
            self._roles_client_uuid = client["id"]
        return self._roles_client_uuid

    def _service_account(self, client_uuid: str) -> str:
        if client_uuid not in self._service_accounts:
            user = self._call("GET", f"/clients/{client_uuid}/service-account-user").json()
            self._service_accounts[client_uuid] = user["id"]
        return self._service_accounts[client_uuid]

    def _mapped_roles(self, user_id: str) -> list[dict]:
        return self._call("GET", f"/users/{user_id}/role-mappings/clients/{self._roles_client()}").json()

    def _role_representations(self, names: list[str]) -> list[dict]:
        client = self._roles_client()
        return [self._call("GET", f"/clients/{client}/roles/{quote(name, safe='')}").json() for name in sorted(names)]

    # -- roles -----------------------------------------------------------------------------
    def list_roles(self, lang: str | None = None) -> list[dict]:
        response = self._call("GET", f"/clients/{self._roles_client()}/roles",
                              params={"briefRepresentation": "false", "max": 1000})
        key = f"description.{lang or 'de'}"
        result = []
        for role in response.json():
            localized = (role.get("attributes") or {}).get(key)
            result.append({"name": role["name"],
                           "description": (localized[0] if localized else None) or role.get("description")})
        return sorted(result, key=lambda role: role["name"])

    def ensure_roles(self, roles: list[str]) -> None:
        unknown = set(roles) - {role["name"] for role in self.list_roles()}
        if unknown:
            raise UnknownRole(f"unknown technical user roles {sorted(unknown)}")

    def roles_for(self, client_id: str) -> list[str]:
        client_uuid = self._client_uuid(client_id)
        if client_uuid is None:
            return []
        return sorted(role["name"] for role in self._mapped_roles(self._service_account(client_uuid)))

    def set_roles(self, client_id: str, roles: list[str]) -> tuple[list[str], list[str]]:
        self.ensure_roles(roles)
        user_id = self._service_account(self._require_uuid(client_id))
        current = {role["name"]: role for role in self._mapped_roles(user_id)}
        add, remove = set(roles) - set(current), set(current) - set(roles)
        if add:
            self._call("POST", f"/users/{user_id}/role-mappings/clients/{self._roles_client()}",
                       json=self._role_representations(list(add)))
        if remove:
            self._call("DELETE", f"/users/{user_id}/role-mappings/clients/{self._roles_client()}",
                       json=[current[name] for name in sorted(remove)])
        return sorted(add), sorted(remove)

    # -- client ----------------------------------------------------------------------------
    def client(self, client_id: str) -> dict | None:
        return self._find_client(client_id)

    def _create_client(self, client_id: str, name: str, description: str | None, enabled: bool) -> None:
        scopes = [scope.strip() for scope in os.environ.get(
            "TECHNICAL_USER_CLIENT_DEFAULT_SCOPES", "basic,roles,catena,technical-roles").split(",") if scope.strip()]
        self._call("POST", "/clients", accept=(409,), json={
            "clientId": client_id, "name": name, "description": description, "enabled": enabled,
            "protocol": "openid-connect", "publicClient": False, "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": True, "standardFlowEnabled": False, "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
            "defaultClientScopes": scopes, "optionalClientScopes": []})

    def _set_attributes(self, user_id: str, company_id: str, bpn: str) -> None:
        user = self._call("GET", f"/users/{user_id}").json()
        attributes = user.get("attributes") or {}
        wanted = {os.environ.get("COMPANY_ID_ATTRIBUTE", "company_id"): [company_id],
                  os.environ.get("BPN_ATTRIBUTE", "bpn"): [bpn]}
        if all(attributes.get(key) == value for key, value in wanted.items()):
            return
        user["attributes"] = attributes | wanted
        self._call("PUT", f"/users/{user_id}", json=user)

    def _set_enabled(self, client_uuid: str, enabled: bool) -> None:
        representation = self._call("GET", f"/clients/{client_uuid}").json()
        if representation.get("enabled") != enabled:
            self._call("PUT", f"/clients/{client_uuid}", json=representation | {"enabled": enabled})

    def create_or_complete(self, client_id: str, *, name: str, description: str | None, company_id: str,
                           bpn: str, roles: list[str], enabled: bool = True) -> dict:
        self.ensure_roles(roles)
        client_uuid = self._client_uuid(client_id)
        if client_uuid is None:
            self._create_client(client_id, name, description, enabled)
            client_uuid = self._require_uuid(client_id)
        user_id = self._service_account(client_uuid)
        self._set_attributes(user_id, company_id, bpn)
        missing = set(roles) - {role["name"] for role in self._mapped_roles(user_id)}
        if missing:
            self._call("POST", f"/users/{user_id}/role-mappings/clients/{self._roles_client()}",
                       json=self._role_representations(list(missing)))
        self._set_enabled(client_uuid, enabled)
        return {"id": client_uuid, "clientId": client_id, "serviceAccountUserId": user_id,
                "name": name, "description": description, "enabled": enabled}

    def update_client(self, client_id: str, *, name: str, description: str | None) -> None:
        client_uuid = self._require_uuid(client_id)
        representation = self._call("GET", f"/clients/{client_uuid}").json()
        self._call("PUT", f"/clients/{client_uuid}", json=representation | {"name": name, "description": description})

    def set_enabled(self, client_id: str, enabled: bool) -> None:
        client_uuid = self._client_uuid(client_id)
        if client_uuid is not None:
            self._set_enabled(client_uuid, enabled)

    def _secret_value(self, response: httpx.Response) -> str:
        value = response.json().get("value")
        if not value:
            raise IamError("Portal IAM returned no client secret")
        return value

    def secret(self, client_id: str) -> str:
        return self._secret_value(self._call("GET", f"/clients/{self._require_uuid(client_id)}/client-secret"))

    def rotate_secret(self, client_id: str) -> str:
        return self._secret_value(self._call("POST", f"/clients/{self._require_uuid(client_id)}/client-secret"))

    def delete(self, client_id: str) -> None:
        client_uuid = self._client_uuid(client_id)
        if client_uuid is None:
            return
        self._call("DELETE", f"/clients/{client_uuid}", accept=(404,))
        self._client_uuids.pop(client_id, None)
        self._service_accounts.pop(client_uuid, None)
