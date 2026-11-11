from abc import ABC, abstractmethod
from typing import Any


class ConfigProvider(ABC):
    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def save(self) -> None: ...

    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    def set_config(self, key: str, value: Any) -> None: ...
