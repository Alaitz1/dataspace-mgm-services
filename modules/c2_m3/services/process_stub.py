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
"""Stand-in for Process Orchestration and C4-M2 (README 11.3), for testing the module alone."""
from __future__ import annotations

import os

from . import steps


def enabled() -> bool:
    return os.environ.get("PROCESS_STUB", "false").lower() == "true"


def handle_event(event: dict) -> None:
    """Replays the wallet flows of FRAMEWORK 5.7 for the module's own events; a repeated event changes nothing."""
    if not enabled() or event.get("source") != "urn:c2-m3":
        return
    data = event.get("data") or {}
    step_input = {"processId": event["id"], "stepRunId": event["id"], "technicalUserId": data.get("technicalUserId")}
    if event.get("type") == "WalletAccessRequested":
        steps.apply_wallet_access(step_input | {"outcome": "ACTIVE",
                                                "walletAccountRef": f"stub-{data.get('technicalUserId')}"})
    elif event.get("type") == "WalletAccessRemovalRequested":
        steps.delete(step_input)
