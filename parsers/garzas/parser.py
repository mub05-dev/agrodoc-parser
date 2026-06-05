from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.garzas._helpers import parse_las_garzas


class LasGarzasParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "las_garzas"

    @property
    def file_type(self) -> str:
        return "pdf"

    @property
    def priority(self) -> int:
        return 2

    def detect(self, text) -> bool:
        t = text.upper()
        return "LABORATORIO AGROPECUARIO LAS GARZAS" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_las_garzas(file_path)
        return ParseResult.model_validate(raw)
