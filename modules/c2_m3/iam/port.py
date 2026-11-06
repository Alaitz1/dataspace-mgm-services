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
"""What C2-M3 needs from the Portal IAM of the OSP (README 6.6 and 11.1)."""
from __future__ import annotations

from typing import Protocol


class IamError(RuntimeError):
    """The Portal IAM did not answer as expected (public error `iam-error`, 502)."""


class IamNotFound(IamError):
    """The Portal IAM answered 404 for an object the adapter knew (a cached ID may be stale)."""


class IamConflict(IamError):
    """The client exists but belongs to another account: it is never adopted, changed or deleted."""


class UnknownRole(ValueError):
    """A role is not on the client `TECHNICAL_ROLES_CLIENT` (public error `role-not-assignable`, 400)."""


class TechnicalUserIam(Protocol):
    def list_roles(self, lang: str | None = None) -> list[dict]:
        """Roles of the technical roles client: `name` and `description` in `lang`."""

    def ensure_roles(self, roles: list[str]) -> None:
        """Raises `UnknownRole` if one of the roles does not exist."""

    def client(self, client_id: str) -> dict | None:
        """The client with this client ID, whoever it belongs to, or None if the ID is free."""

    def create_or_complete(self, client_id: str, *, owner_id: str, name: str, description: str | None,
                           company_id: str, bpn: str, roles: list[str], enabled: bool = True) -> dict:
        """Creates the client for the account `owner_id` if it is missing and completes attributes and roles; the
        result has `id` (internal ID) and `serviceAccountUserId`. A client of another account (or without owner)
        raises `IamConflict`: its secret and company are never taken over."""

    def roles_for(self, client_id: str) -> list[str]: ...

    def set_roles(self, client_id: str, roles: list[str]) -> tuple[list[str], list[str]]:
        """Makes `roles` the complete list; returns the added and the removed roles."""

    def update_client(self, client_id: str, *, name: str, description: str | None) -> None: ...

    def set_enabled(self, client_id: str, enabled: bool) -> None: ...

    def secret(self, client_id: str) -> str: ...

    def rotate_secret(self, client_id: str) -> str: ...

    def delete(self, client_id: str, *, owner_id: str) -> None:
        """A client that is already gone counts as deleted; one of another account raises `IamConflict`."""
