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
"""Public interface of C2-M3 Technical Users: the steps and queries of the spec (call convention of AGENTS.md)
and the operations of people, which only the router calls. The logic lives in `services/`."""
from __future__ import annotations

from . import services
from .services import (
    create_technical_user,
    delete_technical_user,
    get_any_technical_user,
    get_technical_user,
    list_all_technical_users,
    list_assignable_roles,
    list_technical_users,
    reset,
    rotate_credentials,
    update_technical_user,
)

MODULE = "c2-m3"

__all__ = [
    "MODULE", "apply_wallet_access", "check_technical_user", "create_for_subscription", "create_technical_user",
    "delete", "delete_technical_user", "disable_company_technical_users", "disable_subscription_technical_users",
    "enable_company_technical_users", "get_any_technical_user", "get_technical_user", "list_all_technical_users",
    "list_assignable_roles", "list_technical_roles", "list_technical_users", "reset", "rotate_credentials",
    "rotate_subscription_credentials", "update_technical_user",
]


# -- steps for Process Orchestration (README 8): input = JSON body incl. processId and stepRunId ---
def create_for_subscription(input: dict) -> dict:
    return services.create_for_subscription(input)


def apply_wallet_access(input: dict) -> dict:
    return services.apply_wallet_access(input)


def delete(input: dict) -> dict:
    return services.delete(input)


def disable_company_technical_users(input: dict) -> dict:
    return services.disable_company_technical_users(input)


def enable_company_technical_users(input: dict) -> dict:
    return services.enable_company_technical_users(input)


def disable_subscription_technical_users(input: dict) -> dict:
    return services.disable_subscription_technical_users(input)


# -- queries for other modules (README 9): parameters by their openapi names ------------------------
def check_technical_user(*, id: str, companyId: str | None = None, offerSubscriptionId: str | None = None,
                         **_other) -> dict:
    """9.1: always answers; an unknown ID gives `exists: false`."""
    return services.check_technical_user(id=id, company_id=companyId, offer_subscription_id=offerSubscriptionId)


def rotate_subscription_credentials(*, id: str, offerSubscriptionId: str | None = None, **other) -> dict:
    """9.2: a new secret of the subscription account, only in this answer."""
    return services.rotate_subscription_credentials(id=id, offer_subscription_id=offerSubscriptionId, **other)


def list_technical_roles(*, lang: str | None = None, **_other) -> list[dict]:
    """9.3: all roles of the technical roles client."""
    return services.list_technical_roles(lang=lang)
