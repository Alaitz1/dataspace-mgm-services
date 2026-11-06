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
"""Steps for Process Orchestration (README 8); every step is idempotent through its business key (6.9)."""
from __future__ import annotations

from portal_common import standin

from modules.c2_m3 import gateways
from modules.c2_m3.models import LIVE_STATUSES, Origin, Status, SubscriptionParty, TechnicalUserRecord
from modules.c2_m3.repository import repository
from . import accounts, audit, config, iam_access, roles, state, validation
from .audit import Actor


def _subscription_account(input: dict, *, party: SubscriptionParty, company_id: str, role_names: list[str],
                          co_viewer_company_id: str | None, actor: Actor) -> dict:
    subscription_id = input["offerSubscriptionId"]
    row = repository.find_subscription(subscription_id, party)
    if row is None:
        client_id = accounts.draw_client_id()
        row = accounts.new_row(company_id=company_id, name=f"{client_id}-{input['name']}", description=None,
                               origin=Origin.SUBSCRIPTION, client_id=client_id,
                               offer_subscription_id=subscription_id, subscription_party=party,
                               co_viewer_company_id=co_viewer_company_id)
    wallet_requested = party == SubscriptionParty.CUSTOMER and bool(set(role_names) & config.wallet_roles())
    _, assigned = roles.split(role_names)
    iam = iam_access.iam()
    first_completion = row["iam_client_uuid"] is None
    before = set() if first_completion else set(iam_access.call(iam.roles_for, row["iam_client_id"]))
    company = gateways.company(company_id)
    created = iam_access.call(iam.create_or_complete, row["iam_client_id"], name=row["name"], description=None,
                              company_id=company_id, bpn=company["bpn"], roles=assigned,
                              enabled=not row["disabled"] and row["status"] != Status.INACTIVE)
    if first_completion:
        after = set(iam_access.call(iam.roles_for, row["iam_client_id"]))
        accounts.complete_creation(row, created, wallet_requested=wallet_requested,
                                   added_roles=sorted(after - before), operation="create-for-subscription",
                                   actor=actor)
    return {"technicalUserId": row["id"], "subscriptionParty": party, "iamClientId": row["iam_client_id"],
            "status": row["status"], "walletAccess": row["wallet_access"],
            "roles": [{"name": name} for name in role_names]}


def create_for_subscription(input: dict) -> dict:
    role_names = validation.validate_create(input, max_name=200, extra_fields=validation.SUBSCRIPTION_STEP_FIELDS)
    validation.require_keys(input, ("customerCompanyId", "providerCompanyId", "offerSubscriptionId"))
    roles.check_exist(role_names)
    gateways.company_ready(input["customerCompanyId"])
    provider_only = set(role_names) & config.provider_roles()
    if provider_only:
        gateways.company_ready(input["providerCompanyId"])
    customer_roles = [name for name in role_names if name not in config.provider_roles()]
    actor = Actor.process(input)
    with repository.locked(f"subscription:{input['offerSubscriptionId']}"):
        result = [_subscription_account(input, party=SubscriptionParty.CUSTOMER, company_id=input["customerCompanyId"],
                                        role_names=customer_roles, co_viewer_company_id=input["providerCompanyId"],
                                        actor=actor)]
        if provider_only:
            result.append(_subscription_account(input, party=SubscriptionParty.PROVIDER,
                                                company_id=input["providerCompanyId"],
                                                role_names=sorted(provider_only), co_viewer_company_id=None,
                                                actor=actor))
    return standin.step_reply(input, {"offerSubscriptionId": input["offerSubscriptionId"], "accounts": result})


def _wallet_result(row: TechnicalUserRecord) -> dict:
    return {"technicalUserId": row["id"], "status": row["status"], "walletAccess": row["wallet_access"],
            "walletAccountRef": row["wallet_account_ref"]}


def apply_wallet_access(input: dict) -> dict:
    user_id, outcome, wallet_ref = input.get("technicalUserId"), input.get("outcome"), input.get("walletAccountRef")
    with repository.locked(f"technical-user:{user_id}"):
        row = accounts.find(user_id)
        if outcome not in ("ACTIVE", "FAILED") or (outcome == "ACTIVE" and not wallet_ref):
            raise validation.invalid("outcome ACTIVE requires walletAccountRef")
        if state.apply_wallet_outcome(row, outcome, wallet_ref):
            with repository.transaction():
                accounts.touch(row)
                audit.record(row, "apply-wallet-access", Actor.process(input))
        return standin.step_reply(input, _wallet_result(row))


def delete(input: dict) -> dict:
    user_id = input.get("technicalUserId")
    with repository.locked(f"technical-user:{user_id}"):
        row = accounts.find(user_id)
        if row["status"] != Status.DELETED:
            state.require_removal_pending(row)
            accounts.delete_account(row, operation="delete", actor=Actor.process(input))
        return standin.step_reply(input, {"technicalUserId": row["id"], "status": row["status"]})


def _set_client_enabled(row: TechnicalUserRecord, enabled: bool) -> None:
    if row["iam_client_uuid"]:
        iam_access.call(iam_access.iam().set_enabled, row["iam_client_id"], enabled)


def _save_with_audit(row: TechnicalUserRecord, operation: str, actor: Actor) -> None:
    with repository.transaction():
        accounts.touch(row)
        audit.record(row, operation, actor)


def disable_company_technical_users(input: dict) -> dict:
    validation.require_keys(input, ("companyId",))
    company_id, actor = input["companyId"], Actor.process(input)
    with repository.locked(f"company:{company_id}"):
        for row in repository.find(owner_company_id=company_id, statuses=LIVE_STATUSES, disabled=False):
            _set_client_enabled(row, False)
            state.disable(row)
            _save_with_audit(row, "disable-company-technical-users", actor)
        ids = [row["id"] for row in repository.find(owner_company_id=company_id, statuses=LIVE_STATUSES,
                                                    disabled=True)]
    return standin.step_reply(input, {"companyId": company_id, "technicalUserIds": sorted(ids)})


def enable_company_technical_users(input: dict) -> dict:
    validation.require_keys(input, ("companyId",))
    company_id, actor = input["companyId"], Actor.process(input)
    with repository.locked(f"company:{company_id}"):
        for row in repository.find(owner_company_id=company_id, statuses=LIVE_STATUSES, disabled=True):
            if state.client_enabled_after_enable(row):
                _set_client_enabled(row, True)
            state.enable(row)
            _save_with_audit(row, "enable-company-technical-users", actor)
        ids = [row["id"] for row in repository.find(owner_company_id=company_id, statuses=LIVE_STATUSES,
                                                    disabled=False)]
    return standin.step_reply(input, {"companyId": company_id, "technicalUserIds": sorted(ids)})


def disable_subscription_technical_users(input: dict) -> dict:
    validation.require_keys(input, ("offerSubscriptionId",))
    subscription_id, actor = input["offerSubscriptionId"], Actor.process(input)
    with repository.locked(f"subscription:{subscription_id}"):
        for row in repository.find(offer_subscription_id=subscription_id, statuses=(Status.PENDING, Status.ACTIVE)):
            _set_client_enabled(row, False)
            state.deactivate_subscription_account(row)
            _save_with_audit(row, "disable-subscription-technical-users", actor)
        ids = [row["id"] for row in repository.find(offer_subscription_id=subscription_id,
                                                    statuses=(Status.INACTIVE,))]
    return standin.step_reply(input, {"offerSubscriptionId": subscription_id, "technicalUserIds": sorted(ids)})
