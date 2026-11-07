from abc import abstractmethod
from contextlib import AbstractAsyncContextManager


class BaseHttpClientProvider(AbstractAsyncContextManager):
    async def __aexit__(self, *args) -> None:
        await self.close()

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get_text(self, url: str, **kwargs) -> str: ...

    @abstractmethod
    async def get_json(self, url: str, **kwargs) -> str: ...

    @abstractmethod
    async def get_bytes(self, url: str, **kwargs) -> bytes: ...
