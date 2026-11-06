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
"""Every response of C2-M3 against the response schemas of openapi.yaml (fields, types, enums, required)."""
from __future__ import annotations

import datetime as dt
import re

import pytest
import yaml

from portal_common import spec
from test_c2_m3_api import (  # noqa: F401  (the fixtures of the HTTP tests)
    BASE_PATH,
    CUSTOMER,
    PROVIDER,
    ROLE,
    SUBSCRIPTION,
    _service,
    _users,
    client,
    erika,
    hans,
    otto,
)

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TYPES = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list, "null": type(None)}
IDS = {"processId": "00000000-0000-4000-8000-000000000001", "stepRunId": "00000000-0000-4000-8000-000000000002"}


class Schemas:
    """The part of JSON Schema that openapi.yaml of C2-M3 uses."""

    def __init__(self, document: dict) -> None:
        self.document = document
        self.components = document["components"]["schemas"]

    def resolve(self, schema: dict) -> dict:
        return self.components[schema["$ref"].rsplit("/", 1)[1]] if "$ref" in schema else schema

    def declared(self, schema: dict) -> set[str]:
        schema = self.resolve(schema)
        fields = set(schema.get("properties", {}))
        for part in schema.get("allOf", []):
            fields |= self.declared(part)
        return fields

    def check(self, schema: dict, value: object, path: str = "$", *, part: bool = False) -> list[str]:
        """`part`: one branch of an allOf; the fields that the other branches declare are not undeclared."""
        schema = self.resolve(schema)
        if "allOf" in schema:
            errors = [e for branch in schema["allOf"] for e in self.check(branch, value, path, part=True)]
            return errors + ([] if part else self._undeclared(schema, value, path))
        if "oneOf" in schema:
            return [] if any(not self.check(branch, value, path) for branch in schema["oneOf"]) \
                else [f"{path}: matches no branch of oneOf ({str(value)[:40]!r})"]
        errors = []
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected {schema['const']!r}, got {value!r}")
        wanted = schema.get("type")
        wanted = [wanted] if isinstance(wanted, str) else wanted
        if wanted and not any(isinstance(value, TYPES[t]) and not (t == "integer" and isinstance(value, bool))
                              for t in wanted):
            return errors + [f"{path}: {type(value).__name__} is not {wanted}"]
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
        if isinstance(value, str):
            errors += self._text(schema, value, path)
        if isinstance(value, dict):
            props = schema.get("properties", {})
            errors += [f"{path}.{name}: required field is missing" for name in schema.get("required", [])
                       if name not in value]
            for name, item in value.items():
                if name in props:
                    errors += self.check(props[name], item, f"{path}.{name}")
            errors += [] if part else self._undeclared(schema, value, path)
        if isinstance(value, list):
            for index, item in enumerate(value):
                errors += self.check(schema.get("items", {}), item, f"{path}[{index}]")
        return errors

    def _undeclared(self, schema: dict, value: object, path: str) -> list[str]:
        if not isinstance(value, dict) or ("properties" not in schema and "allOf" not in schema):
            return []
        return [f"{path}.{name}: field is not in the schema" for name in sorted(set(value) - self.declared(schema))]

    @staticmethod
    def _text(schema: dict, value: str, path: str) -> list[str]:
        errors = []
        if schema.get("format") == "uuid" and not UUID.match(value):
            errors.append(f"{path}: {value!r} is not a uuid")
        if schema.get("format") == "date-time":
            try:
                dt.datetime.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: {value!r} is not a date-time")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        return errors


@pytest.fixture(scope="module")
def schemas() -> Schemas:
    path = spec.spec_dir() / spec.module("c2-m3").folder / "openapi.yaml"
    return Schemas(yaml.safe_load(path.read_text(encoding="utf-8")))


# -- the validator itself: it must catch what it is there to catch ------------------------------------
SAMPLE = {"components": {"schemas": {
    "Base": {"type": "object", "required": ["id", "status"], "properties": {
        "id": {"type": "string", "format": "uuid"}, "status": {"type": "string", "enum": ["A", "B"]},
        "note": {"type": ["string", "null"]}, "stamp": {"type": "string", "format": "date-time"}}},
    "Child": {"allOf": [{"$ref": "#/components/schemas/Base"},
                        {"type": "object", "required": ["items"], "properties": {
                            "items": {"type": "array", "items": {"type": "integer"}}}}]}}}}
GOOD = {"id": "00000000-0000-4000-8000-000000000001", "status": "A", "note": None, "items": [1, 2],
        "stamp": "2026-11-06T10:00:00+00:00"}


@pytest.mark.parametrize("change, expected", [
    ({}, None),
    ({"status": "C"}, "not one of"),
    ({"id": "nope"}, "not a uuid"),
    ({"note": 5}, "is not"),
    ({"items": [1, "x"]}, "is not"),
    ({"items": [True]}, "is not"),
    ({"stamp": "yesterday"}, "not a date-time"),
    ({"extra": 1}, "not in the schema"),
])
def test_the_validator_catches_what_it_is_for(change, expected):
    errors = Schemas(SAMPLE).check({"$ref": "#/components/schemas/Child"}, GOOD | change)
    assert (not errors) if expected is None else any(expected in error for error in errors), errors


