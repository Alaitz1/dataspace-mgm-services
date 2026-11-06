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
"""Identity and lifecycle guarantees of C2-M3: who owns an IAM client, what may run at the same time, what is final."""
from __future__ import annotations

import threading
import time

import jwt
import pytest

from conftest import BASE
from modules.c2_m3 import iam, service
from modules.c2_m3.iam import IamError
from modules.c2_m3.repository import repository
from portal_common import http as phttp
from portal_common.problems import Problem
from scaffold import app as scaffold_app
from test_c2_m3_api import client, erika, otto, _service, _users  # noqa: F401  (fixtures of the HTTP tests)
from tools import test_iam

U1 = "c0000001-0000-4000-8000-000000000001"
U2 = "c0000002-0000-4000-8000-000000000002"
SUB = "0b5d7e2a-3c4f-4a1b-9e8d-7f6a5b4c3d21"
ACTOR = "5a1c0002-0000-4000-8000-000000000002"
IDS = {"processId": "00000000-0000-4000-8000-000000000001", "stepRunId": "00000000-0000-4000-8000-000000000002"}
ROLE = {"name": "Dataspace Discovery"}
WALLET = {"name": "Identity Wallet Management"}
WAIT = 10


@pytest.fixture
def c2m3(monkeypatch):
    monkeypatch.delenv("IAM_URL", raising=False)
    for neighbour in ("C3_M1_URL", "C6_M1_URL", "C10_M1_URL"):
        monkeypatch.setenv(neighbour, "")
    service.reset()
    yield service
    service.reset()


def _create(company: str, *roles: dict) -> dict:
    return service.create_technical_user(company_id=company, body={"name": "Agent", "roles": list(roles or [ROLE])},
                                         actor_sub=ACTOR)


def _token(credentials: dict) -> tuple[int, dict]:
    """A client-credentials exchange at the token endpoint of the installation's IAM."""
    status, body = test_iam.iam().token_request({"grant_type": "client_credentials",
                                                 "client_id": credentials["iamClientId"],
                                                 "client_secret": credentials["secret"]})
    return status, jwt.decode(body["access_token"], options={"verify_signature": False}) if status == 200 else body


def _subscription_body(**change) -> dict:
    return IDS | {"customerCompanyId": U1, "providerCompanyId": U2, "offerSubscriptionId": SUB, "name": "Profile",
                  "roles": [ROLE]} | change


def _paused(monkeypatch, target, method: str) -> tuple[threading.Event, threading.Event]:
    """Makes `target.method` stop on entry until `release` is set; `entered` tells that a thread is inside."""
    entered, release = threading.Event(), threading.Event()
    real = getattr(target, method)

    def slow(*args, **kwargs):
        entered.set()
        release.wait(WAIT)
        return real(*args, **kwargs)
    monkeypatch.setattr(target, method, slow)
    return entered, release


def _start(function, **results) -> threading.Thread:
    thread = threading.Thread(target=lambda: results.update(value=function()), daemon=True)
    thread.start()
    thread.results = results   # type: ignore[attr-defined]
    return thread


# -- R1: identity allocation and ownership -------------------------------------------------------------
def test_a_restart_never_hands_the_client_of_one_company_to_another(c2m3):
    old = _create(U1)["credentials"]
    assert _token(old)[1]["company_id"] == U1
    repository.reset()   # a restart: the allocator starts again, the IAM keeps its clients
    new = _create(U2)["credentials"]
    assert new["iamClientId"] != old["iamClientId"]
    assert _token(old)[1]["company_id"] == U1, "the old secret must keep acting for the old company"
    assert _token(new)[1]["company_id"] == U2


def test_a_client_that_belongs_to_another_account_is_never_adopted(c2m3):
    first = _create(U1)
    conflict = getattr(iam, "IamConflict", RuntimeError)
    with pytest.raises(conflict):
        iam.get().create_or_complete(first["iamClientId"], owner_id="some-other-account", name="x", description=None,
                                     company_id=U2, bpn="BPNL00000000U2LG", roles=[])
    assert _token(first["credentials"])[1]["company_id"] == U1


