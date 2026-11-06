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

import pytest

from modules.c2_m3 import iam, service
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


def test_own_creation_and_wallet_step_are_idempotent(c2m3):
    created = _create_own({"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]})
    user_id = created["id"]
    assert created["status"] == "PENDING"
    assert created["walletAccess"] == "REQUESTED"
    assert created["credentials"]["secret"]
    assert "secret" not in service.technical_users[user_id]
    assert [event["type"] for event in events.RELAY.log] == ["TechnicalUserCreated", "WalletAccessRequested"]

    step = _step_input(technicalUserId=user_id, outcome="ACTIVE", walletAccountRef="wallet-account-1")
    first = service.apply_wallet_access(step)
    second = service.apply_wallet_access(step)
    assert first == second
    assert first["result"] == {"technicalUserId": user_id, "status": "ACTIVE", "walletAccess": "ACTIVE",
                               "walletAccountRef": "wallet-account-1"}
    assert len(service.audit_log) == 2
    assert len(events.RELAY.log) == 2
    assert all("secret" not in str(entry).lower() for entry in events.RELAY.log + service.audit_log)


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
    customer_row = service.technical_users[customer_account["technicalUserId"]]
    provider_row = service.technical_users[provider_account["technicalUserId"]]
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
    assert [event["type"] for event in events.RELAY.log].count("TechnicalUserCreated") == 2
    assert [event["type"] for event in events.RELAY.log].count("WalletAccessRequested") == 1
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
    assert not service.technical_users


def test_create_rejects_undeclared_fields(c2m3):
    with pytest.raises(Problem) as error:
        service.create_technical_user(company_id=CUSTOMER,
            body={"name": "Unexpected", "roles": [{"name": "Dataspace Discovery"}], "extra": True},
            actor_sub=ACTOR)
    assert error.value.status == 400
    assert error.value.name == "validation"
    assert not service.technical_users
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
    own_row = service.technical_users[own["id"]]
    disabled = service.disable_company_technical_users(_step_input(companyId=CUSTOMER))
    assert disabled["result"]["technicalUserIds"] == [own["id"]]
    assert own_row["disabled"] is True
    assert iam.get().client(own_row["iam_client_id"])["enabled"] is False
    audit_count = len(service.audit_log)
    assert service.disable_company_technical_users(_step_input(companyId=CUSTOMER)) == disabled
    assert len(service.audit_log) == audit_count
    service.enable_company_technical_users(_step_input(companyId=CUSTOMER))
    assert own_row["disabled"] is False
    assert iam.get().client(own_row["iam_client_id"])["enabled"] is True

    subscription = service.create_for_subscription(_step_input(customerCompanyId=CUSTOMER, providerCompanyId=PROVIDER,
        offerSubscriptionId=SUBSCRIPTION, name="Profile", roles=[{"name": "Dataspace Discovery"}]))
    subscription_id = subscription["result"]["accounts"][0]["technicalUserId"]
    subscription_row = service.technical_users[subscription_id]
    service.disable_subscription_technical_users(_step_input(offerSubscriptionId=SUBSCRIPTION))
    assert subscription_row["status"] == "INACTIVE"
    service.disable_company_technical_users(_step_input(companyId=CUSTOMER))
    service.enable_company_technical_users(_step_input(companyId=CUSTOMER))
    assert subscription_row["disabled"] is False
    assert iam.get().client(subscription_row["iam_client_id"])["enabled"] is False


def test_delete_without_wallet_and_wallet_removal_step(c2m3):
    own = _create_own()
    own_row = service.technical_users[own["id"]]
    status_code, body = service.delete_technical_user(id=own["id"], company_id=CUSTOMER, actor_sub=ACTOR)
    assert status_code == 204
    assert body is None
    assert own_row["status"] == "DELETED"
    assert iam.get().client(own_row["iam_client_id"]) is None

    wallet_user = _create_own({"name": "Wallet client", "roles": [{"name": "Identity Wallet Management"}]})
    service.apply_wallet_access(_step_input(technicalUserId=wallet_user["id"], outcome="ACTIVE",
                                             walletAccountRef="wallet-account-2"))
    status_code, body = service.delete_technical_user(id=wallet_user["id"], company_id=CUSTOMER, actor_sub=ACTOR)
    assert status_code == 202
    assert body["status"] == "PENDING_DELETION"
    deleted = service.delete(_step_input(technicalUserId=wallet_user["id"]))
    assert deleted["result"] == {"technicalUserId": wallet_user["id"], "status": "DELETED"}
    assert service.delete(_step_input(technicalUserId=wallet_user["id"])) == deleted
    assert [event["type"] for event in events.RELAY.log].count("TechnicalUserDeleted") == 2

def test_update_rotate_and_delete_respect_owner_and_co_viewer(c2m3):
    body = _step_input(customerCompanyId=CUSTOMER, providerCompanyId=PROVIDER,
        offerSubscriptionId=SUBSCRIPTION, name="Profile", roles=[{"name": "Dataspace Discovery"}])
    account = service.create_for_subscription(body)["result"]["accounts"][0]["technicalUserId"]
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


def test_subscription_account_without_wallet_role_is_active(c2m3):
    result = service.create_for_subscription(_step_input(customerCompanyId=CUSTOMER, providerCompanyId=PROVIDER,
        offerSubscriptionId=SUBSCRIPTION, name="Profile", roles=[{"name": "Dataspace Discovery"}]))
    account = result["result"]["accounts"][0]
    assert (account["status"], account["walletAccess"]) == ("ACTIVE", "NONE")
    assert [event["type"] for event in events.RELAY.log] == ["TechnicalUserCreated"]


def test_subscription_step_requires_business_keys(c2m3):
    body = _step_input(customerCompanyId=CUSTOMER, name="Profile", roles=[{"name": "Dataspace Discovery"}])
    with pytest.raises(Problem) as error:
        service.create_for_subscription(body)
    assert (error.value.status, error.value.name) == (400, "validation")
    assert not service.technical_users
