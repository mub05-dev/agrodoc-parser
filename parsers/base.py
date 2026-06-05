# parsers/base.py
from abc import ABC, abstractmethod
from schema import ParseResult


class BaseLabParser(ABC):

    @property
    @abstractmethod
    def laboratory_key(self) -> str:
        """
        Unique identifier of the laboratory in snake_case.
        Examples: 'agrolab', 'motzz', 'ceres'
        """
        ...

    @property
    @abstractmethod
    def file_type(self) -> str:
        """
        File type that this parser processes.
        Valid values: 'pdf' | 'excel'
        """
        ...

    @property
    def priority(self) -> int:
        """
        Evaluation order in the registry. Higher number = evaluated first.
        Use high values (10+) for very specific detection strings.
        Use low values (0-5) for generic strings with collision risk.
        Default: 0
        """
        return 0

    @abstractmethod
    def detect(self, text: str) -> bool:
        """
        Receives the extracted text from the document and returns True
        if this parser recognizes the issuing laboratory.

        The text is already in uppercase from the router —
        no need to call .upper() internally.
        """
        ...

    @abstractmethod
    def parse(self, file_path: str) -> ParseResult:
        """
        Parses the document and returns a ParseResult validated by Pydantic.
        Raises ValueError if the document cannot be processed.ado.
        """
        ...