def test_a_client_of_the_installation_that_is_not_ours_is_not_taken(c2m3):
    test_iam.iam().create_technical_user("sa1", U1, "BPNLIUK2REMLK3F4", ["Dataspace Discovery"])
    created = _create(U2)
    assert created["iamClientId"] != "sa1"


# -- R2, R3: what may not run at the same time ---------------------------------------------------------
def test_creation_and_company_deactivation_are_serialized(c2m3, monkeypatch):
    memory = iam.get()
    entered, release = _paused(monkeypatch, memory, "create_or_complete")
    creating = _start(lambda: _create(U1))
    assert entered.wait(WAIT)
    disabling = _start(lambda: service.disable_company_technical_users(IDS | {"companyId": U1}))
    time.sleep(0.3)   # the deactivation gets its chance to run ahead of the unfinished creation
    release.set()
    creating.join(WAIT)
    disabling.join(WAIT)
    account = creating.results["value"]
    row = repository.get(account["id"])
    assert row["disabled"] is True, "the account of a deactivated company stays disabled"
    assert memory.client(row["iam_client_id"])["enabled"] is False
    assert account["id"] in disabling.results["value"]["result"]["technicalUserIds"]


def test_a_wallet_result_is_not_lost_to_a_company_deactivation(c2m3, monkeypatch):
    account = _create(U1, WALLET)
    entered, release = _paused(monkeypatch, iam.get(), "set_enabled")
    disabling = _start(lambda: service.disable_company_technical_users(IDS | {"companyId": U1}))
    assert entered.wait(WAIT)
    applying = _start(lambda: service.apply_wallet_access(
        IDS | {"technicalUserId": account["id"], "outcome": "ACTIVE", "walletAccountRef": "wallet-1"}))
    time.sleep(0.3)
    release.set()
    disabling.join(WAIT)
    applying.join(WAIT)
    row = repository.get(account["id"])
    assert (row["status"], row["wallet_access"], row["wallet_account_ref"]) == ("ACTIVE", "ACTIVE", "wallet-1")
    assert row["disabled"] is True


def test_a_stale_row_cannot_overwrite_a_newer_one(c2m3):
    account = _create(U1)
    stale, fresh = repository.get(account["id"]), repository.get(account["id"])
    fresh["name"] = "newer"
    repository.save(fresh)
    stale["name"] = "older"
    conflict = getattr(__import__("modules.c2_m3.repository", fromlist=["Conflict"]), "Conflict", RuntimeError)
    with pytest.raises(conflict):
        repository.save(stale)
    assert repository.get(account["id"])["name"] == "newer"


