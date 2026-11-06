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
"""Operations of people on technical users (README 7.2, 7.4, 7.5, 7.6) and the rotation for Subscriptions (9.2)."""
from __future__ import annotations

import contextlib

from portal_common.problems import Problem

from modules.c2_m3 import gateways
from modules.c2_m3.models import Origin, TechnicalUserRecord, Viewer
from modules.c2_m3.repository import repository
from modules.c2_m3.schemas import SubscriptionCredentialsRequest, TechnicalUserCreate, TechnicalUserUpdate
from . import accounts, audit, config, iam_access, projections, roles, state, validation
from .audit import Actor
from .config import MODULE


def create_technical_user(*, company_id: str, body: dict, actor_sub: str) -> dict:
    data = validation.parse(TechnicalUserCreate, body)
    role_names = data.role_names
    company = gateways.company_ready(company_id)
    roles.require_assignable(company_id, role_names)
    wallet_requested, assigned = roles.split(role_names)
    row = accounts.new_row(company_id=company_id, name=data.name, description=data.description, origin=Origin.OWN)
    iam = iam_access.iam()
    try:
        created = iam_access.call(iam.create_or_complete, row["iam_client_id"], name=row["name"],
                                  description=row["description"], company_id=company_id, bpn=company["bpn"],
                                  roles=assigned)
        secret = iam_access.call(iam.secret, row["iam_client_id"])
        accounts.complete_creation(row, created, wallet_requested=wallet_requested, added_roles=assigned,
                                   operation="createTechnicalUser", actor=Actor.person(actor_sub))
    except Exception:
        repository.remove(row["id"])
        with contextlib.suppress(Problem):
            iam_access.call(iam.delete, row["iam_client_id"])
        raise
    return projections.details(row, Viewer.OWNER) | {"credentials": projections.credentials(row, secret)}


def _update_roles(row: TechnicalUserRecord, data: TechnicalUserUpdate) -> tuple[list[str], list[str]]:
    if data.roles is None:
        return [], []
    role_names = data.role_names
    if row["origin"] == Origin.OWN:
        roles.require_assignable(row["company_id"], role_names)
    else:
        roles.check_exist(role_names)   # 6.5: the company roles do not limit subscription accounts
    wallet_requested, assigned = roles.split(role_names)
    current = set(iam_access.call(iam_access.iam().roles_for, row["iam_client_id"]))
    has_wallet = bool(current & config.wallet_roles()) or row["wallet_access"] != "NONE"
    if has_wallet != wallet_requested:
        raise Problem(MODULE, 409, "wallet-role-change", retryable=False)
    return iam_access.call(iam_access.iam().set_roles, row["iam_client_id"], assigned)


def _update_metadata(row: TechnicalUserRecord, data: TechnicalUserUpdate) -> bool:
    name = data.name if "name" in data.model_fields_set else row["name"]
    description = data.description if "description" in data.model_fields_set else row["description"]
    if (name, description) == (row["name"], row["description"]):
        return False
    iam_access.call(iam_access.iam().update_client, row["iam_client_id"], name=name, description=description)
    row["name"], row["description"] = name, description
    return True


def update_technical_user(*, id: str, company_id: str, body: dict, actor_sub: str) -> dict:
    actor = Actor.person(actor_sub)
    with repository.locked(f"technical-user:{id}"):
        row = accounts.find(id)
        accounts.require_owner(row, company_id)
        data = validation.parse(TechnicalUserUpdate, body)
        state.require_changeable(row)
        added, removed = _update_roles(row, data)
        metadata_changed = _update_metadata(row, data)
        if added or removed or metadata_changed:
            with repository.transaction():
                accounts.touch(row)
                audit.record(row, "updateTechnicalUser", actor)
                audit.record_role_changes(row, added, removed, "updateTechnicalUser", actor)
        return projections.details(row, Viewer.OWNER)


def delete_technical_user(*, id: str, company_id: str, actor_sub: str) -> tuple[int, dict | None]:
    """Returns `(204, None)` or `(202, account)` if the wallet account has to be deleted first."""
    actor = Actor.person(actor_sub)
    with repository.locked(f"technical-user:{id}"):
        row = accounts.find(id)
        viewer = accounts.viewer_of(row, company_id)
        state.require_deletable(row)
        if gateways.connector_uses(id):
            raise Problem(MODULE, 409, "in-use", retryable=False)
        if row["origin"] == Origin.SUBSCRIPTION and gateways.subscription_is_active(row["offer_subscription_id"]):
            raise Problem(MODULE, 409, "in-use", retryable=False)
        if state.needs_wallet_removal(row):
            state.request_removal(row)
            with repository.transaction():
                accounts.touch(row)
                audit.record(row, "deleteTechnicalUser", actor)
                audit.wallet_access_removal_requested(row)
            return 202, projections.details(row, viewer)
        accounts.delete_account(row, operation="deleteTechnicalUser", actor=actor)
        return 204, None


def rotate_credentials(*, id: str, company_id: str, actor_sub: str) -> dict:
    with repository.locked(f"technical-user:{id}"):
        row = accounts.find(id)
        accounts.require_owner(row, company_id)
        state.require_rotatable(row)
        secret = iam_access.call(iam_access.iam().rotate_secret, row["iam_client_id"])
        audit.record(row, "rotateCredentials", Actor.person(actor_sub))
        return projections.credentials(row, secret)


def rotate_subscription_credentials(*, id: str, offer_subscription_id: str | None = None, **_other) -> dict:
    subscription_id = validation.parse(SubscriptionCredentialsRequest,
                                       {"offerSubscriptionId": offer_subscription_id}).offerSubscriptionId
    with repository.locked(f"technical-user:{id}"):
        row = repository.get(id)
        if row is None or row["origin"] != Origin.SUBSCRIPTION or row["offer_subscription_id"] != subscription_id:
            raise Problem(MODULE, 404, "not-found", retryable=False)
        state.require_rotatable(row)
        secret = iam_access.call(iam_access.iam().rotate_secret, row["iam_client_id"])
        audit.record(row, "rotateSubscriptionCredentials", Actor.process())
        return projections.credentials(row, secret)
