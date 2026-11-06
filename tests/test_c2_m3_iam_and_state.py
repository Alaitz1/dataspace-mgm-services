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
"""C2-M3 status rules (README 6.1, 6.2) and the Keycloak adapter (README 6.6, 11.1) against a fake Keycloak."""
from __future__ import annotations

import httpx
import pytest

from modules.c2_m3.iam import keycloak
from modules.c2_m3.iam.port import IamError
from modules.c2_m3.models import Origin, Status, SubscriptionParty, WalletAccess
from modules.c2_m3.services import state
from portal_common.problems import Problem


def _row(**values) -> dict:
    row = {"id": "u1", "company_id": "c1", "co_viewer_company_id": None, "origin": Origin.OWN,
           "subscription_party": None, "offer_subscription_id": None, "iam_client_uuid": "k1",
           "status": Status.ACTIVE, "wallet_access": WalletAccess.NONE, "wallet_account_ref": None,
           "disabled": False}
    return row | values


def _problem(function, *args) -> tuple[int, str]:
    with pytest.raises(Problem) as error:
        function(*args)
    return error.value.status, error.value.name


def test_creation_status_depends_on_the_wallet_role():
    row = _row(status=Status.PENDING)
    state.after_creation(row, wallet_requested=True)
    assert (row["status"], row["wallet_access"]) == (Status.PENDING, WalletAccess.REQUESTED)
    state.after_creation(row, wallet_requested=False)
    assert (row["status"], row["wallet_access"]) == (Status.ACTIVE, WalletAccess.NONE)


def test_changes_and_rotation_need_an_active_enabled_account():
    assert _problem(state.require_changeable, _row(status=Status.PENDING)) == (409, "invalid-state")
    assert _problem(state.require_changeable, _row(disabled=True)) == (409, "invalid-state")
    state.require_rotatable(_row(status=Status.PENDING))
    assert _problem(state.require_rotatable, _row(iam_client_uuid=None)) == (409, "invalid-state")
    assert _problem(state.require_rotatable, _row(status=Status.INACTIVE)) == (409, "invalid-state")


def test_delete_rules():
    assert _problem(state.require_deletable, _row(wallet_access=WalletAccess.REQUESTED)) == (409, "wallet-in-progress")
    assert _problem(state.require_deletable, _row(status=Status.PENDING)) == (409, "invalid-state")
    state.require_deletable(_row(status=Status.INACTIVE, disabled=True))
    row = _row(wallet_access=WalletAccess.ACTIVE, wallet_account_ref="w1")
    assert state.needs_wallet_removal(row)
    state.request_removal(row)
    assert (row["status"], row["wallet_access"]) == (Status.PENDING_DELETION, WalletAccess.REMOVING)
    state.require_removal_pending(row)
    state.mark_deleted(row)
    assert (row["status"], row["wallet_access"], row["wallet_account_ref"]) == (Status.DELETED, WalletAccess.NONE, None)


def test_wallet_outcome_is_applied_once():
    row = _row(status=Status.PENDING, wallet_access=WalletAccess.REQUESTED)
    assert state.apply_wallet_outcome(row, "ACTIVE", "w1") is True
    assert (row["status"], row["wallet_access"], row["wallet_account_ref"]) == (
        Status.ACTIVE, WalletAccess.ACTIVE, "w1")
    assert state.apply_wallet_outcome(row, "ACTIVE", "w1") is False
    assert _problem(state.apply_wallet_outcome, row, "ACTIVE", "w2") == (409, "invalid-state")
    assert _problem(state.apply_wallet_outcome, row, "FAILED", None) == (409, "invalid-state")
    failed = _row(wallet_access=WalletAccess.REQUESTED, status=Status.INACTIVE)
    assert state.apply_wallet_outcome(failed, "FAILED", None) is True
    assert (failed["status"], failed["wallet_access"]) == (Status.INACTIVE, WalletAccess.FAILED)


def test_disabling_and_enabling_report_changes_only():
    row = _row()
    assert state.disable(row) is True and state.disable(row) is False
    assert state.enable(row) is True and state.enable(row) is False
    assert state.client_enabled_after_enable(_row(status=Status.INACTIVE)) is False


