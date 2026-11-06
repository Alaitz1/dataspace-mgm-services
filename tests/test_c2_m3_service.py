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
from __future__ import annotations

import pytest

from modules.c2_m3 import iam, service
from modules.c2_m3.iam import IamError
from modules.c2_m3.repository import repository
from portal_common import events
from portal_common.problems import Problem

CUSTOMER = "c0000001-0000-4000-8000-000000000001"
PROVIDER = "c0000002-0000-4000-8000-000000000002"
OSP_COMPANY = "11111111-1111-4111-8111-111111111111"
SUBSCRIPTION = "0b5d7e2a-3c4f-4a1b-9e8d-7f6a5b4c3d21"
ACTOR = "5a1c0002-0000-4000-8000-000000000002"


@pytest.fixture
def c2m3(monkeypatch):
    monkeypatch.delenv("IAM_URL", raising=False)
    monkeypatch.delenv("MODULE_URLS", raising=False)
    monkeypatch.setenv("C3_M1_URL", "")
    monkeypatch.setenv("C6_M1_URL", "")
    monkeypatch.setenv("C10_M1_URL", "")
    monkeypatch.delenv("ROLE_ASSIGNMENT_FILE", raising=False)
    service.reset()
    yield service
    service.reset()


def _create_own(body: dict | None = None) -> dict:
    return service.create_technical_user(company_id=CUSTOMER,
        body=body or {"name": "Build agent", "roles": [{"name": "Dataspace Discovery"}]}, actor_sub=ACTOR)


def _step_input(**values) -> dict:
    return {"processId": "00000000-0000-4000-8000-000000000001",
            "stepRunId": "00000000-0000-4000-8000-000000000002", **values}


def _subscription(roles: list[str]) -> dict:
    return service.create_for_subscription(_step_input(customerCompanyId=CUSTOMER, providerCompanyId=PROVIDER,
        offerSubscriptionId=SUBSCRIPTION, name="Profile", roles=[{"name": name} for name in roles]))


def _row(user_id: str) -> dict:
    row = repository.get(user_id)
    assert row is not None
    return row


def _event_types() -> list[str]:
    return [event["type"] for event in events.RELAY.log]


