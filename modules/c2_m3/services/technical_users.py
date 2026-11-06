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

import datetime as dt
import json
import os
import uuid
from pathlib import Path

from portal_common import events, neighbours, standin, tokens
from portal_common.problems import Problem

from modules.c2_m3 import iam as iam_adapter
from modules.c2_m3.models import AuditLogRecord, RoleAssignmentLogRecord, TechnicalUserRecord
from modules.c2_m3.repository import repository

MODULE = "c2-m3"
_DATASPACE_DISCOVERY = "Dataspace Discovery"
_IDENTITY_WALLET_MANAGEMENT = "Identity Wallet Management"
_SEMANTIC_MODEL_MANAGEMENT = "Semantic Model Management"
_BPDM_SHARING_INPUT_CONSUMER = "BPDM Sharing Input Consumer"
_BPDM_SHARING_OUTPUT_CONSUMER = "BPDM Sharing Output Consumer"
_DEFAULT_PROVIDER_ROLES = (
    "BPDM Pool Consumer", _BPDM_SHARING_OUTPUT_CONSUMER, "BPDM Sharing Input Manager",
)
technical_users: dict[str, TechnicalUserRecord] = repository.technical_users
audit_log: list[AuditLogRecord] = repository.audit_log
role_assignment_log: list[RoleAssignmentLogRecord] = repository.role_assignment_log
_lock = repository.lock

__all__ = [
    "MODULE", "audit_log", "apply_wallet_access", "check_technical_user", "create_for_subscription",
    "create_technical_user", "delete", "delete_technical_user", "disable_company_technical_users",
    "disable_subscription_technical_users", "enable_company_technical_users", "get_any_technical_user",
    "get_technical_user", "list_all_technical_users", "list_assignable_roles", "list_technical_roles",
    "list_technical_users", "reset", "role_assignment_log", "rotate_credentials",
    "rotate_subscription_credentials", "technical_users", "update_technical_user",
]

_DEFAULT_ROLE_ASSIGNMENTS = {
    "ACTIVE_PARTICIPANT": [_DATASPACE_DISCOVERY, _IDENTITY_WALLET_MANAGEMENT, _SEMANTIC_MODEL_MANAGEMENT],
    "APP_PROVIDER": [_BPDM_SHARING_INPUT_CONSUMER, _BPDM_SHARING_OUTPUT_CONSUMER, _DATASPACE_DISCOVERY,
                     _IDENTITY_WALLET_MANAGEMENT, _SEMANTIC_MODEL_MANAGEMENT],
    "SERVICE_PROVIDER": [_BPDM_SHARING_INPUT_CONSUMER, _BPDM_SHARING_OUTPUT_CONSUMER, _DATASPACE_DISCOVERY,
                         _IDENTITY_WALLET_MANAGEMENT, _SEMANTIC_MODEL_MANAGEMENT],
    "ONBOARDING_SERVICE_PROVIDER": [],
}


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def reset() -> None:
    repository.reset()
    iam_adapter.reset()


def _wallet_roles() -> set[str]:
    return {role.strip() for role in os.environ.get("WALLET_ROLES", _IDENTITY_WALLET_MANAGEMENT).split(",")
            if role.strip()}


def _provider_roles() -> set[str]:
    default = ",".join(_DEFAULT_PROVIDER_ROLES)
    return {role.strip() for role in os.environ.get("PROVIDER_ONLY_ROLES", default).split(",") if role.strip()}


def _role_assignments() -> dict[str, list[str]]:
    configured = os.environ.get("ROLE_ASSIGNMENT_FILE")
    if not configured:
        return _DEFAULT_ROLE_ASSIGNMENTS
    try:
        mapping = json.loads(Path(configured).expanduser().read_text(encoding="utf-8"))
        if not isinstance(mapping, dict):
            raise ValueError("role assignment file must contain an object")
        return {str(role): (value.get("roles", []) if isinstance(value, dict) else value)
                for role, value in mapping.items()}
    except (OSError, ValueError) as exc:
        raise Problem(MODULE, 502, "upstream-error", detail="ROLE_ASSIGNMENT_FILE could not be read") from exc


