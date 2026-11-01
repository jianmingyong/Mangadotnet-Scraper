from abc import ABC, abstractmethod


class DataProvider(ABC):
    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...