def test_own_creation_and_wallet_step_are_idempotent(c2m3):
    created = _create_own({"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]})
    user_id = created["id"]
    assert created["status"] == "PENDING"
    assert created["walletAccess"] == "REQUESTED"
    assert created["credentials"]["secret"]
    assert "secret" not in _row(user_id)
    assert _event_types() == ["TechnicalUserCreated", "WalletAccessRequested"]

    step = _step_input(technicalUserId=user_id, outcome="ACTIVE", walletAccountRef="wallet-account-1")
    first = service.apply_wallet_access(step)
    second = service.apply_wallet_access(step)
    assert first == second
    assert first["result"] == {"technicalUserId": user_id, "status": "ACTIVE", "walletAccess": "ACTIVE",
                               "walletAccountRef": "wallet-account-1"}
    assert len(repository.audit_entries()) == 2
    assert len(events.RELAY.log) == 2
    assert all("secret" not in str(entry).lower() for entry in events.RELAY.log + repository.audit_entries())


def test_subscription_creation_is_idempotent_and_splits_provider_roles(c2m3):
    body = _step_input(customerCompanyId=CUSTOMER, providerCompanyId=PROVIDER,
        offerSubscriptionId=SUBSCRIPTION, name="Profile", roles=[
            {"name": "Dataspace Discovery"}, {"name": "Identity Wallet Management"},
            {"name": "BPDM Sharing Output Consumer"},
        ])
    first = service.create_for_subscription(body)
    retry = service.create_for_subscription(body | {"stepRunId": "00000000-0000-4000-8000-000000000003"})
    assert first["result"] == retry["result"]
    assert len(first["result"]["accounts"]) == 2
    customer_account, provider_account = first["result"]["accounts"]
    customer_row = _row(customer_account["technicalUserId"])
    provider_row = _row(provider_account["technicalUserId"])
    assert customer_row["co_viewer_company_id"] == PROVIDER
    assert customer_row["wallet_access"] == "REQUESTED"
    assert provider_row["company_id"] == PROVIDER
    assert provider_row["co_viewer_company_id"] is None
    provider_filtered = service.list_all_technical_users(company_id=PROVIDER)
    assert {item["id"] for item in provider_filtered["items"]} == {provider_row["id"]}
    assert iam.get().roles_for(customer_row["iam_client_id"]) == ["Dataspace Discovery"]
    assert iam.get().roles_for(provider_row["iam_client_id"]) == ["BPDM Sharing Output Consumer"]
    assert service.check_technical_user(id=customer_row["id"], company_id=CUSTOMER)["usableForConnector"] is False
    assert service.check_technical_user(id=customer_row["id"], company_id=CUSTOMER,
                                        offer_subscription_id=SUBSCRIPTION)["usableForConnector"] is True
    assert service.check_technical_user(id=provider_row["id"], company_id=PROVIDER,
                                        offer_subscription_id=SUBSCRIPTION)["usableForConnector"] is False
    assert _event_types().count("TechnicalUserCreated") == 2
    assert _event_types().count("WalletAccessRequested") == 1
    assert "secret" not in str(first).lower()


def test_role_assignment_and_company_readiness_are_enforced(c2m3):
    with pytest.raises(Problem) as role_error:
        _create_own({"name": "Not allowed", "roles": [{"name": "BPDM Sharing Output Consumer"}]})
    assert role_error.value.status == 400
    assert role_error.value.name == "role-not-assignable"

    with pytest.raises(Problem) as company_error:
        service.create_technical_user(company_id="c0000003-0000-4000-8000-000000000003",
            body={"name": "Not ready", "roles": [{"name": "Dataspace Discovery"}]}, actor_sub=ACTOR)
    assert company_error.value.status == 409
    assert company_error.value.name == "company-not-ready"
    assert not repository.find()


def test_create_rejects_undeclared_fields(c2m3):
    with pytest.raises(Problem) as error:
        service.create_technical_user(company_id=CUSTOMER,
            body={"name": "Unexpected", "roles": [{"name": "Dataspace Discovery"}], "extra": True},
            actor_sub=ACTOR)
    assert error.value.status == 400
    assert error.value.name == "validation"
    assert not repository.find()
    assert not iam.get().clients


def test_role_list_queries_work_with_memory_iam(c2m3):
    roles = service.list_technical_roles(lang="en")
    discovery = next(role for role in roles if role["name"] == "Dataspace Discovery")
    wallet = next(role for role in roles if role["name"] == "Identity Wallet Management")
    provider = next(role for role in roles if role["name"] == "BPDM Sharing Output Consumer")
    assert discovery["providerOnly"] is False
    assert wallet["grantsWalletAccess"] is True
    assert provider["providerOnly"] is True

    assignable = service.list_assignable_roles(company_id=CUSTOMER, lang="en")
    assert {role["name"] for role in assignable} == {
        "Dataspace Discovery", "Identity Wallet Management", "Semantic Model Management",
    }


def test_osp_company_standin_includes_all_framework_roles(c2m3):
    roles = service.list_assignable_roles(company_id=OSP_COMPANY)
    assert {role["name"] for role in roles} == {
        "BPDM Sharing Input Consumer", "BPDM Sharing Output Consumer", "Dataspace Discovery",
        "Identity Wallet Management", "Semantic Model Management",
    }


def test_company_and_subscription_deactivation_preserve_final_state(c2m3):
    own = _create_own()
    own_client = _row(own["id"])["iam_client_id"]
    disabled = service.disable_company_technical_users(_step_input(companyId=CUSTOMER))
    assert disabled["result"]["technicalUserIds"] == [own["id"]]
    assert _row(own["id"])["disabled"] is True
    assert iam.get().client(own_client)["enabled"] is False
    audit_count = len(repository.audit_entries())
    assert service.disable_company_technical_users(_step_input(companyId=CUSTOMER)) == disabled
    assert len(repository.audit_entries()) == audit_count
    service.enable_company_technical_users(_step_input(companyId=CUSTOMER))
    assert _row(own["id"])["disabled"] is False
    assert iam.get().client(own_client)["enabled"] is True

    subscription = _subscription(["Dataspace Discovery"])
    subscription_id = subscription["result"]["accounts"][0]["technicalUserId"]
    subscription_client = _row(subscription_id)["iam_client_id"]
    service.disable_subscription_technical_users(_step_input(offerSubscriptionId=SUBSCRIPTION))
    assert _row(subscription_id)["status"] == "INACTIVE"
    service.disable_company_technical_users(_step_input(companyId=CUSTOMER))
    service.enable_company_technical_users(_step_input(companyId=CUSTOMER))
    assert _row(subscription_id)["disabled"] is False
    assert iam.get().client(subscription_client)["enabled"] is False


def test_delete_without_wallet_and_wallet_removal_step(c2m3):
    own = _create_own()
    own_client = _row(own["id"])["iam_client_id"]
    status_code, body = service.delete_technical_user(id=own["id"], company_id=CUSTOMER, actor_sub=ACTOR)
    assert status_code == 204
    assert body is None
    assert _row(own["id"])["status"] == "DELETED"
    assert iam.get().client(own_client) is None

    wallet_user = _create_own({"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]})
    service.apply_wallet_access(_step_input(technicalUserId=wallet_user["id"], outcome="ACTIVE",
                                             walletAccountRef="wallet-account-2"))
    status_code, body = service.delete_technical_user(id=wallet_user["id"], company_id=CUSTOMER, actor_sub=ACTOR)
    assert status_code == 202
    assert body["status"] == "PENDING_DELETION"
    deleted = service.delete(_step_input(technicalUserId=wallet_user["id"]))
    assert deleted["result"] == {"technicalUserId": wallet_user["id"], "status": "DELETED", "walletAccess": "NONE",
                                 "walletAccountRef": None}
    assert service.delete(_step_input(technicalUserId=wallet_user["id"])) == deleted
    assert _event_types().count("TechnicalUserDeleted") == 2


def test_update_rotate_and_delete_respect_owner_and_co_viewer(c2m3):
    account = _subscription(["Dataspace Discovery"])["result"]["accounts"][0]["technicalUserId"]
    own = _create_own()

    with pytest.raises(Problem) as error:
        service.update_technical_user(id=account, company_id=PROVIDER, body={"name": "x"}, actor_sub=ACTOR)
    assert (error.value.status, error.value.name) == (403, "not-owner")
    with pytest.raises(Problem) as error:
        service.rotate_credentials(id=account, company_id=PROVIDER, actor_sub=ACTOR)
    assert (error.value.status, error.value.name) == (403, "not-owner")
    with pytest.raises(Problem) as error:
        service.rotate_credentials(id=own["id"], company_id=PROVIDER, actor_sub=ACTOR)
    assert (error.value.status, error.value.name) == (404, "not-found")
    with pytest.raises(Problem) as error:
        service.delete_technical_user(id=own["id"], company_id=PROVIDER, actor_sub=ACTOR)
    assert error.value.status == 404

    assert service.update_technical_user(id=own["id"], company_id=CUSTOMER, body={"name": "New"},
                                         actor_sub=ACTOR)["name"] == "New"
    assert service.rotate_credentials(id=own["id"], company_id=CUSTOMER, actor_sub=ACTOR)["secret"]
    status_code, _ = service.delete_technical_user(id=account, company_id=PROVIDER, actor_sub=ACTOR)
    assert status_code == 204


def test_update_changes_roles_but_never_the_wallet_role(c2m3):
    own = _create_own()
    updated = service.update_technical_user(id=own["id"], company_id=CUSTOMER, actor_sub=ACTOR,
                                            body={"roles": [{"name": "Semantic Model Management"}]})
    assert [role["name"] for role in updated["roles"]] == ["Semantic Model Management"]
    assert [(entry["role_name"], entry["action"]) for entry in repository.role_assignment_entries()] == [
        ("Dataspace Discovery", "ADDED"), ("Semantic Model Management", "ADDED"),
        ("Dataspace Discovery", "REMOVED")]
    with pytest.raises(Problem) as error:
        service.update_technical_user(id=own["id"], company_id=CUSTOMER, actor_sub=ACTOR,
                                      body={"roles": [{"name": "Identity Wallet Management"}]})
    assert (error.value.status, error.value.name) == (409, "wallet-role-change")


def test_subscription_account_without_wallet_role_is_active(c2m3):
    account = _subscription(["Dataspace Discovery"])["result"]["accounts"][0]
    assert (account["status"], account["walletAccess"]) == ("ACTIVE", "NONE")
    assert _event_types() == ["TechnicalUserCreated"]


def test_subscription_step_requires_business_keys(c2m3):
    body = _step_input(customerCompanyId=CUSTOMER, name="Profile", roles=[{"name": "Dataspace Discovery"}])
    with pytest.raises(Problem) as error:
        service.create_for_subscription(body)
    assert (error.value.status, error.value.name) == (400, "validation")
    assert not repository.find()


def test_company_step_without_company_id_changes_nothing(c2m3):
    _create_own()
    with pytest.raises(Problem) as error:
        service.disable_company_technical_users(_step_input())
    assert error.value.status == 400
    assert repository.find(disabled=True) == []


def test_creation_is_cleaned_up_when_the_iam_fails(c2m3, monkeypatch):
    monkeypatch.setattr(iam.get(), "secret", lambda client_id: (_ for _ in ()).throw(IamError("boom")))
    with pytest.raises(Problem) as error:
        _create_own()
    assert (error.value.status, error.value.name, error.value.ext["retryable"]) == (502, "iam-error", True)
    assert not repository.find()
    assert not iam.get().clients
    assert not events.RELAY.log


def test_repository_hands_out_copies_and_rolls_a_transaction_back(c2m3):
    own = _create_own()
    row = _row(own["id"])
    row["name"] = "changed without save"
    assert _row(own["id"])["name"] == "Build agent"

    with pytest.raises(RuntimeError):
        with repository.transaction():
            row["name"] = "rolled back"
            repository.save(row)
            raise RuntimeError("fails")
    assert _row(own["id"])["name"] == "Build agent"
    assert repository.next_client_id("sa") != row["iam_client_id"]


def test_a_subscription_has_one_account_per_party(c2m3):
    account = _subscription(["Dataspace Discovery"])["result"]["accounts"][0]["technicalUserId"]
    duplicate = _row(account) | {"id": "other-id"}
    with pytest.raises(ValueError):
        repository.save(duplicate)
    repository.save(duplicate | {"status": "DELETED"})   # a deleted account does not count


def test_client_is_removed_when_saving_the_account_fails(c2m3, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("database down")
    monkeypatch.setattr("modules.c2_m3.services.audit.record", fail)
    with pytest.raises(RuntimeError):
        _create_own()
    assert not repository.find()
    assert not iam.get().clients
    assert not events.RELAY.log


def test_subscription_accounts_may_change_roles_outside_the_company_roles(c2m3):
    result = _subscription(["Dataspace Discovery", "BPDM Sharing Output Consumer"])
    provider = result["result"]["accounts"][1]["technicalUserId"]
    updated = service.update_technical_user(id=provider, company_id=PROVIDER, actor_sub=ACTOR,
                                            body={"roles": [{"name": "BPDM Pool Consumer"}]})
    assert [role["name"] for role in updated["roles"]] == ["BPDM Pool Consumer"]


def test_unreachable_iam_on_the_roles_query_is_an_upstream_error(c2m3, monkeypatch):
    monkeypatch.setattr(iam.get(), "list_roles", lambda lang=None: (_ for _ in ()).throw(IamError("down")))
    with pytest.raises(Problem) as error:
        service.list_technical_roles(lang="en")
    assert (error.value.status, error.value.name, error.value.ext["retryable"]) == (502, "upstream-error", True)


def test_process_stub_replays_the_wallet_flows(c2m3, monkeypatch):
    wallet = _create_own({"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]})
    requested = next(event for event in events.RELAY.log if event["type"] == "WalletAccessRequested")

    service.handle_event(requested)
    assert _row(wallet["id"])["wallet_access"] == "REQUESTED"   # PROCESS_STUB is off by default

    monkeypatch.setenv("PROCESS_STUB", "true")
    service.handle_event(requested)
    service.handle_event(requested)
    row = _row(wallet["id"])
    assert (row["status"], row["wallet_access"], row["wallet_account_ref"]) == ("ACTIVE", "ACTIVE", f"stub-{wallet['id']}")
    assert len(repository.audit_entries()) == 2

    status_code, _ = service.delete_technical_user(id=wallet["id"], company_id=CUSTOMER, actor_sub=ACTOR)
    assert status_code == 202
    removal = next(event for event in events.RELAY.log if event["type"] == "WalletAccessRemovalRequested")
    service.handle_event(removal)
    service.handle_event(removal)
    assert _row(wallet["id"])["status"] == "DELETED"
    assert _event_types().count("TechnicalUserDeleted") == 1
