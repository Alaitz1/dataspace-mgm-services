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
"""The repository guarantees of C2-M3: events leave with their transaction (README 4) and locks are per key."""
from __future__ import annotations

import threading
import zlib

import pytest

from modules.c2_m3.repository import LOCK_STRIPES, InMemoryTechnicalUserRepository


class Bus:
    """A publisher that records what it gets and can be made to fail."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.failures: list[Exception] = []

    def __call__(self, event_type: str, data: dict) -> None:
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append((event_type, data))


@pytest.fixture
def bus() -> Bus:
    return Bus()


@pytest.fixture
def repo(bus) -> InMemoryTechnicalUserRepository:
    return InMemoryTechnicalUserRepository(publisher=bus)


def test_events_leave_only_after_the_transaction_committed(repo, bus):
    with repo.transaction():
        repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
        assert bus.sent == []
        assert repo.unsent_events() == []
    assert bus.sent == [("TechnicalUserCreated", {"technicalUserId": "u1"})]
    assert repo.unsent_events() == []


def test_a_failed_transaction_drops_its_events(repo, bus):
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
            raise RuntimeError("change failed")
    assert bus.sent == [] and repo.unsent_events() == []
    with repo.transaction():
        repo.add_event("TechnicalUserDeleted", {"technicalUserId": "u2"})
    assert [event for event, _ in bus.sent] == ["TechnicalUserDeleted"]


def test_a_nested_transaction_publishes_once_with_the_outermost(repo, bus):
    with repo.transaction():
        with repo.transaction():
            repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
        assert bus.sent == []
        repo.add_event("WalletAccessRequested", {"technicalUserId": "u1"})
    assert [event for event, _ in bus.sent] == ["TechnicalUserCreated", "WalletAccessRequested"]


def test_an_inner_failure_drops_only_its_own_events_when_the_outer_one_recovers(repo, bus):
    with repo.transaction():
        repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
        with pytest.raises(RuntimeError):
            with repo.transaction():
                repo.add_event("TechnicalUserDeleted", {"technicalUserId": "u1"})
                raise RuntimeError("inner")
    assert [event for event, _ in bus.sent] == ["TechnicalUserCreated"]


def test_an_event_needs_a_transaction(repo):
    with pytest.raises(RuntimeError):
        repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})


def test_a_temporary_publish_failure_keeps_the_event_for_the_next_try(repo, bus):
    bus.failures.append(ConnectionError("relay down"))
    with repo.transaction():
        repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
        repo.add_event("WalletAccessRequested", {"technicalUserId": "u1"})
    assert bus.sent == []
    assert [event for event, _ in repo.unsent_events()] == ["TechnicalUserCreated", "WalletAccessRequested"]
    repo.flush_outbox()
    assert [event for event, _ in bus.sent] == ["TechnicalUserCreated", "WalletAccessRequested"]
    assert repo.unsent_events() == []


def test_an_invalid_event_is_dropped_and_does_not_block_the_next_one(repo, bus):
    bus.failures.append(ValueError("secret in data"))
    with repo.transaction():
        repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
        repo.add_event("TechnicalUserDeleted", {"technicalUserId": "u1"})
    assert [event for event, _ in bus.sent] == ["TechnicalUserDeleted"]
    assert repo.unsent_events() == []


def test_the_change_stays_committed_when_the_publisher_fails(repo, bus):
    bus.failures.append(ConnectionError("relay down"))
    with repo.transaction():
        repo.audit_entries()
        repo.add_audit_entry({"id": "a1", "operation": "x"})
        repo.add_event("TechnicalUserCreated", {"technicalUserId": "u1"})
    assert [entry["id"] for entry in repo.audit_entries()] == ["a1"]


def test_the_event_data_is_copied(repo, bus):
    data = {"technicalUserId": "u1"}
    with repo.transaction():
        repo.add_event("TechnicalUserCreated", data)
        data["technicalUserId"] = "changed"
    assert bus.sent[0][1] == {"technicalUserId": "u1"}


def _stripe(key: str) -> int:
    return zlib.crc32(key.encode()) % LOCK_STRIPES


def _keys_on_different_stripes() -> tuple[str, str]:
    first = "technical-user:a"
    other = next(f"technical-user:{n}" for n in range(1000) if _stripe(f"technical-user:{n}") != _stripe(first))
    return first, other


def _run(repo, key: str, entered: threading.Event, release: threading.Event | None = None) -> threading.Thread:
    def work() -> None:
        with repo.locked(key):
            entered.set()
            if release:
                release.wait(5)
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return thread


def test_a_slow_holder_blocks_only_its_own_key(repo):
    first, other = _keys_on_different_stripes()
    holding, release, other_entered = threading.Event(), threading.Event(), threading.Event()
    slow = _run(repo, first, holding, release)
    assert holding.wait(5)
    fast = _run(repo, other, other_entered)
    assert other_entered.wait(2), "an unrelated key must not wait for the slow one"
    release.set()
    slow.join(5)
    fast.join(5)


def test_the_same_key_waits_for_the_holder(repo):
    holding, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    slow = _run(repo, "subscription:s1", holding, release)
    assert holding.wait(5)
    waiting = _run(repo, "subscription:s1", second_entered)
    assert not second_entered.wait(0.3), "the same key must wait"
    release.set()
    assert second_entered.wait(5)
    slow.join(5)
    waiting.join(5)


def test_a_key_lock_can_be_taken_again_by_the_same_thread(repo):
    with repo.locked("technical-user:x"):
        with repo.locked("technical-user:x"):
            with repo.transaction():
                pass
