from collections.abc import Sequence
from typing import IO, Any, Protocol

class Transaction(Protocol):
    dtposted: Any
    trnamt: Any
    name: str | None
    memo: str | None
    fitid: str | None

class Account(Protocol):
    acctid: str | None

class Statement(Protocol):
    account: Account | None
    transactions: Sequence[Transaction] | None

class OFXRoot(Protocol):
    statements: Sequence[Statement] | None

class OFXTree:
    def __init__(self) -> None: ...
    def parse(self, file: IO[bytes], /) -> None: ...
    def convert(self) -> OFXRoot: ...
