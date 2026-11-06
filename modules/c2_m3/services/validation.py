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
"""Input checks of the operations and steps (README 7 and 8): every failure is 400 `validation`."""
from __future__ import annotations

from portal_common.problems import Problem

from .config import MODULE

_CREATE_FIELDS = frozenset({"name", "description", "authMethod", "roles"})
_UPDATE_FIELDS = frozenset({"name", "description", "roles"})
SUBSCRIPTION_STEP_FIELDS = frozenset({"processId", "stepRunId", "customerCompanyId", "providerCompanyId",
                                      "offerSubscriptionId"})


def invalid(detail: str) -> Problem:
    return Problem(MODULE, 400, "validation", detail=detail, retryable=False)


def role_names(values: object) -> list[str]:
    """Names of a non-empty list of `RoleRef` without duplicates."""
    if not isinstance(values, list) or not values:
        raise invalid("roles must be a non-empty array")
    names = [value.get("name") if isinstance(value, dict) else value for value in values]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise invalid("each role requires a name")
    if len(set(names)) != len(names):
        raise invalid("role names must be unique")
    return names


def _check_name(name: object, max_length: int) -> None:
    if not isinstance(name, str) or not 1 <= len(name) <= max_length:
        raise invalid(f"name must contain 1..{max_length} characters")


def _check_description(description: object) -> None:
    if not isinstance(description, str) or len(description) > 255:
        raise invalid("description must contain at most 255 characters")


def validate_create(body: object, *, max_name: int, extra_fields: frozenset[str] = frozenset()) -> list[str]:
    """7.2 and 8.1: returns the role names."""
    if not isinstance(body, dict) or set(body) - (_CREATE_FIELDS | extra_fields):
        raise invalid("request contains unsupported fields")
    _check_name(body.get("name"), max_name)
    if body.get("description") is not None:
        _check_description(body["description"])
    if body.get("authMethod") not in (None, "SECRET"):
        raise invalid("authMethod must be SECRET")
    return role_names(body.get("roles"))


def validate_update(body: object) -> None:
    """7.4."""
    if not isinstance(body, dict) or not body or set(body) - _UPDATE_FIELDS:
        raise invalid("provide name, description, or roles")
    if "name" in body:
        _check_name(body["name"], 80)
    if "description" in body:
        _check_description(body["description"])


def require_keys(input: dict, keys: tuple[str, ...]) -> None:
    if not all(isinstance(input.get(key), str) and input[key] for key in keys):
        raise invalid(f"{', '.join(keys)} required")


def validate_page(page: int, size: int) -> None:
    if page < 0 or not 1 <= size <= 100:
        raise invalid("page must be >= 0 and size must be 1..100")
