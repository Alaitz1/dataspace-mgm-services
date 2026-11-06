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
"""C2-M3 application services: `queries` read, `commands` are people's operations, `steps` are Process Orchestration's."""

from modules.c2_m3 import iam as _iam
from modules.c2_m3.repository import repository as _repository
from .commands import (
    create_technical_user,
    delete_technical_user,
    rotate_credentials,
    rotate_subscription_credentials,
    update_technical_user,
)
from .process_stub import handle_event
from .queries import (
    check_technical_user,
    get_any_technical_user,
    get_technical_user,
    list_all_technical_users,
    list_technical_users,
)
from .roles import list_assignable_roles, list_technical_roles
from .steps import (
    apply_wallet_access,
    create_for_subscription,
    delete,
    disable_company_technical_users,
    disable_subscription_technical_users,
    enable_company_technical_users,
)


def reset() -> None:
    _repository.reset()
    _iam.reset()


__all__ = [
    "apply_wallet_access", "check_technical_user", "create_for_subscription", "create_technical_user", "delete",
    "delete_technical_user", "disable_company_technical_users", "disable_subscription_technical_users",
    "enable_company_technical_users", "get_any_technical_user", "get_technical_user", "handle_event",
    "list_all_technical_users",
    "list_assignable_roles", "list_technical_roles", "list_technical_users", "reset", "rotate_credentials",
    "rotate_subscription_credentials", "update_technical_user",
]