def _iam_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Problem:
        raise
    except ValueError as exc:
        raise Problem(MODULE, 400, "role-not-assignable", detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - all IAM failures have the module's public error shape
        raise Problem(MODULE, 502, "iam-error", detail=f"Portal IAM request failed: {type(exc).__name__}",
                      retryable=True) from exc


def _company(company_id: str) -> dict:
    if not company_id:
        raise Problem(MODULE, 404, "not-found")
    if neighbours.is_standin("c3-m1"):
        stub_path = Path(__file__).resolve().parents[1] / "stub-companies.json"
        companies = json.loads(stub_path.read_text(encoding="utf-8"))["companies"]
        company = companies.get(company_id)
    else:
        company = neighbours.query(MODULE, "c3-m1", "query_company", companyId=company_id)
    if not company:
        raise Problem(MODULE, 404, "not-found", retryable=False)
    return company


def _company_ready(company_id: str) -> dict:
    company = _company(company_id)
    if company.get("status") != "ACTIVE" or not company.get("bpn"):
        raise Problem(MODULE, 409, "company-not-ready", retryable=False)
    return company


def _company_role_names(company: dict) -> set[str]:
    names = set()
    for role in company.get("companyRoles") or []:
        if isinstance(role, str):
            names.add(role)
        elif isinstance(role, dict) and role.get("status", "ACTIVE") == "ACTIVE" and role.get("companyRole"):
            names.add(role["companyRole"])
    return names


def _role_names(values, *, required: bool = True) -> list[str]:
    if not isinstance(values, list) or (required and not values):
        raise Problem(MODULE, 400, "validation", detail="roles must be a non-empty array")
    names = [value.get("name") if isinstance(value, dict) else value for value in values]
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise Problem(MODULE, 400, "validation", detail="each role requires a name")
    if len(set(names)) != len(names):
        raise Problem(MODULE, 400, "validation", detail="role names must be unique")
    return names


def _all_roles(lang: str | None = None) -> list[dict]:
    return _iam_call(iam_adapter.get().list_roles, lang)


def _check_roles_exist(roles: list[str]) -> None:
    _iam_call(iam_adapter.get().ensure_roles, roles)


def _assignable_role_names(company_id: str) -> set[str]:
    company = _company(company_id)
    mapping = _role_assignments()
    assignable = set()
    for company_role in _company_role_names(company):
        configured = mapping.get(company_role, [])
        if isinstance(configured, str):
            configured = [configured]
        assignable.update(configured or [])
    return assignable


def _role_views(roles: list[str], lang: str | None = None) -> list[dict]:
    wallet, provider = _wallet_roles(), _provider_roles()
    descriptions = {role["name"]: role.get("description") for role in _all_roles(lang)}
    return [{"name": name, "description": descriptions.get(name), "grantsWalletAccess": name in wallet,
             "providerOnly": name in provider} for name in sorted(roles)]


def list_assignable_roles(*, company_id: str, lang: str | None = None, **_other) -> list[dict]:
    assignable = _assignable_role_names(company_id)
    available = {role["name"] for role in _all_roles(lang)}
    return _role_views(assignable & available, lang)


def list_technical_roles(*, lang: str | None = None, **_other) -> list[dict]:
    roles = [role["name"] for role in _all_roles(lang)]
    return _role_views(roles, lang)


def _client_id() -> str:
    prefix = os.environ.get("TECHNICAL_USER_CLIENT_ID_PREFIX", "sa")
    return repository.next_client_id(prefix)


def _summary(row: dict, viewer_role: str) -> dict:
    return {"id": row["id"], "companyId": row["company_id"], "name": row["name"],
            "description": row["description"], "origin": row["origin"],
            "offerSubscriptionId": row["offer_subscription_id"],
            "subscriptionParty": row["subscription_party"], "coViewerCompanyId": row["co_viewer_company_id"],
            "viewerRole": viewer_role, "status": row["status"], "iamClientId": row["iam_client_id"],
            "walletAccess": row["wallet_access"], "disabled": row["disabled"],
            "createdAt": row["created_at"], "changedAt": row["changed_at"]}


def _details(row: dict, viewer_role: str) -> dict:
    roles = _iam_call(iam_adapter.get().roles_for, row["iam_client_id"]) if row["iam_client_uuid"] else []
    if row["wallet_access"] != "NONE":
        roles = sorted(set(roles) | _wallet_roles())
    result = _summary(row, viewer_role) | {"authMethod": "SECRET", "roles": [{"name": name} for name in roles]}
    if row["wallet_access"] == "ACTIVE":
        result["walletAccountRef"] = row["wallet_account_ref"]
    return result


def _find(user_id: str) -> TechnicalUserRecord:
    row = repository.get(user_id)
    if row is None:
        raise Problem(MODULE, 404, "not-found", retryable=False)
    return row


def _visible(row: dict, company_id: str) -> str:
    if row["company_id"] == company_id:
        return "OWNER"
    if row["co_viewer_company_id"] == company_id:
        return "CO_VIEWER"
    raise Problem(MODULE, 404, "not-found", retryable=False)


def _owned(row: dict, company_id: str) -> None:
    if _visible(row, company_id) != "OWNER":
        raise Problem(MODULE, 403, "not-owner", retryable=False)


def get_technical_user(*, id: str, company_id: str, **_other) -> dict:
    row = _find(id)
    return _details(row, _visible(row, company_id))


def get_any_technical_user(*, id: str, **_other) -> dict:
    return _details(_find(id), "OSP")


def _page(rows: list[dict], *, page: int, size: int) -> dict:
    if page < 0 or size < 1 or size > 100:
        raise Problem(MODULE, 400, "validation", detail="page must be >= 0 and size must be 1..100")
    rows.sort(key=lambda row: row["createdAt"], reverse=True)
    start = page * size
    return {"items": rows[start:start + size], "page": page, "size": size, "total": len(rows)}


def list_technical_users(*, company_id: str, page: int = 0, size: int = 20, status=None,
                         origin: str | None = None, wallet_access: str | None = None, **_other) -> dict:
    statuses = [status] if isinstance(status, str) else status
    if statuses is None:
        statuses = ["PENDING", "ACTIVE", "PENDING_DELETION"]
    rows = []
    for row in technical_users.values():
        if row["company_id"] != company_id and row["co_viewer_company_id"] != company_id:
            continue
        if row["status"] not in statuses or (origin and row["origin"] != origin):
            continue
        if wallet_access and row["wallet_access"] != wallet_access:
            continue
        viewer_role = "OWNER" if row["company_id"] == company_id else "CO_VIEWER"
        rows.append(_summary(row, viewer_role))
    return _page(rows, page=page, size=size)


def list_all_technical_users(*, page: int = 0, size: int = 20, company_id: str | None = None,
                             status=None, origin: str | None = None, wallet_access: str | None = None,
                             disabled: bool | None = None, **_other) -> dict:
    statuses = [status] if isinstance(status, str) else status
    if statuses is None:
        statuses = ["PENDING", "ACTIVE", "PENDING_DELETION"]
    rows = [_summary(row, "OSP") for row in technical_users.values()
            if (company_id is None or row["company_id"] == company_id)
            and row["status"] in statuses and (not origin or row["origin"] == origin)
            and (not wallet_access or row["wallet_access"] == wallet_access)
            and (disabled is None or row["disabled"] is disabled)]
    return _page(rows, page=page, size=size)


def _audit(row: dict, operation: str, *, actor_type: str, actor_sub: str | None = None,
           process_id: str | None = None, step_run_id: str | None = None) -> None:
    repository.add_audit_entry({"id": str(uuid.uuid4()), "occurred_at": _now(), "actor_type": actor_type,
                                "actor_sub": actor_sub, "company_id": row["company_id"],
                                "process_id": process_id, "step_run_id": step_run_id,
                                "operation": operation, "object_id": row["id"]})


def _role_audit(row: dict, role: str, action: str, *, actor_type: str, actor_sub: str | None = None,
                process_id: str | None = None, step_run_id: str | None = None,
                operation: str) -> None:
    repository.add_role_assignment_entry({"id": str(uuid.uuid4()), "occurred_at": _now(),
                                "technical_user_id": row["id"], "company_id": row["company_id"],
                                "iam_client_id": row["iam_client_id"], "role_name": role, "action": action,
                                "actor_type": actor_type, "actor_sub": actor_sub, "process_id": process_id,
                                "step_run_id": step_run_id, "operation": operation})


def _new_row(*, company_id: str, name: str, description: str | None, origin: str,
             offer_subscription_id: str | None = None, subscription_party: str | None = None,
             co_viewer_company_id: str | None = None) -> TechnicalUserRecord:
    client_id = _client_id()
    now = _now()
    row = {"id": str(uuid.uuid4()), "company_id": company_id, "name": name, "description": description,
           "origin": origin, "offer_subscription_id": offer_subscription_id,
           "subscription_party": subscription_party, "co_viewer_company_id": co_viewer_company_id,
           "iam_client_id": client_id, "iam_client_uuid": None, "iam_service_account_user_id": None,
           "status": "PENDING", "wallet_access": "NONE", "wallet_account_ref": None,
           "disabled": False, "created_at": now, "changed_at": now}
    repository.add(row)
    return row


def _change(row: dict) -> None:
    row["changed_at"] = _now()


def _created_event(row: dict) -> None:
    events.publish(MODULE, "TechnicalUserCreated", {
        "technicalUserId": row["id"], "companyId": row["company_id"], "origin": row["origin"],
        "offerSubscriptionId": row["offer_subscription_id"], "subscriptionParty": row["subscription_party"],
        "coViewerCompanyId": row["co_viewer_company_id"], "iamClientId": row["iam_client_id"],
    })


def _wallet_requested_event(row: dict) -> None:
    events.publish(MODULE, "WalletAccessRequested", {"technicalUserId": row["id"],
                    "companyId": row["company_id"], "offerSubscriptionId": row["offer_subscription_id"]})


def _validate_create(body: dict, *, max_name: int, extra_fields: frozenset[str] = frozenset()) -> list[str]:
    allowed = {"name", "description", "authMethod", "roles"} | extra_fields
    if not isinstance(body, dict) or set(body) - allowed:
        raise Problem(MODULE, 400, "validation", detail="request contains unsupported fields")
    name = body.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= max_name:
        raise Problem(MODULE, 400, "validation", detail=f"name must contain 1..{max_name} characters")
    description = body.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 255):
        raise Problem(MODULE, 400, "validation", detail="description must contain at most 255 characters")
    roles = _role_names(body.get("roles"))
    if body.get("authMethod") not in (None, "SECRET"):
        raise Problem(MODULE, 400, "validation", detail="authMethod must be SECRET")
    return roles


