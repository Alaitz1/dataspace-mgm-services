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
"""Neighbouring modules of C2-M3 (README 11.2) with their built-in stand-ins (empty address)."""
from __future__ import annotations

import json
from pathlib import Path

from portal_common import neighbours
from portal_common.problems import Problem

MODULE = "c2-m3"
_STUB_COMPANIES = Path(__file__).resolve().parent / "stub-companies.json"


def company(company_id: str | None) -> dict:
    """C3-M1 `query_company`; 404 `not-found` if the company is unknown."""
    if not company_id:
        raise Problem(MODULE, 404, "not-found", retryable=False)
    if neighbours.is_standin("c3-m1"):
        found = json.loads(_STUB_COMPANIES.read_text(encoding="utf-8"))["companies"].get(company_id)
    else:
        found = neighbours.query(MODULE, "c3-m1", "query_company", companyId=company_id)
    if not found:
        raise Problem(MODULE, 404, "not-found", retryable=False)
    return found


def company_ready(company_id: str | None) -> dict:
    """A company that is `ACTIVE` and has a BPN (7.2, 8.1)."""
    found = company(company_id)
    if found.get("status") != "ACTIVE" or not found.get("bpn"):
        raise Problem(MODULE, 409, "company-not-ready", retryable=False)
    return found


def company_role_names(company_data: dict) -> set[str]:
    names = set()
    for role in company_data.get("companyRoles") or []:
        if isinstance(role, str):
            names.add(role)
        elif isinstance(role, dict) and role.get("status", "ACTIVE") == "ACTIVE" and role.get("companyRole"):
            names.add(role["companyRole"])
    return names


def connector_uses(technical_user_id: str) -> bool:
    """C6-M1 `list_connectors_internal`: does an active connector use the account?"""
    if neighbours.is_standin("c6-m1"):
        return False
    return bool(neighbours.query(MODULE, "c6-m1", "list_connectors_internal", technicalUserId=technical_user_id))


def subscription_is_active(offer_subscription_id: str) -> bool:
    """C10-M1 `get_subscription_internal`."""
    if neighbours.is_standin("c10-m1"):
        return False
    found = neighbours.query(MODULE, "c10-m1", "get_subscription_internal", offerSubscriptionId=offer_subscription_id)
    return bool(found) and found.get("status") == "ACTIVE"
