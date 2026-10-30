"""Atomic, auditable verification-credit ledger for one research run."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class Reservation:
    agreement_id: str
    request_id: str
    owner: str
    units: int
    phase: str = "reserved"


class VerificationBudget:
    """Cumulative credits and concurrent slots are different constraints.

    Finished work releases execution slots but keeps its credits spent. A cancelled
    reservation refunds credits only before execution starts.
    """

    def __init__(self, credits: int, concurrent_slots: int | None = None):
        if credits < 0 or concurrent_slots is not None and concurrent_slots < 1:
            raise ValueError("invalid resource capacity")
        self.credits = credits
        self.concurrent_slots = concurrent_slots or max(1, credits)
        self.spent = 0
        self.reservations: dict[str, Reservation] = {}
        self.by_request: dict[str, str] = {}
        self.lock = asyncio.Lock()
        self.peak_active = 0

    def _held(self) -> int:
        return sum(r.units for r in self.reservations.values()
                   if r.phase in {"reserved", "active"})

    def _active(self) -> int:
        return sum(1 for r in self.reservations.values() if r.phase == "active")

    def _assert_invariants(self) -> None:
        if self.spent + self._held() > self.credits or self._active() > self.concurrent_slots:
            raise AssertionError("resource invariant violated")

    async def reserve(self, agreement_id: str, request_id: str,
                      owner: str, units: int) -> bool:
        if not agreement_id or not request_id or not owner or units < 1:
            raise ValueError("invalid reservation")
        async with self.lock:
            old = self.reservations.get(agreement_id)
            if old:
                if (old.request_id, old.owner, old.units) != (request_id, owner, units):
                    raise ValueError("agreement identifier reused with different terms")
                return old.phase in {"reserved", "active", "finished"}
            previous = self.by_request.get(request_id)
            if previous:
                if self.reservations[previous].phase != "cancelled":
                    raise ValueError("request already has an agreement")
                self.by_request.pop(request_id)
            if self.spent + self._held() + units > self.credits:
                return False
            self.reservations[agreement_id] = Reservation(agreement_id, request_id,
                                                           owner, units)
            self.by_request[request_id] = agreement_id
            self._assert_invariants()
            return True

    async def start(self, agreement_id: str, owner: str) -> bool:
        async with self.lock:
            record = self.reservations.get(agreement_id)
            if record is None or record.owner != owner or record.phase != "reserved":
                return False
            if self._active() + 1 > self.concurrent_slots:
                return False
            record.phase = "active"
            self.peak_active = max(self.peak_active, self._active())
            self._assert_invariants()
            return True

    async def finish(self, agreement_id: str, owner: str) -> bool:
        async with self.lock:
            record = self.reservations.get(agreement_id)
            if record is None or record.owner != owner or record.phase != "active":
                return False
            record.phase = "finished"
            self.spent += record.units
            self._assert_invariants()
            return True

    async def cancel(self, agreement_id: str, owner: str) -> bool:
        async with self.lock:
            record = self.reservations.get(agreement_id)
            if record is None or record.owner != owner or record.phase != "reserved":
                return False
            record.phase = "cancelled"
            self._assert_invariants()
            return True

    async def abort(self, agreement_id: str, owner: str) -> bool:
        """Release a stalled allocation; active work consumes its reserved credits."""
        async with self.lock:
            record = self.reservations.get(agreement_id)
            if record is None or record.owner != owner or record.phase not in {
                    "reserved", "active"}:
                return False
            if record.phase == "active":
                self.spent += record.units
                record.phase = "failed"
            else:
                record.phase = "cancelled"
            self._assert_invariants()
            return True

    async def authorized(self, agreement_id: str, request_id: str,
                         owner: str, units: int) -> bool:
        async with self.lock:
            record = self.reservations.get(agreement_id)
            return bool(record and record.phase == "active" and
                        (record.request_id, record.owner, record.units)
                        == (request_id, owner, units))

    def snapshot(self) -> dict:
        self._assert_invariants()
        return {"credits": self.credits, "spent": self.spent, "held": self._held(),
                "active": self._active(), "concurrent_slots": self.concurrent_slots,
                "peak_active": self.peak_active,
                "reservations": {key: vars(value).copy()
                                 for key, value in self.reservations.items()}}
