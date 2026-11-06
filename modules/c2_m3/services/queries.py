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
"""Reading operations (README 7.1, 7.3, 7.9, 7.10 and 9.1); they change nothing."""
from __future__ import annotations

from modules.c2_m3.models import DEFAULT_LIST_STATUSES, TechnicalUserRecord, Viewer
from modules.c2_m3.repository import repository
from . import accounts, projections, state, validation


def _statuses(status: str | list[str] | None) -> list[str] | tuple[str, ...]:
    if status is None:
        return DEFAULT_LIST_STATUSES
    return [status] if isinstance(status, str) else list(status)


def _page(rows: list[dict], *, page: int, size: int) -> dict:
    validation.validate_page(page, size)
    rows.sort(key=lambda row: row["createdAt"], reverse=True)
    start = page * size
    return {"items": rows[start:start + size], "page": page, "size": size, "total": len(rows)}


def get_technical_user(*, id: str, company_id: str, **_other) -> dict:
    row = accounts.find(id)
    return projections.details(row, accounts.viewer_of(row, company_id))


def get_any_technical_user(*, id: str, **_other) -> dict:
    return projections.details(accounts.find(id), Viewer.OSP)


def list_technical_users(*, company_id: str, page: int = 0, size: int = 20, status: str | list[str] | None = None,
                         origin: str | None = None, wallet_access: str | None = None, **_other) -> dict:
    rows = repository.find(visible_to=company_id, statuses=_statuses(status), origin=origin,
                           wallet_access=wallet_access)
    return _page([projections.summary(row, _viewer(row, company_id)) for row in rows], page=page, size=size)


def _viewer(row: TechnicalUserRecord, company_id: str) -> Viewer:
    return Viewer.OWNER if row["company_id"] == company_id else Viewer.CO_VIEWER


def list_all_technical_users(*, page: int = 0, size: int = 20, company_id: str | None = None,
                             status: str | list[str] | None = None, origin: str | None = None,
                             wallet_access: str | None = None, disabled: bool | None = None, **_other) -> dict:
    rows = repository.find(owner_company_id=company_id, statuses=_statuses(status), origin=origin,
                           wallet_access=wallet_access, disabled=disabled)
    return _page([projections.summary(row, Viewer.OSP) for row in rows], page=page, size=size)


def check_technical_user(*, id: str, company_id: str | None = None, offer_subscription_id: str | None = None,
                         **_other) -> dict:
    """9.1: always answers, an unknown ID gives `exists: false`."""
    row = repository.get(id)
    if row is None:
        return {"exists": False, "usableForConnector": False}
    return {"exists": True, "belongsToCompany": row["company_id"] == company_id, "status": row["status"],
            "origin": row["origin"], "walletAccess": row["wallet_access"], "disabled": row["disabled"],
            "usableForConnector": state.usable_for_connector(row, company_id, offer_subscription_id)}
