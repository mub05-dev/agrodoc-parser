from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.motzz._helpers import parse_motzz


class MotzzParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "motzz"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 10

    def detect(self, text) -> bool:
        t = text.upper()
        return "ARIZONA AGRICULTURAL SOLUTIONS" in t and "LAB NUMBER" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_motzz(file_path)
        return ParseResult.model_validate(raw)
