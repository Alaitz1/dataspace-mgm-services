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
"""The input models of C2-M3 against openapi.yaml, and the 400 `validation` answers they produce."""
from __future__ import annotations

import pytest
import yaml

from modules.c2_m3 import schemas
from modules.c2_m3 import services as service
from modules.c2_m3.repository import repository
from portal_common import spec
from portal_common.problems import Problem

CUSTOMER = "c0000001-0000-4000-8000-000000000001"
PROVIDER = "c0000002-0000-4000-8000-000000000002"
SUBSCRIPTION = "0b5d7e2a-3c4f-4a1b-9e8d-7f6a5b4c3d21"
ACTOR = "5a1c0002-0000-4000-8000-000000000002"
IDS = {"processId": "00000000-0000-4000-8000-000000000001", "stepRunId": "00000000-0000-4000-8000-000000000002"}
ROLE = {"name": "Dataspace Discovery"}

MODELS = {
    "TechnicalUserCreate": schemas.TechnicalUserCreate,
    "TechnicalUserUpdate": schemas.TechnicalUserUpdate,
    "SubscriptionCredentialsRequest": schemas.SubscriptionCredentialsRequest,
    "StepCreateForSubscription": schemas.StepCreateForSubscription,
    "StepApplyWalletAccess": schemas.StepApplyWalletAccess,
    "StepTechnicalUserRef": schemas.StepTechnicalUserRef,
    "StepCompanyRef": schemas.StepCompanyRef,
    "StepSubscriptionRef": schemas.StepSubscriptionRef,
}


@pytest.fixture(scope="module")
def components() -> dict:
    path = spec.spec_dir() / spec.module("c2-m3").folder / "openapi.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["components"]["schemas"]


def _flatten(components: dict, name: str) -> dict:
    """Properties, required fields and limits of a schema, with `allOf` and `$ref` resolved."""
    schema = components[name]
    merged = {"properties": {}, "required": set(), "additionalProperties": schema.get("additionalProperties", True)}
    for part in schema.get("allOf", [schema]):
        part = components[part["$ref"].rsplit("/", 1)[1]] if "$ref" in part else part
        flat = _flatten(components, part["$ref"].rsplit("/", 1)[1]) if "$ref" in part else None
        merged["properties"] |= part.get("properties", {}) if flat is None else flat["properties"]
        merged["required"] |= set(part.get("required", []))
    return merged


@pytest.mark.parametrize("name", sorted(MODELS))
def test_model_has_the_fields_and_requirements_of_the_openapi_schema(components, name):
    wanted, model = _flatten(components, name), MODELS[name].model_json_schema()
    assert set(model["properties"]) == set(wanted["properties"])
    assert set(model.get("required", [])) == wanted["required"]


@pytest.mark.parametrize("name", ["TechnicalUserCreate", "TechnicalUserUpdate", "SubscriptionCredentialsRequest"])
def test_request_bodies_reject_undeclared_fields_like_the_schema(components, name):
    assert components[name]["additionalProperties"] is False
    assert MODELS[name].model_config["extra"] == "forbid"


def test_length_limits_and_enums_match_the_openapi_schema(components):
    create = components["TechnicalUserCreate"]["properties"]
    model = schemas.TechnicalUserCreate.model_json_schema()["properties"]
    assert model["name"]["maxLength"] == create["name"]["maxLength"] == 80
    assert model["description"]["anyOf"][0]["maxLength"] == create["description"]["maxLength"] == 255
    subscription = components["StepCreateForSubscription"]["allOf"][1]["properties"]["name"]
    assert schemas.StepCreateForSubscription.model_json_schema()["properties"]["name"]["maxLength"] == \
        subscription["maxLength"] == 200
    outcome = components["StepApplyWalletAccess"]["allOf"][1]["properties"]["outcome"]["enum"]
    assert schemas.StepApplyWalletAccess.model_json_schema()["properties"]["outcome"]["enum"] == outcome


@pytest.fixture
def c2m3(monkeypatch):
    monkeypatch.delenv("IAM_URL", raising=False)
    monkeypatch.setenv("C3_M1_URL", "")
    monkeypatch.setenv("C6_M1_URL", "")
    monkeypatch.setenv("C10_M1_URL", "")
    service.reset()
    yield service
    service.reset()


def _problem(call, *args, **kwargs) -> Problem:
    with pytest.raises(Problem) as error:
        call(*args, **kwargs)
    return error.value


def _create(body: object) -> dict:
    return service.create_technical_user(company_id=CUSTOMER, body=body, actor_sub=ACTOR)


