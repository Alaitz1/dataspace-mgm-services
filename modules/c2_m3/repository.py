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
import logging
import threading
import zlib
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from portal_common import events

from .models import AuditLogRecord, RoleAssignmentLogRecord, TechnicalUserRecord

log = logging.getLogger("portal.c2-m3")
LOCK_STRIPES = 64
Publisher = Callable[[str, dict], None]


def _publish(event_type: str, data: dict) -> None:
    events.publish("c2-m3", event_type, data)


class TechnicalUserRepository(Protocol):
    """Persistence contract of C2-M3: rows are values, so change a row and then `save` it.

    `locked(key)` serializes the work on one key (never nest two different keys). `transaction()` makes rows, logs
    and events (`add_event`) one unit: the events are published only after the outermost transaction committed,
    and a failed transaction drops them (README 4: outbox)."""

    def reset(self) -> None: ...

    def locked(self, key: str) -> AbstractContextManager[None]: ...

    def transaction(self) -> AbstractContextManager[None]: ...

    def add_event(self, event_type: str, data: dict) -> None: ...

    def flush_outbox(self) -> None: ...

    def unsent_events(self) -> list[tuple[str, dict]]: ...

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

    def __init__(self, publisher: Publisher = _publish) -> None:
        self._lock = threading.RLock()   # guards the data; never held while a caller does slow work
        self._key_locks = [threading.RLock() for _ in range(LOCK_STRIPES)]
        self._publisher = publisher
        self._depth = 0
        self._pending: list[tuple[str, dict]] = []   # events of the open transaction
        self._outbox: list[tuple[str, dict]] = []    # committed events that are not published yet
        self._users: dict[str, TechnicalUserRecord] = {}
        self._audit: list[AuditLogRecord] = []
        self._role_log: list[RoleAssignmentLogRecord] = []
        self._client_number = 0

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._audit.clear()
            self._role_log.clear()
            self._pending.clear()
            self._outbox.clear()
            self._client_number = 0

    @contextmanager
    def locked(self, key: str) -> Iterator[None]:
        with self._key_locks[zlib.crc32(key.encode()) % LOCK_STRIPES]:
            yield

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._depth += 1
            users, audit, role_log = copy.deepcopy(self._users), list(self._audit), list(self._role_log)
            pending = len(self._pending)
            try:
                yield
            except BaseException:
                self._users = users
                self._audit[:], self._role_log[:] = audit, role_log
                del self._pending[pending:]
                raise
            finally:
                self._depth -= 1
            outermost = self._depth == 0
            if outermost:
                self._outbox.extend(self._pending)
                self._pending.clear()
        if outermost:
            self.flush_outbox()

    def add_event(self, event_type: str, data: dict) -> None:
        with self._lock:
            if self._depth == 0:
                raise RuntimeError("an event is added inside the transaction of its change")
            self._pending.append((event_type, copy.deepcopy(data)))

    def flush_outbox(self) -> None:
        """Publishes the committed events in order; an event that fails for a temporary reason stays for the next try."""
        with self._lock:
            while self._outbox:
                event_type, data = self._outbox[0]
                try:
                    self._publisher(event_type, data)
                except ValueError:   # an invalid event never gets better: report it and go on
                    log.exception("event %s is invalid and was dropped", event_type)
                except Exception:  # noqa: BLE001 - the change is committed, the publisher is retried later
                    log.exception("event %s stays in the outbox", event_type)
                    return
                self._outbox.pop(0)

    def unsent_events(self) -> list[tuple[str, dict]]:
        with self._lock:
            return list(self._outbox)

    def next_client_id(self, prefix: str) -> str:
        with self._lock:
            self._client_number += 1
            return f"{prefix}{self._client_number}"

    def save(self, row: TechnicalUserRecord) -> None:
        with self._lock:
            party = row["subscription_party"]
            if party and row["status"] != "DELETED" and any(
                    other["id"] != row["id"] and other["status"] != "DELETED"
                    and other["offer_subscription_id"] == row["offer_subscription_id"]
                    and other["subscription_party"] == party for other in self._users.values()):
                raise ValueError("a subscription has one account per subscription party")   # README 5: unique
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