def test_locks_taken_together_never_deadlock():
    locked_all = getattr(repository, "locked_all", None)
    assert locked_all, "several keys are locked together, in a fixed order"
    barrier, failures = threading.Barrier(2), []

    def work(keys: tuple[str, ...]) -> None:
        try:
            barrier.wait(WAIT)
            for _ in range(200):
                with locked_all(*keys):
                    pass
        except Exception as exc:   # noqa: BLE001 - reported by the assertion below
            failures.append(exc)
    threads = [threading.Thread(target=work, args=(keys,), daemon=True)
               for keys in (("company:a", "technical-user:b"), ("technical-user:b", "company:a"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT)
    assert not any(thread.is_alive() for thread in threads), "deadlock"
    assert not failures


# -- R4: INACTIVE is final -----------------------------------------------------------------------------
def test_an_inactive_subscription_account_is_not_reactivated_by_a_retried_creation(c2m3, monkeypatch):
    memory, real, failures = iam.get(), iam.get().create_or_complete, {"left": 1}

    def flaky(*args, **kwargs):
        if failures["left"]:
            failures["left"] -= 1
            raise IamError("Portal IAM down")
        return real(*args, **kwargs)
    monkeypatch.setattr(memory, "create_or_complete", flaky)
    with pytest.raises(Problem):
        service.create_for_subscription(_subscription_body())
    service.disable_subscription_technical_users(IDS | {"offerSubscriptionId": SUB})
    assert [row["status"] for row in repository.find(offer_subscription_id=SUB)] == ["INACTIVE"]

    service.create_for_subscription(_subscription_body())   # the retry of Process Orchestration
    row = repository.find(offer_subscription_id=SUB)[0]
    assert row["status"] == "INACTIVE"
    assert not service.check_technical_user(id=row["id"], company_id=U1, offer_subscription_id=SUB)["usableForConnector"]
    service.disable_company_technical_users(IDS | {"companyId": U1})
    service.enable_company_technical_users(IDS | {"companyId": U1})
    client = memory.client(row["iam_client_id"])
    assert client is None or client["enabled"] is False


# -- R5: the credentials of the in-memory IAM work -----------------------------------------------------
def test_credentials_of_the_memory_iam_authenticate_at_the_returned_token_url(c2m3):
    phttp.register_local(BASE, scaffold_app.create_app())
    service.reset()
    credentials = _create(U1)["credentials"]

    def exchange(secret: str) -> int:
        return phttp.request("POST", credentials["tokenUrl"], data={
            "grant_type": "client_credentials", "client_id": credentials["iamClientId"],
            "client_secret": secret}).status_code
    assert exchange(credentials["secret"]) == 200
    status, claims = _token(credentials)
    assert claims["company_id"] == U1 and claims["resource_access"]["technical_roles_management"]["roles"] == [
        "Dataspace Discovery"]
    assert "portal-core" not in str(claims.get("aud"))


def test_the_memory_iam_follows_disable_rotate_and_delete_like_keycloak(c2m3):
    own = _create(U1)
    credentials, user = own["credentials"], own["id"]
    assert _token(credentials)[0] == 200
    service.disable_company_technical_users(IDS | {"companyId": U1})
    assert _token(credentials)[0] == 401
    service.enable_company_technical_users(IDS | {"companyId": U1})
    assert _token(credentials)[0] == 200, "the same secret works again"
    rotated = service.rotate_credentials(id=user, company_id=U1, actor_sub=ACTOR)
    assert _token(credentials)[0] == 401
    assert _token(rotated)[0] == 200
    service.delete_technical_user(id=user, company_id=U1, actor_sub=ACTOR)
    assert _token(rotated)[0] == 401


# -- the order of effects ------------------------------------------------------------------------------
def test_role_changes_are_audited_even_if_the_metadata_update_fails(c2m3, monkeypatch):
    account = _create(U1)

    def failing(*args, **kwargs):
        raise IamError("Portal IAM down")
    monkeypatch.setattr(iam.get(), "update_client", failing)
    with pytest.raises(Problem):
        service.update_technical_user(id=account["id"], company_id=U1, actor_sub=ACTOR, body={
            "name": "Renamed", "roles": [{"name": "Semantic Model Management"}]})
    assert iam.get().roles_for(account["iamClientId"]) == ["Semantic Model Management"]
    changes = [(entry["role_name"], entry["action"]) for entry in repository.role_assignment_entries()]
    assert ("Semantic Model Management", "ADDED") in changes and ("Dataspace Discovery", "REMOVED") in changes


def test_the_creation_answer_needs_no_further_iam_call(c2m3, monkeypatch):
    def failing(*args, **kwargs):
        raise IamError("Portal IAM down")
    monkeypatch.setattr(iam.get(), "roles_for", failing)
    created = _create(U1, ROLE, WALLET)
    assert created["credentials"]["secret"]
    assert sorted(role["name"] for role in created["roles"]) == ["Dataspace Discovery", "Identity Wallet Management"]


def test_a_rotation_request_with_an_undeclared_field_changes_nothing(client, erika):   # noqa: F811
    account = client.post(f"/api/c2-m3/steps/create-for-subscription", headers=_service("c12-m1"), json=_subscription_body())
    user = account.json()["result"]["accounts"][0]["technicalUserId"]
    client_id = account.json()["result"]["accounts"][0]["iamClientId"]
    before = iam.get().secret(client_id)
    rejected = client.post(f"/api/c2-m3/internal/technical-users/{user}/credentials/rotate", headers=_service("c10-m1"),
                           json={"offerSubscriptionId": SUB, "extra": True})
    assert rejected.status_code == 400
    assert iam.get().secret(client_id) == before
