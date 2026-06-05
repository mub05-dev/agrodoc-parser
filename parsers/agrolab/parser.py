from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.agrolab._helpers import parse_agrolab


class AgrolabParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "agrolab"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 1

    def detect(self, text) -> bool:
        t = text.upper()
        return "AGROLAB" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_agrolab(file_path)
        return ParseResult.model_validate(raw)
