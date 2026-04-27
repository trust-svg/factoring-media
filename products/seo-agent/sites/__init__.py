from core.sites import Site
from sites.faccel import FaccelSite
from sites.saimu_times import SaimuTimesSite


def all_sites() -> list[Site]:
    return [FaccelSite(), SaimuTimesSite()]


__all__ = ["all_sites", "FaccelSite", "SaimuTimesSite"]
