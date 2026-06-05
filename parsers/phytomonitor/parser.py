from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.phytomonitor._helpers import parse_phytomonitor


class PhytomonitorParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "phytomonitor"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 4

    def detect(self, text) -> bool:
        t = text.upper()
        return "PHYTOMONITOR" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_phytomonitor(file_path)
        return ParseResult.model_validate(raw)
