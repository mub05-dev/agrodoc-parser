from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.agroanalitica._helpers import parse_agroanalitica


class AgroanaliticaParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "agroanalitica"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 6

    def detect(self, text) -> bool:
        t = text.upper()
        return "AGROANALITICA" in t or "AGROANALÍTICA" in t or "AGROANALITICALABORATORIO" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_agroanalitica(file_path)
        return ParseResult.model_validate(raw)
