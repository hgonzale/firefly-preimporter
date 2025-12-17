from collections.abc import Mapping

class Response:
    status_code: int
    _content: bytes
    def __init__(self) -> None: ...
    def raise_for_status(self) -> None: ...
    def json(self) -> Mapping[str, object]: ...

class Session:
    def __init__(self) -> None: ...
    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = ...,
        data: Mapping[str, str] | None = ...,
        json: object | None = ...,
        files: Mapping[str, tuple[str, bytes, str]] | None = ...,
        timeout: float | None = ...,
        verify: bool | str | None = ...,
    ) -> Response: ...
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = ...,
        params: Mapping[str, object] | None = ...,
        timeout: float | None = ...,
        verify: bool | str | None = ...,
    ) -> Response: ...

def post(
    url: str,
    *,
    headers: Mapping[str, str] | None = ...,
    json: object | None = ...,
    timeout: float | None = ...,
    verify: bool | str | None = ...,
) -> Response: ...
def put(
    url: str,
    *,
    headers: Mapping[str, str] | None = ...,
    json: object | None = ...,
    timeout: float | None = ...,
    verify: bool | str | None = ...,
) -> Response: ...
