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
"""HTTP layer of C2-M3 Technical Users: token, permission and company scope, then the interface function."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, Response

from portal_common import spec, standin
from portal_common.problems import route_class

from . import interface
from .interface import MODULE
from .models import Origin, Status, WalletAccess
from .services import handle_event

router = APIRouter(prefix=spec.module(MODULE).base_path, route_class=route_class(MODULE), tags=[MODULE])

COMPANY = "/companies/{companyId}/technical-users"
ACCOUNT = COMPANY + "/{id}"
LANG = Query("de", pattern="^[a-z]{2}$")


def reset() -> None:
    interface.reset()


def on_event(event: dict) -> None:
    """Replays the wallet flows when `PROCESS_STUB=true` (README 11.3); every other event is ignored."""
    handle_event(event)


def _perm(method: str, path: str):
    return standin.perm(MODULE, method, path)


def _scoped(claims: dict, company_id: str) -> str:
    """Scope `company` (README 6.4 step 3): the token's company must be the company of the path; returns `sub`."""
    standin.company_scope(MODULE, claims, company_id)
    return claims["sub"]


# -- technical users of the company (`assignable-roles` is declared before `{id}`) -------------
@router.get(COMPANY, summary="List the technical users visible to the company")
def list_technical_users(companyId: str, page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100),
                         status: list[Status] | None = Query(None), origin: Origin | None = None,
                         walletAccess: WalletAccess | None = None, claims: dict = _perm("GET", COMPANY)):
    _scoped(claims, companyId)
    return interface.list_technical_users(company_id=companyId, page=page, size=size, status=status,
                                          origin=origin, wallet_access=walletAccess)


@router.post(COMPANY, status_code=201, summary="Create a technical user")
def create_technical_user(companyId: str, body: dict = Body(...), claims: dict = _perm("POST", COMPANY)):
    sub = _scoped(claims, companyId)
    return interface.create_technical_user(company_id=companyId, body=body, actor_sub=sub)


@router.get(COMPANY + "/assignable-roles", summary="Roles that the company can assign")
def list_assignable_roles(companyId: str, lang: str = LANG, claims: dict = _perm("GET", COMPANY + "/assignable-roles")):
    _scoped(claims, companyId)
    return interface.list_assignable_roles(company_id=companyId, lang=lang)


@router.get(ACCOUNT, summary="Details of a technical user")
def get_technical_user(companyId: str, id: str, claims: dict = _perm("GET", ACCOUNT)):
    _scoped(claims, companyId)
    return interface.get_technical_user(id=id, company_id=companyId)


@router.patch(ACCOUNT, summary="Change name, description or roles")
def update_technical_user(companyId: str, id: str, body: dict = Body(...), claims: dict = _perm("PATCH", ACCOUNT)):
    sub = _scoped(claims, companyId)
    return interface.update_technical_user(id=id, company_id=companyId, body=body, actor_sub=sub)


@router.delete(ACCOUNT, status_code=204, summary="Delete a technical user")
def delete_technical_user(companyId: str, id: str, claims: dict = _perm("DELETE", ACCOUNT)):
    sub = _scoped(claims, companyId)
    status_code, account = interface.delete_technical_user(id=id, company_id=companyId, actor_sub=sub)
    if status_code == 202:
        return JSONResponse(account, status_code=202)
    return Response(status_code=204)


@router.post(ACCOUNT + "/credentials/rotate", summary="Create a new secret")
def rotate_credentials(companyId: str, id: str, claims: dict = _perm("POST", ACCOUNT + "/credentials/rotate")):
    sub = _scoped(claims, companyId)
    return interface.rotate_credentials(id=id, company_id=companyId, actor_sub=sub)


# -- technical users of all companies (OSP staff) -----------------------------------------------
@router.get("/osp/technical-users", summary="List the technical users of all companies")
def list_all_technical_users(page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100),
                             companyId: str | None = None, status: list[Status] | None = Query(None),
                             origin: Origin | None = None, walletAccess: WalletAccess | None = None,
                             disabled: bool | None = None, _: dict = _perm("GET", "/osp/technical-users")):
    return interface.list_all_technical_users(page=page, size=size, company_id=companyId, status=status,
                                              origin=origin, wallet_access=walletAccess, disabled=disabled)


@router.get("/osp/technical-users/{id}", summary="Details of any technical user")
def get_any_technical_user(id: str, _: dict = _perm("GET", "/osp/technical-users/{id}")):
    return interface.get_any_technical_user(id=id)


# -- queries for other modules ----------------------------------------------------------------
@router.get("/internal/technical-users/{id}", summary="Can the account be used for a connector?")
def check_technical_user(id: str, companyId: str, offerSubscriptionId: str | None = None,
                         _: dict = _perm("GET", "/internal/technical-users/{id}")):
    return interface.check_technical_user(id=id, companyId=companyId, offerSubscriptionId=offerSubscriptionId)


@router.post("/internal/technical-users/{id}/credentials/rotate", summary="Rotate a subscription account's secret")
def rotate_subscription_credentials(id: str, body: dict = Body(...),
                                    _: dict = _perm("POST", "/internal/technical-users/{id}/credentials/rotate")):
    return interface.rotate_subscription_credentials(id=id, offerSubscriptionId=body.get("offerSubscriptionId"))


@router.get("/internal/technical-roles", summary="All technical user roles")
def list_technical_roles(lang: str = LANG, _: dict = _perm("GET", "/internal/technical-roles")):
    return interface.list_technical_roles(lang=lang)


# -- steps for Process Orchestration ------------------------------------------------------------
def _register_step(name: str, function: Callable[[dict], dict]) -> None:
    path = f"/steps/{name}"

    def endpoint(body: dict = Body(...), _: dict = _perm("POST", path)):
        return function(body)

    endpoint.__name__ = "step_" + name.replace("-", "_")
    router.add_api_route(path, endpoint, methods=["POST"], summary=f"Step: {name}")


for _name, _function in {
    "create-for-subscription": interface.create_for_subscription,
    "apply-wallet-access": interface.apply_wallet_access,
    "delete": interface.delete,
    "disable-company-technical-users": interface.disable_company_technical_users,
    "enable-company-technical-users": interface.enable_company_technical_users,
    "disable-subscription-technical-users": interface.disable_subscription_technical_users,
}.items():
    _register_step(_name, _function)
