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
"""Shared flows on a technical user: lookup, visibility (6.3), creation and deletion."""
from __future__ import annotations

import uuid

from portal_common.problems import Problem

from modules.c2_m3 import config
from modules.c2_m3.config import MODULE
from modules.c2_m3.models import Origin, Status, SubscriptionParty, TechnicalUserRecord, Viewer, WalletAccess
from modules.c2_m3.repository import repository
from . import audit, iam_access, state
from .audit import Actor


def find(user_id: str | None) -> TechnicalUserRecord:
    row = repository.get(user_id) if user_id else None
    if row is None:
        raise Problem(MODULE, 404, "not-found", retryable=False)
    return row


def viewer_of(row: TechnicalUserRecord, company_id: str | None) -> Viewer:
    """6.3: the owner or the co-viewing company sees the account, everybody else gets 404."""
    if company_id and row["company_id"] == company_id:
        return Viewer.OWNER
    if company_id and row["co_viewer_company_id"] == company_id:
        return Viewer.CO_VIEWER
    raise Problem(MODULE, 404, "not-found", retryable=False)


def require_owner(row: TechnicalUserRecord, company_id: str | None) -> None:
    if viewer_of(row, company_id) != Viewer.OWNER:
        raise Problem(MODULE, 403, "not-owner", retryable=False)


def draw_client_id() -> str:
    """The next client ID of the sequence that is free in the Portal IAM: after a restart the sequence starts again,
    and the IAM can hold clients of other origin; such a client is never taken over."""
    for _attempt in range(1000):
        candidate = repository.next_client_id(config.client_id_prefix())
        if iam_access.call(iam_access.iam().client, candidate) is None:
            return candidate
    raise Problem(MODULE, 502, "iam-error", detail="no free client ID in the Portal IAM", retryable=True)


def new_row(*, company_id: str, name: str, description: str | None, origin: Origin, client_id: str | None = None,
            offer_subscription_id: str | None = None, subscription_party: SubscriptionParty | None = None,
            co_viewer_company_id: str | None = None) -> TechnicalUserRecord:
    """A `PENDING` row whose client ID is stored before the client exists in the Portal IAM (6.9)."""
    now = audit.now()
    row: TechnicalUserRecord = {
        "id": str(uuid.uuid4()), "company_id": company_id, "name": name, "description": description,
        "origin": origin, "offer_subscription_id": offer_subscription_id,
        "subscription_party": subscription_party, "co_viewer_company_id": co_viewer_company_id,
        "iam_client_id": client_id or draw_client_id(), "iam_client_uuid": None,
        "iam_service_account_user_id": None, "status": Status.PENDING, "wallet_access": WalletAccess.NONE,
        "wallet_account_ref": None, "disabled": False, "created_at": now, "changed_at": now, "version": 0}
    repository.save(row)
    return row


def touch(row: TechnicalUserRecord) -> None:
    row["changed_at"] = audit.now()
    repository.save(row)


def complete_creation(row: TechnicalUserRecord, created: dict, *, wallet_requested: bool,
                      added_roles: list[str], operation: str, actor: Actor) -> None:
    """Stores the IAM IDs and the status; rows, logs and events are one transaction (README 6.8)."""
    row["iam_client_uuid"] = created["id"]
    row["iam_service_account_user_id"] = created.get("serviceAccountUserId")
    wallet_requested = state.after_creation(row, wallet_requested=wallet_requested)
    with repository.transaction():
        touch(row)
        audit.record(row, operation, actor)
        audit.record_role_changes(row, added_roles, [], operation, actor)
        audit.created(row)
        if wallet_requested:
            audit.wallet_access_requested(row)


def delete_account(row: TechnicalUserRecord, *, operation: str, actor: Actor) -> None:
    """Deletes the client in the Portal IAM and marks the row `DELETED` (7.5 step 4, 8.3)."""
    roles = iam_access.call(iam_access.iam().roles_for, row["iam_client_id"])
    iam_access.call(iam_access.iam().delete, row["iam_client_id"], owner_id=row["id"])
    state.mark_deleted(row)
    with repository.transaction():
        touch(row)
        audit.record(row, operation, actor)
        audit.record_role_changes(row, [], roles, operation, actor)
        audit.deleted(row)
