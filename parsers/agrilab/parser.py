from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.agrilab._helpers import parse_agrilab


class AgrilabParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "agrilab"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 5

    def detect(self, text) -> bool:
        t = text.upper()
        return "AGRILAB LABORATORIOS" in t or "AGRILAB.COM.CO" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_agrilab(file_path)
        return ParseResult.model_validate(raw)
