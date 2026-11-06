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
"""Security dependencies of the routes: the permission of an operation and the company scope."""
from __future__ import annotations

from portal_common import standin

from .config import MODULE


def perm(method: str, path: str):
    """The token check with the `x-permission` that `openapi.yaml` declares for this operation."""
    return standin.perm(MODULE, method, path)


def company_scoped(claims: dict, company_id: str) -> str:
    """Scope `company` (README 6.4 step 3): the token's company must be the company of the path; returns `sub`."""
    standin.company_scope(MODULE, claims, company_id)
    return claims["sub"]
