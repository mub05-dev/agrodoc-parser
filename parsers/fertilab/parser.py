from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.fertilab._helpers import parse_fertilab


class FertilabParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "fertilab"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 3

    def detect(self, text) -> bool:
        t = text.upper()
        return "FERTILIDAD DE SUELOS" in t or "FERTILAB" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_fertilab(file_path)
        return ParseResult.model_validate(raw)
