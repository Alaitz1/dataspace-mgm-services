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
"""Calls to the Portal IAM with the public error shape of the module (README 12)."""
from __future__ import annotations

import httpx

from portal_common.problems import Problem

from modules.c2_m3 import iam as iam_package
from modules.c2_m3.iam import IamConflict, IamError, TechnicalUserIam, UnknownRole
from .config import MODULE


def iam() -> TechnicalUserIam:
    return iam_package.get()


def call(function, *args, **kwargs):
    """Runs one IAM call: unknown role -> 400 `role-not-assignable`, IAM trouble -> 502 `iam-error`."""
    try:
        return function(*args, **kwargs)
    except UnknownRole as exc:
        raise Problem(MODULE, 400, "role-not-assignable", detail=str(exc), retryable=False) from exc
    except IamConflict as exc:   # a retry would meet the same foreign client again
        raise Problem(MODULE, 502, "iam-error", detail=str(exc), retryable=False) from exc
    except (IamError, httpx.HTTPError) as exc:
        raise Problem(MODULE, 502, "iam-error", detail=f"Portal IAM request failed: {type(exc).__name__}",
                      retryable=True) from exc
