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
"""Configuration of README section 4, read from the environment at call time."""
from __future__ import annotations

import json
import os
from pathlib import Path

from portal_common.problems import Problem

MODULE = "c2-m3"

IDENTITY_WALLET_MANAGEMENT = "Identity Wallet Management"
_ALL_ASSIGNABLE = ("Dataspace Discovery", IDENTITY_WALLET_MANAGEMENT, "Semantic Model Management")
_PROVIDER_ASSIGNABLE = ("BPDM Sharing Input Consumer", "BPDM Sharing Output Consumer", *_ALL_ASSIGNABLE)
DEFAULT_PROVIDER_ONLY_ROLES = ("BPDM Pool Consumer", "BPDM Sharing Output Consumer", "BPDM Sharing Input Manager")
DEFAULT_ROLE_ASSIGNMENTS: dict[str, list[str]] = {
    "ACTIVE_PARTICIPANT": list(_ALL_ASSIGNABLE),
    "APP_PROVIDER": list(_PROVIDER_ASSIGNABLE),
    "SERVICE_PROVIDER": list(_PROVIDER_ASSIGNABLE),
    "ONBOARDING_SERVICE_PROVIDER": [],
}


def _csv(name: str, default: str) -> set[str]:
    return {item.strip() for item in os.environ.get(name, default).split(",") if item.strip()}


def wallet_roles() -> set[str]:
    return _csv("WALLET_ROLES", IDENTITY_WALLET_MANAGEMENT)


def provider_roles() -> set[str]:
    return _csv("PROVIDER_ONLY_ROLES", ",".join(DEFAULT_PROVIDER_ONLY_ROLES))


def client_id_prefix() -> str:
    return os.environ.get("TECHNICAL_USER_CLIENT_ID_PREFIX", "sa")


def role_assignments() -> dict[str, list[str]]:
    """`ROLE_ASSIGNMENT_FILE` (company role -> assignable roles, 6.5) or the initial values."""
    configured = os.environ.get("ROLE_ASSIGNMENT_FILE")
    if not configured:
        return DEFAULT_ROLE_ASSIGNMENTS
    try:
        mapping = json.loads(Path(configured).expanduser().read_text(encoding="utf-8"))
        if not isinstance(mapping, dict):
            raise ValueError("role assignment file must contain an object")
        return {str(role): (value.get("roles", []) if isinstance(value, dict) else value)
                for role, value in mapping.items()}
    except (OSError, ValueError) as exc:
        raise Problem(MODULE, 502, "upstream-error", detail="ROLE_ASSIGNMENT_FILE could not be read",
                      retryable=True) from exc
