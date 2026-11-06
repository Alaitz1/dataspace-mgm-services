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

import copy
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from .models import AuditLogRecord, RoleAssignmentLogRecord, TechnicalUserRecord


class TechnicalUserRepository(Protocol):
    """Persistence contract of C2-M3: rows are values, so change a row and then `save` it."""

    def reset(self) -> None: ...

    def locked(self, key: str) -> AbstractContextManager[None]: ...

    def transaction(self) -> AbstractContextManager[None]: ...

    def next_client_id(self, prefix: str) -> str: ...

    def save(self, row: TechnicalUserRecord) -> None: ...

    def remove(self, user_id: str) -> None: ...

    def get(self, user_id: str) -> TechnicalUserRecord | None: ...

    def find(self, *, owner_company_id: str | None = None, visible_to: str | None = None,
             statuses: tuple[str, ...] | list[str] | None = None, origin: str | None = None,
             wallet_access: str | None = None, disabled: bool | None = None,
             offer_subscription_id: str | None = None) -> list[TechnicalUserRecord]: ...

    def find_subscription(self, subscription_id: str, party: str) -> TechnicalUserRecord | None: ...

    def add_audit_entry(self, entry: AuditLogRecord) -> None: ...

    def add_role_assignment_entry(self, entry: RoleAssignmentLogRecord) -> None: ...

    def audit_entries(self) -> list[AuditLogRecord]: ...

    def role_assignment_entries(self) -> list[RoleAssignmentLogRecord]: ...


class InMemoryTechnicalUserRepository:
    """Hackathon implementation; it hands out copies so that a missing `save` shows up in tests."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: dict[str, TechnicalUserRecord] = {}
        self._audit: list[AuditLogRecord] = []
        self._role_log: list[RoleAssignmentLogRecord] = []
        self._client_number = 0

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._audit.clear()
            self._role_log.clear()
            self._client_number = 0

    @contextmanager
    def locked(self, key: str) -> Iterator[None]:
        with self._lock:
            yield

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            users, audit, role_log = copy.deepcopy(self._users), list(self._audit), list(self._role_log)
            try:
                yield
            except BaseException:
                self._users = users
                self._audit[:], self._role_log[:] = audit, role_log
                raise

    def next_client_id(self, prefix: str) -> str:
        with self._lock:
            self._client_number += 1
            return f"{prefix}{self._client_number}"

    def save(self, row: TechnicalUserRecord) -> None:
        with self._lock:
            self._users[row["id"]] = copy.deepcopy(row)

    def remove(self, user_id: str) -> None:
        with self._lock:
            self._users.pop(user_id, None)

    def get(self, user_id: str) -> TechnicalUserRecord | None:
        with self._lock:
            row = self._users.get(user_id)
            return copy.deepcopy(row) if row else None

    def find(self, *, owner_company_id: str | None = None, visible_to: str | None = None,
             statuses: tuple[str, ...] | list[str] | None = None, origin: str | None = None,
             wallet_access: str | None = None, disabled: bool | None = None,
             offer_subscription_id: str | None = None) -> list[TechnicalUserRecord]:
        with self._lock:
            return [copy.deepcopy(row) for row in self._users.values()
                    if (owner_company_id is None or row["company_id"] == owner_company_id)
                    and (visible_to is None or visible_to in (row["company_id"], row["co_viewer_company_id"]))
                    and (statuses is None or row["status"] in statuses)
                    and (not origin or row["origin"] == origin)
                    and (not wallet_access or row["wallet_access"] == wallet_access)
                    and (disabled is None or row["disabled"] is disabled)
                    and (offer_subscription_id is None or row["offer_subscription_id"] == offer_subscription_id)]

    def find_subscription(self, subscription_id: str, party: str) -> TechnicalUserRecord | None:
        return next((row for row in self.find(offer_subscription_id=subscription_id)
                     if row["subscription_party"] == party and row["status"] != "DELETED"), None)

    def add_audit_entry(self, entry: AuditLogRecord) -> None:
        with self._lock:
            self._audit.append(entry)

    def add_role_assignment_entry(self, entry: RoleAssignmentLogRecord) -> None:
        with self._lock:
            self._role_log.append(entry)

    def audit_entries(self) -> list[AuditLogRecord]:
        with self._lock:
            return list(self._audit)

    def role_assignment_entries(self) -> list[RoleAssignmentLogRecord]:
        with self._lock:
            return list(self._role_log)


repository: TechnicalUserRepository = InMemoryTechnicalUserRepository()