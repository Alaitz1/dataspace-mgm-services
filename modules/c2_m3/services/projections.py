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
"""API shapes of a technical user (`TechnicalUserSummary`, `TechnicalUser`, `Credentials`)."""
from __future__ import annotations

from portal_common import tokens

from modules.c2_m3.models import TechnicalUserRecord, Viewer, WalletAccess
from . import config, iam_access


def summary(row: TechnicalUserRecord, viewer: Viewer) -> dict:
    return {"id": row["id"], "companyId": row["company_id"], "name": row["name"],
            "description": row["description"], "origin": row["origin"],
            "offerSubscriptionId": row["offer_subscription_id"],
            "subscriptionParty": row["subscription_party"], "coViewerCompanyId": row["co_viewer_company_id"],
            "viewerRole": viewer, "status": row["status"], "iamClientId": row["iam_client_id"],
            "walletAccess": row["wallet_access"], "disabled": row["disabled"],
            "createdAt": row["created_at"], "changedAt": row["changed_at"]}


def details(row: TechnicalUserRecord, viewer: Viewer, roles: list[str] | None = None) -> dict:
    """7.3: the roles come from the Portal IAM (or are given by the caller, who has just set them); with wallet
    access the wallet role is listed too."""
    if roles is None:
        roles = iam_access.call(iam_access.iam().roles_for, row["iam_client_id"]) if row["iam_client_uuid"] else []
    if row["wallet_access"] != WalletAccess.NONE:
        roles = sorted(set(roles) | config.wallet_roles())
    result = summary(row, viewer) | {"authMethod": "SECRET", "roles": [{"name": name} for name in roles]}
    if row["wallet_access"] == WalletAccess.ACTIVE:
        result["walletAccountRef"] = row["wallet_account_ref"]
    return result


def credentials(row: TechnicalUserRecord, secret: str) -> dict:
    return {"iamClientId": row["iam_client_id"], "secret": secret, "tokenUrl": tokens.token_endpoint()}
