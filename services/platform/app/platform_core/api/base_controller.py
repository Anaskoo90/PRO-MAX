"""
Base Controllers: a thin convenience base for grouping related route
handlers into a class (mirroring the "controller" vocabulary used
throughout the Solution Design Pack's API Specifications), while staying
plain FastAPI underneath — no custom routing magic to learn.
"""

from __future__ import annotations

from fastapi import APIRouter


class BaseController:
    router: APIRouter

    def __init__(self, *, prefix: str, tags: list[str]) -> None:
        self.router = APIRouter(prefix=prefix, tags=tags)
        self.register_routes()

    def register_routes(self) -> None:
        """Subclasses call self.router.get/post/... here."""
        raise NotImplementedError
