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
"""Status rules of README 6.1 and 6.2 as plain functions on a row; the caller saves the row."""
from __future__ import annotations

from portal_common.problems import Problem

from modules.c2_m3.config import MODULE
from modules.c2_m3.models import Origin, Status, SubscriptionParty, TechnicalUserRecord, WalletAccess


def _invalid_state() -> Problem:
    return Problem(MODULE, 409, "invalid-state", retryable=False)


def after_creation(row: TechnicalUserRecord, *, wallet_requested: bool) -> bool:
    """Status once the client exists. An account that was deactivated meanwhile stays `INACTIVE` (6.1: final) and
    asks for no wallet. Returns whether wallet access was requested."""
    if row["status"] == Status.INACTIVE:
        return False
    row["status"] = Status.PENDING if wallet_requested else Status.ACTIVE
    row["wallet_access"] = WalletAccess.REQUESTED if wallet_requested else WalletAccess.NONE
    return wallet_requested


def require_changeable(row: TechnicalUserRecord) -> None:
    """7.4: only `ACTIVE` and not disabled."""
    if row["status"] != Status.ACTIVE or row["disabled"]:
        raise _invalid_state()


def require_rotatable(row: TechnicalUserRecord) -> None:
    """7.6 and 9.2: `ACTIVE` or `PENDING` with a created client, not disabled."""
    if row["status"] not in (Status.ACTIVE, Status.PENDING) or not row["iam_client_uuid"] or row["disabled"]:
        raise _invalid_state()


def require_deletable(row: TechnicalUserRecord) -> None:
    """7.5 step 1."""
    if row["wallet_access"] == WalletAccess.REQUESTED:
        raise Problem(MODULE, 409, "wallet-in-progress", retryable=False)
    if row["status"] not in (Status.ACTIVE, Status.INACTIVE):
        raise _invalid_state()


def needs_wallet_removal(row: TechnicalUserRecord) -> bool:
    return row["wallet_access"] == WalletAccess.ACTIVE


def request_removal(row: TechnicalUserRecord) -> None:
    row["status"], row["wallet_access"] = Status.PENDING_DELETION, WalletAccess.REMOVING


def require_removal_pending(row: TechnicalUserRecord) -> None:
    """8.3."""
    if row["status"] != Status.PENDING_DELETION or row["wallet_access"] != WalletAccess.REMOVING:
        raise _invalid_state()


def mark_deleted(row: TechnicalUserRecord) -> None:
    row["status"], row["wallet_access"], row["wallet_account_ref"] = Status.DELETED, WalletAccess.NONE, None


def apply_wallet_outcome(row: TechnicalUserRecord, outcome: str, wallet_account_ref: str | None) -> bool:
    """8.2: returns False if the outcome is already applied, raises 409 if it cannot be applied."""
    expected = WalletAccess.ACTIVE if outcome == "ACTIVE" else WalletAccess.FAILED
    if row["wallet_access"] == expected and (outcome == "FAILED" or row["wallet_account_ref"] == wallet_account_ref):
        return False
    if row["wallet_access"] != WalletAccess.REQUESTED:
        raise _invalid_state()
    row["wallet_access"] = expected
    row["wallet_account_ref"] = wallet_account_ref if outcome == "ACTIVE" else None
    if row["status"] != Status.INACTIVE:
        row["status"] = Status.ACTIVE
    return True


def disable(row: TechnicalUserRecord) -> bool:
    """8.4: False if the account is already disabled."""
    if row["disabled"]:
        return False
    row["disabled"] = True
    return True


def enable(row: TechnicalUserRecord) -> bool:
    """8.5: False if the account is not disabled."""
    if not row["disabled"]:
        return False
    row["disabled"] = False
    return True


def client_enabled_after_enable(row: TechnicalUserRecord) -> bool:
    """8.5: an `INACTIVE` account keeps its client disabled."""
    return row["status"] != Status.INACTIVE


def deactivate_subscription_account(row: TechnicalUserRecord) -> None:
    """8.6."""
    row["status"] = Status.INACTIVE


def usable_for_connector(row: TechnicalUserRecord, company_id: str | None, offer_subscription_id: str | None) -> bool:
    """9.1."""
    if row["company_id"] != company_id or row["disabled"] or row["status"] not in (Status.ACTIVE, Status.PENDING):
        return False
    if row["origin"] == Origin.OWN:
        return True
    return (offer_subscription_id is not None and row["subscription_party"] == SubscriptionParty.CUSTOMER
            and row["offer_subscription_id"] == offer_subscription_id)