@pytest.mark.parametrize("body", [
    {"name": "", "roles": [ROLE]},
    {"name": "x" * 81, "roles": [ROLE]},
    {"name": 123, "roles": [ROLE]},
    {"name": "ok", "description": "d" * 256, "roles": [ROLE]},
    {"name": "ok", "description": None, "roles": [ROLE]},
    {"name": "ok", "authMethod": None, "roles": [ROLE]},
    {"name": "ok", "authMethod": "KEY", "roles": [ROLE]},
    {"name": "ok", "roles": []},
    {"name": "ok"},
    {"name": "ok", "roles": [ROLE, ROLE]},
    {"name": "ok", "roles": [{"name": "  "}]},
    {"name": "ok", "roles": [{"name": 5}]},
    {"name": "ok", "roles": "Dataspace Discovery"},
    {"name": "ok", "roles": [ROLE], "extra": True},
    ["not", "an", "object"],
    None,
])
def test_invalid_create_bodies_are_400_validation_and_create_nothing(c2m3, body):
    problem = _problem(_create, body)
    assert (problem.status, problem.name, problem.ext["retryable"]) == (400, "validation", False)
    assert not repository.find()


def test_valid_create_bodies_are_accepted(c2m3):
    created = _create({"name": "n" * 80, "description": "d" * 255, "authMethod": "SECRET", "roles": [ROLE]})
    assert created["status"] == "ACTIVE"
    assert _create({"name": "no description", "roles": [ROLE]})["description"] is None


def test_validation_messages_never_contain_the_submitted_values(c2m3):
    secret_looking = "s3cr3t-" + "x" * 90
    problem = _problem(_create, {"name": secret_looking, "roles": [ROLE]})
    assert "s3cr3t" not in str(problem.body())
    assert "name" in problem.detail


def test_update_needs_something_to_change_and_accepts_nothing_else(c2m3):
    account = _create({"name": "Agent", "roles": [ROLE]})["id"]

    def update(body: object) -> dict:
        return service.update_technical_user(id=account, company_id=CUSTOMER, body=body, actor_sub=ACTOR)

    for body in ({}, {"extra": 1}, {"name": None}, {"roles": None}, {"name": ""}, {"description": "d" * 256},
                 {"roles": []}, {"name": 5}):
        assert _problem(update, body).name == "validation", body
    assert update({"description": ""})["description"] == ""   # the schema has no null; an empty text clears it
    assert update({"name": "Renamed"})["name"] == "Renamed"


@pytest.mark.parametrize("change", [
    {"customerCompanyId": "not-a-uuid"}, {"providerCompanyId": None}, {"offerSubscriptionId": 7},
    {"name": ""}, {"name": "n" * 201}, {"roles": []}, {"processId": "x"},
])
def test_invalid_subscription_steps_are_400_and_create_nothing(c2m3, change):
    body = IDS | {"customerCompanyId": CUSTOMER, "providerCompanyId": PROVIDER, "offerSubscriptionId": SUBSCRIPTION,
                  "name": "Profile", "roles": [ROLE]} | change
    assert _problem(service.create_for_subscription, body).name == "validation"
    assert not repository.find()


def test_a_step_without_its_audit_ids_is_refused(c2m3):
    body = {"customerCompanyId": CUSTOMER, "providerCompanyId": PROVIDER, "offerSubscriptionId": SUBSCRIPTION,
            "name": "Profile", "roles": [ROLE]}
    assert _problem(service.create_for_subscription, body).status == 400


@pytest.mark.parametrize("step, body", [
    ("apply_wallet_access", {"technicalUserId": CUSTOMER, "outcome": "DONE"}),
    ("apply_wallet_access", {"technicalUserId": CUSTOMER, "outcome": "ACTIVE"}),
    ("apply_wallet_access", {"technicalUserId": "x", "outcome": "FAILED"}),
    ("delete", {}),
    ("delete", {"technicalUserId": 5}),
    ("disable_company_technical_users", {"companyId": ""}),
    ("enable_company_technical_users", {}),
    ("disable_subscription_technical_users", {"offerSubscriptionId": "nope"}),
])
def test_invalid_step_inputs_are_400_validation(c2m3, step, body):
    problem = _problem(getattr(service, step), IDS | body)
    assert (problem.status, problem.name, problem.ext["retryable"]) == (400, "validation", False)


def test_rotation_for_subscriptions_needs_a_uuid(c2m3):
    for value in (None, "", "no-uuid"):
        assert _problem(service.rotate_subscription_credentials, id=CUSTOMER,
                        offer_subscription_id=value).name == "validation"
    assert _problem(service.rotate_subscription_credentials, id=CUSTOMER,
                    offer_subscription_id=SUBSCRIPTION).name == "not-found"
