from parsers.base import BaseLabParser
from parsers.ceres.parser import CeresParser
from parsers.garzas.parser import LasGarzasParser
from parsers.fertilab.parser import FertilabParser
from parsers.phytomonitor.parser import PhytomonitorParser
from parsers.agrilab.parser import AgrilabParser
from parsers.agroanalitica.parser import AgroanaliticaParser
from parsers.tepeyac.parser import TepeyacParser
from parsers.tepeyac_plant.parser import TepeyacPlantParser
from parsers.agrolab.parser import AgrolabParser

from parsers.motzz.parser import MotzzParser

REGISTRY: list[BaseLabParser] = sorted(
    [
        AgrolabParser(),
        CeresParser(),
        LasGarzasParser(),
        FertilabParser(),
        PhytomonitorParser(),
        AgrilabParser(),
        AgroanaliticaParser(),
        TepeyacParser(),
        TepeyacPlantParser(),
        MotzzParser()
    ],
    key=lambda p: p.priority,
    reverse=True
)

PDF_REGISTRY = [p for p in REGISTRY if p.file_type == "pdf"]
EXCEL_REGISTRY = [p for p in REGISTRY if p.file_type == "excel"]