def _assignable(company_id: str, roles: list[str]) -> None:
    _check_roles_exist(roles)
    not_assignable = set(roles) - _assignable_role_names(company_id)
    if not_assignable:
        raise Problem(MODULE, 400, "role-not-assignable", detail=f"roles are not assignable: {sorted(not_assignable)}")


def _credentials(row: dict, secret: str) -> dict:
    return {"iamClientId": row["iam_client_id"], "secret": secret,
            "tokenUrl": f"{tokens.iam_url()}/realms/{tokens.realm()}/protocol/openid-connect/token"}


def create_technical_user(*, company_id: str, body: dict, actor_sub: str) -> dict:
    roles = _validate_create(body, max_name=80)
    company = _company_ready(company_id)
    _assignable(company_id, roles)
    wallet_roles = set(roles) & _wallet_roles()
    assigned_roles = sorted(set(roles) - _wallet_roles())
    with _lock:
        row = _new_row(company_id=company_id, name=body["name"], description=body.get("description"), origin="OWN")
        try:
            created = _iam_call(iam_adapter.get().create_or_complete, row["iam_client_id"],
                                name=row["name"], description=row["description"], company_id=company_id,
                                bpn=company["bpn"], roles=assigned_roles)
            secret = _iam_call(iam_adapter.get().secret, row["iam_client_id"])
        except Exception:
            repository.remove(row["id"])
            _iam_call(iam_adapter.get().delete, row["iam_client_id"])
            raise
        row["iam_client_uuid"] = created["id"]
        row["iam_service_account_user_id"] = created.get("serviceAccountUserId")
        row["status"] = "PENDING" if wallet_roles else "ACTIVE"
        row["wallet_access"] = "REQUESTED" if wallet_roles else "NONE"
        _change(row)
        _audit(row, "createTechnicalUser", actor_type="PERSON", actor_sub=actor_sub)
        for role in assigned_roles:
            _role_audit(row, role, "ADDED", actor_type="PERSON", actor_sub=actor_sub,
                        operation="createTechnicalUser")
        _created_event(row)
        if wallet_roles:
            _wallet_requested_event(row)
        return _details(row, "OWNER") | {"credentials": _credentials(row, secret)}


