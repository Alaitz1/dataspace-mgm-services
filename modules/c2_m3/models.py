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
#  The software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
#  CONDITIONS OF ANY KIND, either express or implied. See the License for the
#  specific language governing permissions and limitations under the License.
#
#  AI Disclosure: This file was entirely AI-generated.
#  The AI-generated portions are made available under CC0-1.0 and not subject
#  to the project's license. The human contributor has reviewed and verified
#  that the code is correct.
#
#  SPDX-License-Identifier: Apache-2.0 AND CC0-1.0
#  Assisted-By: GitHub Copilot (GPT-5.1)
#################################################################################
from __future__ import annotations

from typing import TypedDict


class TechnicalUserRecord(TypedDict):
    id: str
    company_id: str
    name: str
    description: str | None
    origin: str
    offer_subscription_id: str | None
    subscription_party: str | None
    co_viewer_company_id: str | None
    iam_client_id: str
    iam_client_uuid: str | None
    iam_service_account_user_id: str | None
    status: str
    wallet_access: str
    wallet_account_ref: str | None
    disabled: bool
    created_at: str
    changed_at: str


class AuditLogRecord(TypedDict):
    id: str
    occurred_at: str
    actor_type: str
    actor_sub: str | None
    company_id: str
    process_id: str | None
    step_run_id: str | None
    operation: str
    object_id: str


class RoleAssignmentLogRecord(TypedDict):
    id: str
    occurred_at: str
    technical_user_id: str
    company_id: str
    iam_client_id: str
    role_name: str
    action: str
    actor_type: str
    actor_sub: str | None
    process_id: str | None
    step_run_id: str | None
    operation: str