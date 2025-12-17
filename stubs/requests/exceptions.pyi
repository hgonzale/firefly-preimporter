from . import Response

class RequestError(Exception): ...

RequestException = RequestError

class HTTPError(RequestError):
    response: Response | None
