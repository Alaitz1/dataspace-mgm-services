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
"""Input of the operations and steps as in `openapi.yaml` (components/schemas); `validation.parse` turns a
failed check into 400 `validation`."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Uuid = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]


class RoleRef(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("role name must not be blank")
        return value


def _unique(roles: list[RoleRef]) -> list[RoleRef]:
    if len({role.name for role in roles}) != len(roles):
        raise ValueError("role names must be unique")
    return roles


RoleList = Annotated[list[RoleRef], Field(min_length=1), AfterValidator(_unique)]


class _Body(BaseModel):
    """A request body with `additionalProperties: false`; an optional field may be left out but not be null."""

    model_config = ConfigDict(strict=True, extra="forbid")

    @model_validator(mode="after")
    def _no_explicit_null(self) -> _Body:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class TechnicalUserCreate(_Body):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    authMethod: Literal["SECRET"] | None = None
    roles: RoleList

    @property
    def role_names(self) -> list[str]:
        return [role.name for role in self.roles]


class TechnicalUserUpdate(_Body):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    roles: RoleList | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> TechnicalUserUpdate:
        if not self.model_fields_set:
            raise ValueError("provide name, description, or roles")
        return self

    @property
    def role_names(self) -> list[str]:
        return [role.name for role in self.roles or []]


class SubscriptionCredentialsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    offerSubscriptionId: Uuid


class StepRequest(BaseModel):
    """`processId` and `stepRunId` are required by openapi.yaml (StepRequest); they only serve the audit log."""

    model_config = ConfigDict(strict=True, extra="ignore")

    processId: Uuid
    stepRunId: Uuid


class StepCreateForSubscription(StepRequest):
    customerCompanyId: Uuid
    providerCompanyId: Uuid
    offerSubscriptionId: Uuid
    name: str = Field(min_length=1, max_length=200)
    roles: RoleList

    @property
    def role_names(self) -> list[str]:
        return [role.name for role in self.roles]


class StepApplyWalletAccess(StepRequest):
    technicalUserId: Uuid
    outcome: Literal["ACTIVE", "FAILED"]
    walletAccountRef: str | None = None

    @model_validator(mode="after")
    def _active_needs_a_reference(self) -> StepApplyWalletAccess:
        if self.outcome == "ACTIVE" and not self.walletAccountRef:
            raise ValueError("outcome ACTIVE requires walletAccountRef")
        return self


class StepTechnicalUserRef(StepRequest):
    technicalUserId: Uuid


class StepCompanyRef(StepRequest):
    companyId: Uuid


class StepSubscriptionRef(StepRequest):
    offerSubscriptionId: Uuid
