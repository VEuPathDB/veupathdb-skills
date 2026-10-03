import pytest


def test_all_14_sites_present():
    from _sites import SITES
    assert len(SITES) == 14
    for sid in ("plasmodb", "vectorbase", "toxodb", "veupathdb", "orthomcl"):
        assert sid in SITES


def test_service_and_web_urls():
    from _sites import service_url, strategy_url, web_base_url
    assert service_url("plasmodb") == "https://plasmodb.org/plasmo/service"
    assert web_base_url("plasmodb") == "https://plasmodb.org/plasmo"
    assert (strategy_url("plasmodb", 123)
            == "https://plasmodb.org/plasmo/app/workspace/strategies/123")
    assert (strategy_url("plasmodb", 123, 456)
            == "https://plasmodb.org/plasmo/app/workspace/strategies/123/456")


def test_unknown_site_lists_valid_ids():
    from _sites import UnknownSiteError, service_url
    with pytest.raises(UnknownSiteError) as e:
        service_url("nope")
    assert "plasmodb" in str(e.value)


def test_portal_timeout_is_120():
    from _sites import SITES
    assert SITES["veupathdb"]["timeout"] == 120
    assert SITES["plasmodb"]["timeout"] == 30


def test_profile_and_registration_urls():
    from _sites import profile_url, registration_url

    assert profile_url("plasmodb") == "https://plasmodb.org/plasmo/app/user/profile#serviceAccess"
    assert registration_url("plasmodb") == "https://plasmodb.org/plasmo/app/user/registration"
    assert profile_url("toxodb") == "https://toxodb.org/toxo/app/user/profile#serviceAccess"
    assert registration_url("vectorbase") == "https://vectorbase.org/vectorbase/app/user/registration"
    assert profile_url("veupathdb") == "https://veupathdb.org/veupathdb/app/user/profile#serviceAccess"


def test_detect_site_from_queries():
    from _sites import detect_site

    assert detect_site("Find kinase genes in Toxoplasma gondii") == "toxodb"
    assert detect_site("Anopheles gambiae PGRPLB exons") == "vectorbase"
    assert detect_site("Plasmodium falciparum 3D7 genes") == "plasmodb"
    assert detect_site("Leishmania major surface proteins") == "tritrypdb"
    assert detect_site("Candida albicans cell wall") == "fungidb"
    assert detect_site("Cryptosporidium parvum oocyst") == "cryptodb"
    assert detect_site("Entamoeba histolytica motility") == "amoebadb"
    assert detect_site("Schistosoma mansoni egg production") == "schistodb"
    assert detect_site("Show all genes with molecular weight 10000") == "veupathdb"
    assert detect_site("") == "veupathdb"
    assert detect_site(None) == "veupathdb"

