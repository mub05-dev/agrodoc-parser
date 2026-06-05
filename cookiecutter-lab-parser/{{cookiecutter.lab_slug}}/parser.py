from parsers.base import BaseLabParser
from schema import ParseResult
from parsers.{{cookiecutter.lab_slug}}._helpers import parse_{{cookiecutter.lab_slug}}


class {{cookiecutter.lab_class_name}}(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "{{cookiecutter.lab_slug}}"

    @property
    def file_type(self) -> str:
        return "{{cookiecutter.file_type}}"

    @property
    def priority(self) -> int:
        return {{cookiecutter.priority}}

    def detect(self, text) -> bool:
        t = text.upper()
        return "{{cookiecutter.detect_string}}" in t

    def parse(self, file_path) -> ParseResult:
        raw = parse_{{cookiecutter.lab_slug}}(file_path)
        return ParseResult.model_validate(raw)
