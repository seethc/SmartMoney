"""Shared types for possible additional read-only bank adapters.

The working Enable Banking integration lives in bankfeed.py and openbanking.py.
There is deliberately no payment interface.
Adapters must normalise GBP amounts to pence and preserve stable provider IDs.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BalanceSnapshot:
    provider_account_id: str
    available_pence: int
    observed_at: str
    currency: str = 'GBP'


@dataclass(frozen=True)
class BookedTransaction:
    provider_account_id: str
    provider_transaction_id: str
    booked_date: str
    description: str
    amount_pence: int
    currency: str = 'GBP'


class ReadOnlyBankFeed(Protocol):
    def balances(self) -> list[BalanceSnapshot]: ...

    def transactions(self, account_id: str, since: str) -> list[BookedTransaction]: ...