def test_connector_usability_rules():
    assert state.usable_for_connector(_row(), "c1", None) is True
    assert state.usable_for_connector(_row(), "c2", None) is False
    assert state.usable_for_connector(_row(disabled=True), "c1", None) is False
    assert state.usable_for_connector(_row(status=Status.INACTIVE), "c1", None) is False
    customer = _row(origin=Origin.SUBSCRIPTION, subscription_party=SubscriptionParty.CUSTOMER,
                    offer_subscription_id="s1")
    assert state.usable_for_connector(customer, "c1", None) is False
    assert state.usable_for_connector(customer, "c1", "s1") is True
    assert state.usable_for_connector(customer | {"subscription_party": SubscriptionParty.PROVIDER}, "c1", "s1") is False


class FakeKeycloak:
    """Just enough of the Admin REST API for one technical user; records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.bodies: dict[tuple[str, str], object] = {}
        self.tokens = 0
        self.reject_next_admin_call = False
        self.client_exists = False
        self.delete_status = 204
        self.uuid = "k1"                 # internal ID of the client in this fake
        self.user = "u1"                 # its service account user
        self.roles = "rc"                # the client with the technical user roles
        self.gone: set[str] = set()      # internal IDs of clients and users that Keycloak no longer knows (404)

    def __call__(self, method: str, url: str, **kwargs) -> httpx.Response:
        if url.endswith("/protocol/openid-connect/token"):
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"token-{self.tokens}", "expires_in": 300})
        if self.reject_next_admin_call:
            self.reject_next_admin_call = False
            return httpx.Response(401)
        path = "/" + url.split("/admin/realms/", 1)[1].split("/", 1)[1]
        key = (method, path)
        self.calls.append(key)
        self.bodies[key] = kwargs.get("json")
        segments = path.split("/")
        if len(segments) > 2 and segments[1] in ("clients", "users") and segments[2] in self.gone:
            return httpx.Response(404)
        wanted = (kwargs.get("params") or {}).get("clientId")
        if key == ("GET", "/clients"):
            if wanted == "technical_roles_management":
                return httpx.Response(200, json=[{"id": self.roles}])
            return httpx.Response(200, json=[{"id": self.uuid, "clientId": wanted}] if self.client_exists else [])
        if key == ("POST", "/clients"):
            self.client_exists = True
            return httpx.Response(201)
        if method == "DELETE" and path == f"/clients/{self.uuid}":
            return httpx.Response(self.delete_status)
        responses = {
            ("GET", f"/clients/{self.roles}/roles"): [
                {"name": "Dataspace Discovery", "description": "d", "attributes": {}}],
            ("GET", f"/clients/{self.uuid}/service-account-user"): {"id": self.user},
            ("GET", f"/users/{self.user}"): {"id": self.user, "attributes": {}},
            ("GET", f"/users/{self.user}/role-mappings/clients/{self.roles}"): [],
            ("GET", f"/clients/{self.roles}/roles/Dataspace%20Discovery"): {"id": "r1", "name": "Dataspace Discovery"},
            ("GET", f"/clients/{self.uuid}"): {"id": self.uuid, "enabled": True},
            ("GET", f"/clients/{self.uuid}/client-secret"): {"value": "s3cret"},
            ("POST", f"/clients/{self.uuid}/client-secret"): {"value": "rotated"},
        }
        return httpx.Response(200, json=responses.get(key, {}))


@pytest.fixture
def fake(monkeypatch):
    fake = FakeKeycloak()
    monkeypatch.setattr(keycloak.http, "request", fake)
    monkeypatch.setenv("IAM_URL", "http://keycloak.test/auth")
    return fake


def test_client_is_created_in_the_documented_order(fake):
    created = keycloak.KeycloakIAM().create_or_complete(
        "sa1", name="Agent", description=None, company_id="c1", bpn="BPNL1", roles=["Dataspace Discovery"])
    assert created == {"id": "k1", "clientId": "sa1", "serviceAccountUserId": "u1", "name": "Agent",
                       "description": None, "enabled": True}
    order = [call for call in fake.calls if call[0] in ("POST", "PUT") or call[1].endswith("service-account-user")]
    assert order == [("POST", "/clients"), ("GET", "/clients/k1/service-account-user"), ("PUT", "/users/u1"),
                     ("POST", "/users/u1/role-mappings/clients/rc")]
    client = fake.bodies[("POST", "/clients")]
    assert client["optionalClientScopes"] == []
    assert client["defaultClientScopes"] == ["basic", "roles", "catena", "technical-roles"]
    assert client["serviceAccountsEnabled"] is True and client["fullScopeAllowed"] is False
    assert fake.bodies[("PUT", "/users/u1")]["attributes"] == {"company_id": ["c1"], "bpn": ["BPNL1"]}


def test_an_existing_client_is_completed_not_created_again(fake):
    fake.client_exists = True
    keycloak.KeycloakIAM().create_or_complete(
        "sa1", name="Agent", description=None, company_id="c1", bpn="BPNL1", roles=[])
    assert ("POST", "/clients") not in fake.calls


def test_unknown_role_is_rejected_before_anything_is_written(fake):
    with pytest.raises(keycloak.UnknownRole):
        keycloak.KeycloakIAM().create_or_complete(
            "sa1", name="Agent", description=None, company_id="c1", bpn="BPNL1", roles=["Nope"])
    assert not [call for call in fake.calls if call[0] != "GET"]


def test_an_expired_admin_token_is_replaced_once(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    fake.reject_next_admin_call = True
    assert adapter.secret("sa1") == "s3cret"
    assert fake.tokens == 2


def test_lookups_are_cached_per_adapter(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    adapter.secret("sa1")
    adapter.secret("sa1")
    assert fake.calls.count(("GET", "/clients")) == 1
    assert fake.tokens == 1


def test_deleting_a_client_that_is_already_gone_counts_as_deleted(fake):
    fake.client_exists, fake.delete_status = True, 404
    keycloak.KeycloakIAM().delete("sa1")
    assert ("DELETE", "/clients/k1") in fake.calls


def test_other_iam_failures_are_reported(fake):
    fake.client_exists, fake.delete_status = True, 500
    with pytest.raises(IamError):
        keycloak.KeycloakIAM().delete("sa1")


def _recreated(fake) -> None:
    """The client was deleted and created again outside the module: same client ID, new IDs (client and user)."""
    fake.gone |= {fake.uuid, fake.user}
    fake.uuid, fake.user = "k2", "u2"


def test_a_stale_client_id_is_forgotten_and_the_call_retried_once(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    assert adapter.secret("sa1") == "s3cret"
    _recreated(fake)
    assert adapter.rotate_secret("sa1") == "rotated"
    assert fake.calls.count(("GET", "/clients")) == 2   # the first lookup and the one after the 404
    assert ("POST", "/clients/k2/client-secret") in fake.calls


def test_a_stale_service_account_is_dropped_with_its_client(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    assert adapter.roles_for("sa1") == []
    _recreated(fake)
    assert adapter.roles_for("sa1") == []
    assert ("GET", "/clients/k2/service-account-user") in fake.calls
    assert ("GET", "/users/u2/role-mappings/clients/rc") in fake.calls


def test_a_client_that_is_gone_for_good_is_reported_not_retried_forever(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    adapter.secret("sa1")
    fake.gone.add(fake.uuid)   # not recreated: the lookup still names the same, now unknown, ID
    with pytest.raises(IamError):
        adapter.secret("sa1")
    assert fake.calls.count(("GET", "/clients/k1/client-secret")) == 3   # first call, then twice after the 404


def test_a_stale_roles_client_is_looked_up_again(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    assert [role["name"] for role in adapter.list_roles()] == ["Dataspace Discovery"]
    fake.gone.add("rc")
    fake.roles = "rc2"   # the roles client was recreated under a new internal ID
    assert [role["name"] for role in adapter.list_roles()] == ["Dataspace Discovery"]
    assert ("GET", "/clients/rc2/roles") in fake.calls


def test_delete_with_a_stale_id_removes_the_recreated_client(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    adapter.secret("sa1")
    _recreated(fake)
    adapter.delete("sa1")
    assert ("DELETE", "/clients/k2") in fake.calls


def test_delete_of_a_client_that_vanished_is_not_an_error(fake):
    fake.client_exists = True
    adapter = keycloak.KeycloakIAM()
    adapter.secret("sa1")
    fake.gone.add(fake.uuid)
    fake.client_exists = False
    adapter.delete("sa1")
    assert not [call for call in fake.calls if call[0] == "DELETE" and call[1] == "/clients/k2"]
