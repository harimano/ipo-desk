"""Every source failure is one of three kinds. Modules catch these and record them; they never
swallow them into 'looks fine'. The distinction matters for what to do next:
  SourceBlocked  -> the host refused us (403/401/421/429). Retrying is pointless; fall through.
  SourceDown     -> network/timeout. A retry may help; the http layer already tried.
  SourceChanged  -> we got a response but could not parse it. The site changed; a human must look.
"""


class SourceError(Exception):
    kind = "error"

    def __init__(self, source: str, detail: str, url: str | None = None, status: int | None = None):
        self.source, self.detail, self.url, self.status = source, detail, url, status
        super().__init__(f"{source}: {detail}" + (f" [{status}]" if status else "") + (f" {url}" if url else ""))

    def record(self) -> dict:
        return {"kind": self.kind, "source": self.source, "detail": self.detail, "url": self.url, "status": self.status}


class SourceBlocked(SourceError):
    kind = "blocked"


class SourceDown(SourceError):
    kind = "down"


class SourceChanged(SourceError):
    kind = "changed"
