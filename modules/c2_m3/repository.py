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

import threading

from .models import AuditLogRecord, RoleAssignmentLogRecord, TechnicalUserRecord


class InMemoryTechnicalUserRepository:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.technical_users: dict[str, TechnicalUserRecord] = {}
        self.audit_log: list[AuditLogRecord] = []
        self.role_assignment_log: list[RoleAssignmentLogRecord] = []
        self._client_number = 0

    def reset(self) -> None:
        with self.lock:
            self.technical_users.clear()
            self.audit_log.clear()
            self.role_assignment_log.clear()
            self._client_number = 0

    def next_client_id(self, prefix: str) -> str:
        with self.lock:
            self._client_number += 1
            return f"{prefix}{self._client_number}"

    def add(self, row: TechnicalUserRecord) -> None:
        with self.lock:
            self.technical_users[row["id"]] = row

    def get(self, user_id: str) -> TechnicalUserRecord | None:
        return self.technical_users.get(user_id)

    def remove(self, user_id: str) -> None:
        with self.lock:
            self.technical_users.pop(user_id, None)

    def all(self) -> list[TechnicalUserRecord]:
        return list(self.technical_users.values())

    def find_subscription(self, subscription_id: str, party: str) -> TechnicalUserRecord | None:
        return next((row for row in self.all()
                     if row["offer_subscription_id"] == subscription_id
                     and row["subscription_party"] == party and row["status"] != "DELETED"), None)

    def add_audit_entry(self, entry: AuditLogRecord) -> None:
        with self.lock:
            self.audit_log.append(entry)

    def add_role_assignment_entry(self, entry: RoleAssignmentLogRecord) -> None:
        with self.lock:
            self.role_assignment_log.append(entry)


repository = InMemoryTechnicalUserRepository()