@pytest.mark.parametrize("missing", ["id", "status", "items"])
def test_the_validator_catches_a_missing_required_field(missing):
    errors = Schemas(SAMPLE).check({"$ref": "#/components/schemas/Child"}, {k: v for k, v in GOOD.items() if k != missing})
    assert any("required field is missing" in error for error in errors), errors


# -- the module against the spec ------------------------------------------------------------------
def test_every_response_of_a_full_scenario_matches_openapi(client, erika, hans, otto, schemas):  # noqa: F811
    c12, c10, c6, c8 = (_service(module) for module in ("c12-m1", "c10-m1", "c6-m1", "c8-m1"))
    problems: list[str] = []
    checked = 0

    def go(method: str, template: str, url: str, status: int, **kwargs):
        nonlocal checked
        response = client.request(method, url, **kwargs)
        checked += 1
        if response.status_code != status:
            problems.append(f"{method} {template}: expected {status}, got {response.status_code} {response.text[:100]}")
            return response
        if status != 204:
            declared = schemas.document["paths"][template][method.lower()]["responses"][str(status)]
            ref = declared.get("$ref")
            body = (schemas.document["components"]["responses"][ref.rsplit("/", 1)[1]] if ref else declared)["content"]
            schema = next(iter(body.values()))["schema"]
            problems.extend(schemas.check(schema, response.json(), f"{method} {template} {status}"))
        return response

    def step(step_name: str, **body):
        return go("POST", f"/steps/{step_name}", f"{BASE_PATH}/steps/{step_name}", 200, headers=c12, json=IDS | body)

    account_path = "/companies/{companyId}/technical-users"
    users = _users(CUSTOMER)
    plain = go("POST", account_path, users, 201, headers=erika,
               json={"name": "Agent", "description": "d", "roles": [ROLE]}).json()
    wallet = go("POST", account_path, users, 201, headers=erika,
                json={"name": "Wallet", "roles": [{"name": "Identity Wallet Management"}]}).json()
    go("GET", account_path, users, 200, headers=erika)
    go("GET", account_path, users + "?status=ACTIVE&status=PENDING&origin=OWN&walletAccess=NONE", 200, headers=erika)
    go("GET", account_path + "/{id}", f"{users}/{plain['id']}", 200, headers=erika)
    go("GET", account_path + "/assignable-roles", users + "/assignable-roles?lang=en", 200, headers=erika)
    go("PATCH", account_path + "/{id}", f"{users}/{plain['id']}", 200, headers=erika,
       json={"name": "Renamed", "roles": [{"name": "Semantic Model Management"}]})
    go("POST", account_path + "/{id}/credentials/rotate", f"{users}/{plain['id']}/credentials/rotate", 200,
       headers=erika)
    step("apply-wallet-access", technicalUserId=wallet["id"], outcome="ACTIVE", walletAccountRef="wallet-1")
    created = step("create-for-subscription", customerCompanyId=CUSTOMER, providerCompanyId=PROVIDER,
                   offerSubscriptionId=SUBSCRIPTION, name="Profile",
                   roles=[ROLE, {"name": "Identity Wallet Management"}, {"name": "BPDM Sharing Output Consumer"}]).json()
    customer_account = created["result"]["accounts"][0]["technicalUserId"]
    go("GET", "/osp/technical-users", f"{BASE_PATH}/osp/technical-users", 200, headers=otto)
    go("GET", "/osp/technical-users/{id}", f"{BASE_PATH}/osp/technical-users/{customer_account}", 200, headers=otto)
    check_path = "/internal/technical-users/{id}"
    go("GET", check_path, f"{BASE_PATH}/internal/technical-users/{plain['id']}?companyId={CUSTOMER}", 200, headers=c6)
    go("GET", check_path, f"{BASE_PATH}/internal/technical-users/{PROVIDER}?companyId={CUSTOMER}", 200, headers=c6)
    go("POST", check_path + "/credentials/rotate",
       f"{BASE_PATH}/internal/technical-users/{customer_account}/credentials/rotate", 200, headers=c10,
       json={"offerSubscriptionId": SUBSCRIPTION})
    go("GET", "/internal/technical-roles", f"{BASE_PATH}/internal/technical-roles?lang=en", 200, headers=c8)
    step("disable-company-technical-users", companyId=CUSTOMER)
    step("enable-company-technical-users", companyId=CUSTOMER)
    step("disable-subscription-technical-users", offerSubscriptionId=SUBSCRIPTION)
    go("DELETE", account_path + "/{id}", f"{users}/{wallet['id']}", 202, headers=erika)
    step("delete", technicalUserId=wallet["id"])
    go("DELETE", account_path + "/{id}", f"{users}/{plain['id']}", 204, headers=erika)
    # the error bodies
    go("POST", account_path, users, 400, headers=erika, json={"name": ""})
    go("GET", account_path + "/{id}", f"{BASE_PATH}/companies/{PROVIDER}/technical-users/{plain['id']}", 404,
       headers=erika)
    go("PATCH", account_path + "/{id}", f"{users}/{customer_account}", 409, headers=erika, json={"name": "x"})
    go("PATCH", account_path + "/{id}", f"{_users(PROVIDER)}/{customer_account}", 403, headers=hans,
       json={"name": "x"})

    assert checked >= 26   # a scenario that silently skips calls would prove nothing
    assert not problems, problems
