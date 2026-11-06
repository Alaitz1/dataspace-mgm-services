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
"""C2-M3 over HTTP: token, permission, company scope (README 6.3, 6.4) and the paths of openapi.yaml."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import BASE, bearer
from modules.c2_m3 import router
from portal_common import events
from portal_common import http as phttp
from scaffold import app as scaffold_app
from tools import test_iam

CUSTOMER = "c0000001-0000-4000-8000-000000000001"
PROVIDER = "c0000002-0000-4000-8000-000000000002"
SUBSCRIPTION = "0b5d7e2a-3c4f-4a1b-9e8d-7f6a5b4c3d21"
BASE_PATH = "/api/c2-m3"
ROLE = {"name": "Dataspace Discovery"}


@pytest.fixture
def client(monkeypatch):
    for neighbour in ("C3_M1_URL", "C6_M1_URL", "C10_M1_URL"):
        monkeypatch.setenv(neighbour, "")
    app = scaffold_app.create_app()
    phttp.register_local(BASE, app)
    yield TestClient(app, base_url=BASE)
    scaffold_app.reset_all(app.state.entries)


def _person(key: str, company_id: str | None, bpn: str | None, role: str) -> dict:
    iam = test_iam.iam()
    uid = iam.find(key)
    iam.add_portal_roles(uid, [role])
    if company_id:
        iam.bind(uid, company_id, bpn)
    return bearer(iam.person_token(uid))


@pytest.fixture
def erika():
    return _person("erika", CUSTOMER, "BPNLIUK2REMLK3F4", "Company Admin")


@pytest.fixture
def hans():
    return _person("hans", PROVIDER, "BPNL00000000U2LG", "Company Admin")


@pytest.fixture
def otto():
    return bearer(test_iam.iam().person_token(test_iam.iam().find("otto")))


def _service(module: str) -> dict:
    return bearer(test_iam.iam().client_token(f"svc-{module}"))


def _users(company: str) -> str:
    return f"{BASE_PATH}/companies/{company}/technical-users"


def _create(client, headers, body=None):
    return client.post(_users(CUSTOMER), headers=headers, json=body or {"name": "Build agent", "roles": [ROLE]})


def _subscribe(client) -> str:
    body = {"processId": "00000000-0000-4000-8000-000000000001", "stepRunId": "00000000-0000-4000-8000-000000000002",
            "customerCompanyId": CUSTOMER, "providerCompanyId": PROVIDER, "offerSubscriptionId": SUBSCRIPTION,
            "name": "Profile", "roles": [ROLE]}
    reply = client.post(f"{BASE_PATH}/steps/create-for-subscription", headers=_service("c12-m1"), json=body)
    assert reply.status_code == 200, reply.text
    return reply.json()["result"]["accounts"][0]["technicalUserId"]


def test_create_read_and_list_with_company_scope(client, erika, hans):
    created = _create(client, erika)
    assert created.status_code == 201
    account = created.json()
    assert account["status"] == "ACTIVE" and account["credentials"]["secret"]

    details = client.get(f"{_users(CUSTOMER)}/{account['id']}", headers=erika).json()
    assert [role["name"] for role in details["roles"]] == ["Dataspace Discovery"]
    assert "credentials" not in details and "secret" not in str(details)

    page = client.get(_users(CUSTOMER), headers=erika).json()
    assert page["total"] == 1 and page["items"][0]["viewerRole"] == "OWNER" and "roles" not in page["items"][0]

    assert client.get(_users(PROVIDER), headers=erika).status_code == 404
    assert client.get(_users(CUSTOMER), headers=hans).status_code == 404
    assert client.get(f"{_users(PROVIDER)}/{account['id']}", headers=hans).status_code == 404


def test_checks_run_in_the_documented_order(client, erika):
    assert client.get(_users(CUSTOMER)).status_code == 401
    lieschen = bearer(test_iam.iam().person_token(test_iam.iam().find("lieschen")))
    denied = client.get(_users(CUSTOMER), headers=lieschen)
    assert denied.status_code == 403 and denied.json()["type"] == "urn:c2-m3:problem:forbidden"
    invalid = _create(client, erika, {"name": "", "roles": [ROLE]})
    assert invalid.status_code == 400 and invalid.json()["type"] == "urn:c2-m3:problem:validation"
    assert client.get(_users(CUSTOMER) + "?size=500", headers=erika).status_code == 400


def test_assignable_roles_is_not_taken_for_an_account_id(client, erika):
    roles = client.get(_users(CUSTOMER) + "/assignable-roles", headers=erika)
    assert roles.status_code == 200
    assert {role["name"] for role in roles.json()} >= {"Dataspace Discovery", "Identity Wallet Management"}


def test_co_viewer_may_see_and_delete_but_not_change(client, erika, hans):
    account = _subscribe(client)
    seen = client.get(f"{_users(PROVIDER)}/{account}", headers=hans)
    assert seen.status_code == 200 and seen.json()["viewerRole"] == "CO_VIEWER"
    listed = client.get(_users(PROVIDER), headers=hans).json()["items"]
    assert [item["viewerRole"] for item in listed] == ["CO_VIEWER"]
    assert client.get(f"{_users(CUSTOMER)}/{account}", headers=erika).status_code == 200

    other = client.patch(f"{_users(PROVIDER)}/{account}", headers=hans, json={"name": "x"})
    assert other.status_code == 403 and other.json()["type"] == "urn:c2-m3:problem:not-owner"
    assert client.post(f"{_users(PROVIDER)}/{account}/credentials/rotate", headers=hans).status_code == 403
    assert client.delete(f"{_users(PROVIDER)}/{account}", headers=hans).status_code == 204


def test_update_rotate_and_delete_by_the_owner(client, erika):
    account = _create(client, erika).json()["id"]
    changed = client.patch(f"{_users(CUSTOMER)}/{account}", headers=erika, json={"name": "Renamed"})
    assert changed.status_code == 200 and changed.json()["name"] == "Renamed"
    rotated = client.post(f"{_users(CUSTOMER)}/{account}/credentials/rotate", headers=erika)
    assert rotated.status_code == 200 and rotated.json()["secret"]
    assert client.delete(f"{_users(CUSTOMER)}/{account}", headers=erika).status_code == 204
    assert client.get(_users(CUSTOMER), headers=erika).json()["total"] == 0


def test_delete_with_wallet_access_answers_202_with_the_account(client, erika):
    wallet = {"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]}
    account = _create(client, erika, wallet).json()["id"]
    step = {"processId": "00000000-0000-4000-8000-000000000001", "stepRunId": "00000000-0000-4000-8000-000000000002",
            "technicalUserId": account, "outcome": "ACTIVE", "walletAccountRef": "wallet-1"}
    assert client.post(f"{BASE_PATH}/steps/apply-wallet-access", headers=_service("c12-m1"), json=step).status_code == 200
    removed = client.delete(f"{_users(CUSTOMER)}/{account}", headers=erika)
    assert removed.status_code == 202 and removed.json()["status"] == "PENDING_DELETION"


def test_osp_staff_see_all_companies_but_not_the_company_paths(client, erika, otto):
    _create(client, erika)
    listed = client.get(f"{BASE_PATH}/osp/technical-users", headers=otto).json()
    assert listed["total"] == 1 and listed["items"][0]["viewerRole"] == "OSP"
    assert client.get(f"{BASE_PATH}/osp/technical-users?companyId={PROVIDER}", headers=otto).json()["total"] == 0
    assert client.get(f"{BASE_PATH}/osp/technical-users/{listed['items'][0]['id']}", headers=otto).status_code == 200
    assert client.get(_users(CUSTOMER), headers=otto).status_code == 403
    assert client.get(f"{BASE_PATH}/osp/technical-users", headers=erika).status_code == 403


def test_queries_and_steps_need_their_service_permissions(client, erika):
    account = _subscribe(client)
    path = f"{BASE_PATH}/internal/technical-users/{account}"
    checked = client.get(path, params={"companyId": CUSTOMER, "offerSubscriptionId": SUBSCRIPTION},
                         headers=_service("c6-m1"))
    assert checked.json()["usableForConnector"] is True
    assert client.get(path, params={"companyId": CUSTOMER}, headers=erika).status_code == 403

    rotation = f"{path}/credentials/rotate"
    assert client.post(rotation, json={"offerSubscriptionId": SUBSCRIPTION}, headers=_service("c6-m1")).status_code == 403
    rotated = client.post(rotation, json={"offerSubscriptionId": SUBSCRIPTION}, headers=_service("c10-m1"))
    assert rotated.status_code == 200 and rotated.json()["secret"]
    wrong = client.post(rotation, json={"offerSubscriptionId": PROVIDER}, headers=_service("c10-m1"))
    assert wrong.status_code == 404

    roles = client.get(f"{BASE_PATH}/internal/technical-roles", headers=_service("c8-m1"))
    assert roles.status_code == 200 and {"name", "providerOnly", "grantsWalletAccess"} <= set(roles.json()[0])
    assert client.get(f"{BASE_PATH}/internal/technical-roles", headers=erika).status_code == 403


def test_a_failing_step_carries_retryable(client):
    failed = client.post(f"{BASE_PATH}/steps/disable-company-technical-users", headers=_service("c12-m1"), json={})
    assert failed.status_code == 400
    assert failed.json()["type"] == "urn:c2-m3:problem:validation" and failed.json()["retryable"] is False


def test_the_module_is_a_team_module_with_the_process_stub_hook(client, erika, monkeypatch):
    kinds = {entry["module"]: entry["kind"] for entry in client.get("/scaffold/modules").json()}
    assert kinds["c2-m3"] == "team"

    wallet = {"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]}
    account = _create(client, erika, wallet).json()["id"]
    requested = next(event for event in events.RELAY.log if event["type"] == "WalletAccessRequested")

    router.on_event(requested)
    assert client.get(f"{_users(CUSTOMER)}/{account}", headers=erika).json()["walletAccess"] == "REQUESTED"
    monkeypatch.setenv("PROCESS_STUB", "true")
    router.on_event(requested)
    details = client.get(f"{_users(CUSTOMER)}/{account}", headers=erika).json()
    assert (details["status"], details["walletAccess"]) == ("ACTIVE", "ACTIVE")
    assert details["walletAccountRef"] == f"stub-{account}"