def _validate_update(body: dict) -> None:
    allowed = {"name", "description", "roles"}
    if not body or set(body) - allowed:
        raise Problem(MODULE, 400, "validation", detail="provide name, description, or roles")
    if "name" in body and (not isinstance(body["name"], str) or not 1 <= len(body["name"]) <= 80):
        raise Problem(MODULE, 400, "validation", detail="name must contain 1..80 characters")
    if "description" in body and (not isinstance(body["description"], str) or len(body["description"]) > 255):
        raise Problem(MODULE, 400, "validation", detail="description must contain at most 255 characters")


def _update_roles(row: TechnicalUserRecord, body: dict) -> tuple[list[str], list[str]]:
    if "roles" not in body:
        return [], []
    roles = _role_names(body["roles"])
    _assignable(row["company_id"], roles)
    current = set(_iam_call(iam_adapter.get().roles_for, row["iam_client_id"]))
    current_wallet = bool(current & _wallet_roles()) or row["wallet_access"] != "NONE"
    target_wallet = bool(set(roles) & _wallet_roles())
    if current_wallet != target_wallet:
        raise Problem(MODULE, 409, "wallet-role-change")
    assigned = sorted(set(roles) - _wallet_roles())
    return _iam_call(iam_adapter.get().set_roles, row["iam_client_id"], assigned)


