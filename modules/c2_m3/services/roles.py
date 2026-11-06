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
"""Technical user roles: which roles exist, which a company may assign (README 6.5, 7.8, 9.3)."""
from __future__ import annotations

from portal_common.problems import Problem

from modules.c2_m3 import gateways
from . import config, iam_access
from .config import MODULE


def split(roles: list[str]) -> tuple[bool, list[str]]:
    """Wallet role among `roles`? And the roles that are assigned in the Portal IAM (never wallet roles)."""
    wallet = config.wallet_roles()
    return bool(set(roles) & wallet), sorted(set(roles) - wallet)


def check_exist(roles: list[str]) -> None:
    iam_access.call(iam_access.iam().ensure_roles, roles)


def _all_roles(lang: str | None) -> list[dict]:
    return iam_access.call(iam_access.iam().list_roles, lang)


def assignable_names(company_id: str) -> set[str]:
    mapping = config.role_assignments()
    names: set[str] = set()
    for company_role in gateways.company_role_names(gateways.company(company_id)):
        configured = mapping.get(company_role) or []
        names.update([configured] if isinstance(configured, str) else configured)
    return names


def require_assignable(company_id: str, roles: list[str]) -> None:
    """7.2 step 3: the roles exist and the company may assign them."""
    check_exist(roles)
    not_assignable = set(roles) - assignable_names(company_id)
    if not_assignable:
        raise Problem(MODULE, 400, "role-not-assignable", retryable=False,
                      detail=f"roles are not assignable: {sorted(not_assignable)}")


def _views(roles: dict[str, str | None], names: set[str]) -> list[dict]:
    wallet, provider = config.wallet_roles(), config.provider_roles()
    return [{"name": name, "description": roles[name], "grantsWalletAccess": name in wallet,
             "providerOnly": name in provider} for name in sorted(names)]


def list_assignable_roles(*, company_id: str, lang: str | None = None, **_other) -> list[dict]:
    available = {role["name"]: role.get("description") for role in _all_roles(lang)}
    return _views(available, assignable_names(company_id) & set(available))


def list_technical_roles(*, lang: str | None = None, **_other) -> list[dict]:
    """9.3: an unreachable Portal IAM is 502 `upstream-error` here (README 9.3), not `iam-error`."""
    try:
        available = {role["name"]: role.get("description") for role in _all_roles(lang)}
    except Problem as exc:
        if exc.name != "iam-error":
            raise
        raise Problem(MODULE, 502, "upstream-error", detail=exc.detail, retryable=True) from exc
    return _views(available, set(available))
