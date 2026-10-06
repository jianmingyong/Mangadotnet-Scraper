from mangadotnet_scraper.modules.manager import ModuleManager
from mangadotnet_scraper.modules.sources.en.art_lapsa import ArtLapsaModule
from mangadotnet_scraper.modules.sources.en.ez_manga import EzMangaModule
from mangadotnet_scraper.modules.sources.en.hijala_scans import (
    HijalaScansModule,
)
from mangadotnet_scraper.modules.sources.en.hive_scans import HiveScansModule
from mangadotnet_scraper.modules.sources.en.ken_scans import KenScansModule
from mangadotnet_scraper.modules.sources.en.magus_manga import MagusMangaModule
from mangadotnet_scraper.modules.sources.en.nyx_scans import NyxScansModule
from mangadotnet_scraper.modules.sources.en.orion_scans import OrionScansModule
from mangadotnet_scraper.modules.sources.en.rena_scans import RenaScansModule
from mangadotnet_scraper.modules.sources.en.rinko_comics import (
    RinkoComicsModule,
)
from mangadotnet_scraper.modules.sources.en.rithar_scans import (
    RitharScansModule,
)
from mangadotnet_scraper.modules.sources.en.sana_scans import SanaScansModule
from mangadotnet_scraper.modules.sources.en.vortex_scans import (
    VortexScansModule,
)

ModuleManager.register_module(ArtLapsaModule)
ModuleManager.register_module(EzMangaModule)
ModuleManager.register_module(HijalaScansModule)
ModuleManager.register_module(HiveScansModule)
ModuleManager.register_module(KenScansModule)
ModuleManager.register_module(MagusMangaModule)
ModuleManager.register_module(NyxScansModule)
ModuleManager.register_module(OrionScansModule)
ModuleManager.register_module(RenaScansModule)
ModuleManager.register_module(RinkoComicsModule)
ModuleManager.register_module(RitharScansModule)
ModuleManager.register_module(SanaScansModule)
ModuleManager.register_module(VortexScansModule)
