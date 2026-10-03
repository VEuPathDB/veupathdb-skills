"""VEuPathDB site registry. base_url IS the WDK REST service root."""


class UnknownSiteError(KeyError):
    pass


def _s(base_url: str, project_id: str, timeout: int = 30) -> dict:
    return {"base_url": base_url, "project_id": project_id, "timeout": timeout}


SITES: dict[str, dict] = {
    "veupathdb": _s("https://veupathdb.org/veupathdb/service", "EuPathDB", 120),
    "amoebadb": _s("https://amoebadb.org/amoeba/service", "AmoebaDB"),
    "cryptodb": _s("https://cryptodb.org/cryptodb/service", "CryptoDB"),
    "fungidb": _s("https://fungidb.org/fungidb/service", "FungiDB"),
    "giardiadb": _s("https://giardiadb.org/giardiadb/service", "GiardiaDB"),
    "hostdb": _s("https://hostdb.org/hostdb/service", "HostDB"),
    "microsporidiadb": _s("https://microsporidiadb.org/micro/service", "MicrosporidiaDB"),
    "orthomcl": _s("https://orthomcl.org/orthomcl/service", "OrthoMCL"),
    "piroplasmadb": _s("https://piroplasmadb.org/piro/service", "PiroplasmaDB"),
    "plasmodb": _s("https://plasmodb.org/plasmo/service", "PlasmoDB"),
    "toxodb": _s("https://toxodb.org/toxo/service", "ToxoDB"),
    "trichdb": _s("https://trichdb.org/trichdb/service", "TrichDB"),
    "tritrypdb": _s("https://tritrypdb.org/tritrypdb/service", "TriTrypDB"),
    "vectorbase": _s("https://vectorbase.org/vectorbase/service", "VectorBase"),
}


def _site(site_id: str) -> dict:
    try:
        return SITES[site_id]
    except KeyError:
        raise UnknownSiteError(
            f"unknown site '{site_id}'; valid: {', '.join(sorted(SITES))}"
        ) from None


def service_url(site_id: str) -> str:
    return _site(site_id)["base_url"]


def project_id(site_id: str) -> str:
    return _site(site_id)["project_id"]


def web_base_url(site_id: str) -> str:
    return _site(site_id)["base_url"].removesuffix("/service")


def profile_url(site_id: str) -> str:
    return f"{web_base_url(site_id)}/app/user/profile#serviceAccess"


def registration_url(site_id: str) -> str:
    return f"{web_base_url(site_id)}/app/user/registration"


def strategy_url(site_id: str, strategy_id, step_id=None) -> str:
    url = f"{web_base_url(site_id)}/app/workspace/strategies/{strategy_id}"
    return f"{url}/{step_id}" if step_id is not None else url


COMMUNITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "plasmodb": (
        "plasmodium", "malaria", "falciparum", "vivax", "berghei", "knowlesi",
        "chabaudi", "yoelii", "cynomolgi", "ovale", "malariae",
    ),
    "toxodb": (
        "toxoplasma", "gondii", "neospora", "caninum", "sarcocystis",
        "besnoitia", "hammondia", "cystoisospora",
    ),
    "vectorbase": (
        "anopheles", "aedes", "culex", "glossina", "ixodes", "phlebotomus",
        "lutzomyia", "rhodnius", "triatoma", "stegomyia", "mosquito", "tick",
        "tsetse", "sandfly", "vector", "culicoides",
    ),
    "tritrypdb": (
        "trypanosoma", "leishmania", "brucei", "cruzi", "donovani", "infantum",
        "major", "braziliensis", "mexicana", "chagas", "sleeping sickness",
        "kinetoplastid",
    ),
    "fungidb": (
        "candida", "aspergillus", "cryptococcus", "histoplasma", "coccidioides",
        "pneumocystis", "saccharomyces", "neurospora", "fusarium", "blastomyces",
        "paracoccidioides", "fungus", "fungi", "yeast", "mycology",
    ),
    "cryptodb": (
        "cryptosporidium", "parvum", "hominis", "crypto",
    ),
    "amoebadb": (
        "entamoeba", "acanthamoeba", "naegleria", "histolytica", "fowleri",
        "amoeba", "ameba",
    ),
    "giardiadb": (
        "giardia", "lamblia", "duodenalis", "intestinalis",
    ),
    "trichdb": (
        "trichomonas", "vaginalis", "trichomonad",
    ),
    "piroplasmadb": (
        "babesia", "theileria", "microti", "bovis", "annulata", "divergens",
        "piroplasm",
    ),
    "microsporidiadb": (
        "encephalitozoon", "nosema", "enterocytozoon", "microsporidia",
    ),
    "schistodb": (
        "schistosoma", "mansoni", "haematobium", "japonicum", "blood fluke",
        "schistosome", "schistosomiasis",
    ),
    "hostdb": (
        "human", "homo sapiens", "mouse", "mus musculus", "host",
    ),
}


def detect_site(text: str) -> str:
    """Detect the most likely VEuPathDB community site from query text.

    Falls back to 'veupathdb'.
    """
    if not text:
        return "veupathdb"

    normalized = text.lower()

    # 1. Direct mention of site ID or project name
    for site_id, site_info in SITES.items():
        if site_id in normalized or site_info["project_id"].lower() in normalized:
            return site_id

    # 2. Organism / disease keywords
    for site_id, keywords in COMMUNITY_KEYWORDS.items():
        for kw in keywords:
            if kw in normalized:
                return site_id

    return "veupathdb"