def _update_client_metadata(row: TechnicalUserRecord, body: dict) -> bool:
    name = body.get("name", row["name"])
    description = body.get("description", row["description"])
    if name == row["name"] and description == row["description"]:
        return False
    _iam_call(iam_adapter.get().update_client, row["iam_client_id"], name=name, description=description)
    row["name"], row["description"] = name, description
    return True


def _audit_role_changes(row: TechnicalUserRecord, added: list[str], removed: list[str], actor_sub: str) -> None:
    for role in added:
        _role_audit(row, role, "ADDED", actor_type="PERSON", actor_sub=actor_sub,
                    operation="updateTechnicalUser")
    for role in removed:
        _role_audit(row, role, "REMOVED", actor_type="PERSON", actor_sub=actor_sub,
                    operation="updateTechnicalUser")


def update_technical_user(*, id: str, company_id: str, body: dict, actor_sub: str) -> dict:
    row = _find(id)
    _owned(row, company_id)
    _validate_update(body)
    if row["status"] != "ACTIVE" or row["disabled"]:
        raise Problem(MODULE, 409, "invalid-state")
    added, removed = _update_roles(row, body)
    metadata_changed = _update_client_metadata(row, body)
    if added or removed or metadata_changed:
        _change(row)
        _audit(row, "updateTechnicalUser", actor_type="PERSON", actor_sub=actor_sub)
        _audit_role_changes(row, added, removed, actor_sub)
    return _details(row, "OWNER")


def _query_neighbour(target: str, function: str, **params):
    if neighbours.is_standin(target):
        if target == "c6-m1":
            return []
        if target == "c10-m1":
            return {"offerSubscriptionId": params.get("offerSubscriptionId"), "status": "INACTIVE"}
    return neighbours.query(MODULE, target, function, **params)


