from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.tepeyac._helpers import parse_tepeyac


class TepeyacParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "tepeyac"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 7

    def detect(self, text) -> bool:
        t = text.upper()
        return "FERTILIZANTES TEPEYAC" in t or "FTEPEYAC" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_tepeyac(file_path)
        return ParseResult.model_validate(raw)
