from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.ceres._helpers import parse_ceres


class CeresParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "ceres"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 1

    def detect(self, text) -> bool:
        t = text.upper()
        return "AGROLABORATORIO CERES" in t or "LABCERESGUATE" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_ceres(file_path)
        return ParseResult.model_validate(raw)