def delete_technical_user(*, id: str, company_id: str, actor_sub: str) -> tuple[int, dict | None]:
    row = _find(id)
    viewer_role = _visible(row, company_id)
    if row["wallet_access"] == "REQUESTED":
        raise Problem(MODULE, 409, "wallet-in-progress")
    if row["status"] not in ("ACTIVE", "INACTIVE"):
        raise Problem(MODULE, 409, "invalid-state")
    connectors = _query_neighbour("c6-m1", "list_connectors_internal", technicalUserId=id)
    if connectors:
        raise Problem(MODULE, 409, "in-use")
    if row["origin"] == "SUBSCRIPTION":
        subscription = _query_neighbour("c10-m1", "get_subscription_internal",
                                         offerSubscriptionId=row["offer_subscription_id"])
        if subscription and subscription.get("status") == "ACTIVE":
            raise Problem(MODULE, 409, "in-use")
    with _lock:
        if row["wallet_access"] == "ACTIVE":
            row["status"], row["wallet_access"] = "PENDING_DELETION", "REMOVING"
            _change(row)
            _audit(row, "deleteTechnicalUser", actor_type="PERSON", actor_sub=actor_sub)
            events.publish(MODULE, "WalletAccessRemovalRequested", {"technicalUserId": row["id"],
                            "companyId": row["company_id"], "walletAccountRef": row["wallet_account_ref"]})
            return 202, _details(row, viewer_role)
        roles = _iam_call(iam_adapter.get().roles_for, row["iam_client_id"])
        _iam_call(iam_adapter.get().delete, row["iam_client_id"])
        row["status"], row["wallet_access"], row["wallet_account_ref"] = "DELETED", "NONE", None
        _change(row)
        _audit(row, "deleteTechnicalUser", actor_type="PERSON", actor_sub=actor_sub)
        for role in roles:
            _role_audit(row, role, "REMOVED", actor_type="PERSON", actor_sub=actor_sub,
                        operation="deleteTechnicalUser")
        events.publish(MODULE, "TechnicalUserDeleted", {"technicalUserId": row["id"],
                        "companyId": row["company_id"], "coViewerCompanyId": row["co_viewer_company_id"],
                        "iamClientId": row["iam_client_id"]})
        return 204, None


def rotate_credentials(*, id: str, company_id: str, actor_sub: str) -> dict:
    row = _find(id)
    _owned(row, company_id)
    if row["status"] not in ("ACTIVE", "PENDING") or not row["iam_client_uuid"] or row["disabled"]:
        raise Problem(MODULE, 409, "invalid-state")
    secret = _iam_call(iam_adapter.get().rotate_secret, row["iam_client_id"])
    _audit(row, "rotateCredentials", actor_type="PERSON", actor_sub=actor_sub)
    return _credentials(row, secret)


def rotate_subscription_credentials(*, id: str, offer_subscription_id: str, **_other) -> dict:
    row = technical_users.get(id)
    if row is None or row["origin"] != "SUBSCRIPTION" or row["offer_subscription_id"] != offer_subscription_id:
        raise Problem(MODULE, 404, "not-found", retryable=False)
    if row["status"] not in ("ACTIVE", "PENDING") or not row["iam_client_uuid"] or row["disabled"]:
        raise Problem(MODULE, 409, "invalid-state", retryable=False)
    secret = _iam_call(iam_adapter.get().rotate_secret, row["iam_client_id"])
    _audit(row, "rotateSubscriptionCredentials", actor_type="PROCESS")
    return _credentials(row, secret)


def check_technical_user(*, id: str, company_id: str, offer_subscription_id: str | None = None,
                         **_other) -> dict:
    row = technical_users.get(id)
    if row is None:
        return {"exists": False, "usableForConnector": False}
    belongs = row["company_id"] == company_id
    usable = belongs and row["status"] in ("ACTIVE", "PENDING") and not row["disabled"] and (
        row["origin"] == "OWN" or (row["origin"] == "SUBSCRIPTION" and row["subscription_party"] == "CUSTOMER"
                                    and offer_subscription_id is not None
                                    and row["offer_subscription_id"] == offer_subscription_id))
    return {"exists": True, "belongsToCompany": belongs, "status": row["status"], "origin": row["origin"],
            "walletAccess": row["wallet_access"], "disabled": row["disabled"], "usableForConnector": usable}


def _subscription_row(offer_subscription_id: str, party: str) -> dict | None:
    return repository.find_subscription(offer_subscription_id, party)


