from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.tepeyac_plant._helpers import parse_tepeyac_plant


class TepeyacPlantParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "tepeyac_plant"

    @property
    def file_type(self) -> str:
        return "excel"

    @property
    def priority(self) -> int:
        return 10

    def detect(self, text) -> bool:
        return "RESULTADOS" in text and "DATOS_CLIENTE" in text

    def parse(self, file_path) -> ParseResult:
        raw = parse_tepeyac_plant(file_path)
        return ParseResult.model_validate(raw)
