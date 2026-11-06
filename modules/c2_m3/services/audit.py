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
"""Audit log, role assignment log (README 6.8) and events (README 10); no secrets, no names.

The events go to the repository outbox: call them inside the transaction of the change they report."""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from modules.c2_m3.models import ActorType, TechnicalUserRecord
from modules.c2_m3.repository import repository


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


@dataclass(frozen=True)
class Actor:
    """Who changes something: a person (operation) or a process (step)."""

    type: ActorType
    sub: str | None = None
    process_id: str | None = None
    step_run_id: str | None = None

    @classmethod
    def person(cls, sub: str | None) -> Actor:
        return cls(ActorType.PERSON, sub)

    @classmethod
    def process(cls, step_input: dict | None = None) -> Actor:
        step_input = step_input or {}
        return cls(ActorType.PROCESS, None, step_input.get("processId"), step_input.get("stepRunId"))


def record(row: TechnicalUserRecord, operation: str, actor: Actor) -> None:
    repository.add_audit_entry({
        "id": str(uuid.uuid4()), "occurred_at": now(), "actor_type": actor.type, "actor_sub": actor.sub,
        "company_id": row["company_id"], "process_id": actor.process_id, "step_run_id": actor.step_run_id,
        "operation": operation, "object_id": row["id"]})


def record_role(row: TechnicalUserRecord, role: str, action: str, operation: str, actor: Actor) -> None:
    repository.add_role_assignment_entry({
        "id": str(uuid.uuid4()), "occurred_at": now(), "technical_user_id": row["id"],
        "company_id": row["company_id"], "iam_client_id": row["iam_client_id"], "role_name": role,
        "action": action, "actor_type": actor.type, "actor_sub": actor.sub, "process_id": actor.process_id,
        "step_run_id": actor.step_run_id, "operation": operation})


def record_role_changes(row: TechnicalUserRecord, added: list[str], removed: list[str],
                        operation: str, actor: Actor) -> None:
    for role in added:
        record_role(row, role, "ADDED", operation, actor)
    for role in removed:
        record_role(row, role, "REMOVED", operation, actor)


def created(row: TechnicalUserRecord) -> None:
    repository.add_event("TechnicalUserCreated", {
        "technicalUserId": row["id"], "companyId": row["company_id"], "origin": row["origin"],
        "offerSubscriptionId": row["offer_subscription_id"], "subscriptionParty": row["subscription_party"],
        "coViewerCompanyId": row["co_viewer_company_id"], "iamClientId": row["iam_client_id"]})


def wallet_access_requested(row: TechnicalUserRecord) -> None:
    repository.add_event("WalletAccessRequested", {
        "technicalUserId": row["id"], "companyId": row["company_id"],
        "offerSubscriptionId": row["offer_subscription_id"]})


def wallet_access_removal_requested(row: TechnicalUserRecord) -> None:
    repository.add_event("WalletAccessRemovalRequested", {
        "technicalUserId": row["id"], "companyId": row["company_id"], "walletAccountRef": row["wallet_account_ref"]})


def deleted(row: TechnicalUserRecord) -> None:
    repository.add_event("TechnicalUserDeleted", {
        "technicalUserId": row["id"], "companyId": row["company_id"],
        "coViewerCompanyId": row["co_viewer_company_id"], "iamClientId": row["iam_client_id"]})