def _create_subscription_account(*, input: dict, party: str, company: dict, name: str,
                                 roles: list[str], co_viewer_company_id: str | None) -> dict:
    subscription_id = input["offerSubscriptionId"]
    row = _subscription_row(subscription_id, party)
    if row is None:
        row = _new_row(company_id=company["id"], name="", description=None, origin="SUBSCRIPTION",
                       offer_subscription_id=subscription_id, subscription_party=party,
                       co_viewer_company_id=co_viewer_company_id)
        row["name"] = f"{row['iam_client_id']}-{name}"
    wallet_roles = set(roles) & _wallet_roles() if party == "CUSTOMER" else set()
    assigned_roles = sorted(set(roles) - _wallet_roles())
    was_created = row["iam_client_uuid"] is None
    previous_roles = set(_iam_call(iam_adapter.get().roles_for, row["iam_client_id"])) if not was_created else set()
    created = _iam_call(iam_adapter.get().create_or_complete, row["iam_client_id"], name=row["name"],
                        description=None, company_id=company["id"], bpn=company["bpn"], roles=assigned_roles,
                        enabled=not row["disabled"] and row["status"] != "INACTIVE")
    current_roles = set(_iam_call(iam_adapter.get().roles_for, row["iam_client_id"]))
    if was_created:
        row["iam_client_uuid"] = created["id"]
        row["iam_service_account_user_id"] = created.get("serviceAccountUserId")
        row["status"] = "PENDING" if wallet_roles else "ACTIVE"
        row["wallet_access"] = "REQUESTED" if wallet_roles else "NONE"
        _change(row)
        _audit(row, "create-for-subscription", actor_type="PROCESS", process_id=input.get("processId"),
               step_run_id=input.get("stepRunId"))
        for role in sorted(current_roles - previous_roles):
            _role_audit(row, role, "ADDED", actor_type="PROCESS", process_id=input.get("processId"),
                        step_run_id=input.get("stepRunId"), operation="create-for-subscription")
        _created_event(row)
        if wallet_roles:
            _wallet_requested_event(row)
    return {"technicalUserId": row["id"], "subscriptionParty": party, "iamClientId": row["iam_client_id"],
            "status": row["status"], "walletAccess": row["wallet_access"],
            "roles": [{"name": role} for role in roles]}


def create_for_subscription(input: dict) -> dict:
    roles = _validate_create(input, max_name=200, extra_fields=frozenset({
        "processId", "stepRunId", "customerCompanyId", "providerCompanyId", "offerSubscriptionId",
    }))
    if not all(isinstance(input.get(key), str) and input[key]
               for key in ("customerCompanyId", "providerCompanyId", "offerSubscriptionId")):
        raise Problem(MODULE, 400, "validation", retryable=False,
                      detail="customerCompanyId, providerCompanyId and offerSubscriptionId are required")
    _check_roles_exist(roles)
    _company_ready(input.get("customerCompanyId"))
    provider_roles = set(roles) & _provider_roles()
    provider = _company_ready(input.get("providerCompanyId")) if provider_roles else None
    customer = _company(input["customerCompanyId"])
    customer_roles = [role for role in roles if role not in _provider_roles()]
    result = []
    with _lock:
        result.append(_create_subscription_account(input=input, party="CUSTOMER", company=customer,
                       name=input["name"], roles=customer_roles,
                       co_viewer_company_id=input.get("providerCompanyId")))
        if provider_roles:
            result.append(_create_subscription_account(input=input, party="PROVIDER", company=provider,
                           name=input["name"], roles=sorted(provider_roles), co_viewer_company_id=None))
    return standin.step_reply(input, {"offerSubscriptionId": input["offerSubscriptionId"], "accounts": result})


def apply_wallet_access(input: dict) -> dict:
    row = _find(input.get("technicalUserId"))
    outcome = input.get("outcome")
    wallet_ref = input.get("walletAccountRef")
    if outcome not in ("ACTIVE", "FAILED") or (outcome == "ACTIVE" and not wallet_ref):
        raise Problem(MODULE, 400, "validation", detail="outcome ACTIVE requires walletAccountRef", retryable=False)
    current = row["wallet_access"]
    expected = "ACTIVE" if outcome == "ACTIVE" else "FAILED"
    if current == expected and (outcome == "FAILED" or row["wallet_account_ref"] == wallet_ref):
        return standin.step_reply(input, {"technicalUserId": row["id"], "status": row["status"],
                                "walletAccess": current, "walletAccountRef": row["wallet_account_ref"]})
    if current != "REQUESTED":
        raise Problem(MODULE, 409, "invalid-state", retryable=False)
    row["wallet_access"] = expected
    row["wallet_account_ref"] = wallet_ref if outcome == "ACTIVE" else None
    if row["status"] != "INACTIVE":
        row["status"] = "ACTIVE"
    _change(row)
    _audit(row, "apply-wallet-access", actor_type="PROCESS", process_id=input.get("processId"),
           step_run_id=input.get("stepRunId"))
    return standin.step_reply(input, {"technicalUserId": row["id"], "status": row["status"],
                            "walletAccess": row["wallet_access"], "walletAccountRef": row["wallet_account_ref"]})


def delete(input: dict) -> dict:
    row = _find(input.get("technicalUserId"))
    if row["status"] == "DELETED":
        return standin.step_reply(input, {"technicalUserId": row["id"], "status": "DELETED"})
    if row["status"] != "PENDING_DELETION" or row["wallet_access"] != "REMOVING":
        raise Problem(MODULE, 409, "invalid-state", retryable=False)
    roles = _iam_call(iam_adapter.get().roles_for, row["iam_client_id"])
    _iam_call(iam_adapter.get().delete, row["iam_client_id"])
    row["status"], row["wallet_access"], row["wallet_account_ref"] = "DELETED", "NONE", None
    _change(row)
    _audit(row, "delete", actor_type="PROCESS", process_id=input.get("processId"),
           step_run_id=input.get("stepRunId"))
    for role in roles:
        _role_audit(row, role, "REMOVED", actor_type="PROCESS", process_id=input.get("processId"),
                    step_run_id=input.get("stepRunId"), operation="delete")
    events.publish(MODULE, "TechnicalUserDeleted", {"technicalUserId": row["id"], "companyId": row["company_id"],
                    "coViewerCompanyId": row["co_viewer_company_id"], "iamClientId": row["iam_client_id"]})
    return standin.step_reply(input, {"technicalUserId": row["id"], "status": row["status"]})


def disable_company_technical_users(input: dict) -> dict:
    company_id = input.get("companyId")
    with _lock:
        rows = [row for row in technical_users.values()
                if row["company_id"] == company_id and row["status"] != "DELETED"]
        for row in rows:
            if row["disabled"]:
                continue
            if row["iam_client_uuid"]:
                _iam_call(iam_adapter.get().set_enabled, row["iam_client_id"], False)
            row["disabled"] = True
            _change(row)
            _audit(row, "disable-company-technical-users", actor_type="PROCESS",
                   process_id=input.get("processId"), step_run_id=input.get("stepRunId"))
    ids = sorted(row["id"] for row in technical_users.values()
                 if row["company_id"] == company_id and row["status"] != "DELETED" and row["disabled"])
    return standin.step_reply(input, {"companyId": company_id, "technicalUserIds": ids})


def enable_company_technical_users(input: dict) -> dict:
    company_id = input.get("companyId")
    with _lock:
        rows = [row for row in technical_users.values()
                if row["company_id"] == company_id and row["status"] != "DELETED" and row["disabled"]]
        for row in rows:
            if row["iam_client_uuid"] and row["status"] != "INACTIVE":
                _iam_call(iam_adapter.get().set_enabled, row["iam_client_id"], True)
            row["disabled"] = False
            _change(row)
            _audit(row, "enable-company-technical-users", actor_type="PROCESS",
                   process_id=input.get("processId"), step_run_id=input.get("stepRunId"))
    ids = sorted(row["id"] for row in technical_users.values()
                 if row["company_id"] == company_id and row["status"] != "DELETED" and not row["disabled"])
    return standin.step_reply(input, {"companyId": company_id, "technicalUserIds": ids})


def disable_subscription_technical_users(input: dict) -> dict:
    subscription_id = input.get("offerSubscriptionId")
    with _lock:
        rows = [row for row in technical_users.values()
                if row["offer_subscription_id"] == subscription_id and row["status"] in ("PENDING", "ACTIVE")]
        for row in rows:
            if row["iam_client_uuid"]:
                _iam_call(iam_adapter.get().set_enabled, row["iam_client_id"], False)
            row["status"] = "INACTIVE"
            _change(row)
            _audit(row, "disable-subscription-technical-users", actor_type="PROCESS",
                   process_id=input.get("processId"), step_run_id=input.get("stepRunId"))
    ids = sorted(row["id"] for row in technical_users.values()
                 if row["offer_subscription_id"] == subscription_id and row["status"] == "INACTIVE")
    return standin.step_reply(input, {"offerSubscriptionId": subscription_id, "technicalUserIds": ids})