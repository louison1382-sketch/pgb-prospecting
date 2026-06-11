"""Tests unitaires pour prospecting.py — fonctions pures, pas d'appels API."""

from prospecting import _calculate_score, REGION_MAP, SIZE_MAP


# ── REGION_MAP ─────────────────────────────────────────────────────────────────

def test_region_map_europe_contains_france():
    assert "FR" in REGION_MAP["Europe"]


def test_region_map_europe_contains_expected_countries():
    assert {"FR", "DE", "GB", "CH", "BE"}.issubset(set(REGION_MAP["Europe"]))


def test_region_map_all_values_are_lists():
    for region, codes in REGION_MAP.items():
        assert isinstance(codes, list), f"{region} should be a list"
        assert len(codes) > 0, f"{region} should not be empty"


def test_region_map_no_duplicate_codes():
    all_codes = [code for codes in REGION_MAP.values() for code in codes]
    assert len(all_codes) == len(set(all_codes)), "Duplicate country codes across regions"


# ── SIZE_MAP ────────────────────────────────────────────────────────────────────────

def test_size_map_covers_all_ranges():
    expected_keys = {"1-10", "11-50", "51-200", "201-500", "500+"}
    assert expected_keys == set(SIZE_MAP.keys())


def test_size_map_values_are_strings():
    for k, v in SIZE_MAP.items():
        assert isinstance(v, str), f"SIZE_MAP[{k}] should be a string"


# ── _calculate_score ──────────────────────────────────────────────────────────────────

def test_score_perfect_match():
    prospect = {
        "Poste": "Directeur Général",
        "Secteur": "Services B2B",
        "Taille": "51-200",
        "Email": "test@example.com",
    }
    icp = {
        "job_titles": ["Directeur Général"],
        "sectors": ["Services B2B"],
        "company_size": ["51-200"],
    }
    assert _calculate_score(prospect, icp)["total"] == 100


def test_score_no_match():
    prospect = {"Poste": "", "Secteur": "", "Taille": "", "Email": ""}
    icp = {"job_titles": ["CEO"], "sectors": ["Tech"], "company_size": ["11-50"]}
    assert _calculate_score(prospect, icp)["total"] == 0


def test_score_title_only():
    prospect = {"Poste": "CEO", "Secteur": "", "Taille": "", "Email": ""}
    icp = {"job_titles": ["CEO"], "sectors": [], "company_size": []}
    assert _calculate_score(prospect, icp)["total"] == 40


def test_score_email_verified_adds_10():
    prospect = {"Poste": "", "Secteur": "", "Taille": "", "Email": "a@b.com"}
    icp = {"job_titles": [], "sectors": [], "company_size": []}
    assert _calculate_score(prospect, icp)["total"] == 10


def test_score_partial_title_match():
    prospect = {"Poste": "Directeur des Opérations", "Secteur": "", "Taille": "", "Email": ""}
    icp = {"job_titles": ["Directeur Général"], "sectors": [], "company_size": []}
    score = _calculate_score(prospect, icp)["total"]
    assert score == 20


def test_score_sector_partial_match():
    prospect = {"Poste": "", "Secteur": "Services numériques B2B", "Taille": "", "Email": ""}
    icp = {"job_titles": [], "sectors": ["Services B2B"], "company_size": []}
    score = _calculate_score(prospect, icp)["total"]
    assert score >= 15


def test_score_size_present_but_no_match():
    prospect = {"Poste": "", "Secteur": "", "Taille": "201-500", "Email": ""}
    icp = {"job_titles": [], "sectors": [], "company_size": ["11-50"]}
    assert _calculate_score(prospect, icp)["total"] == 10  # taille présente mais no match exact


def test_score_never_exceeds_100():
    prospect = {
        "Poste": "CEO Directeur Général",
        "Secteur": "Services B2B Tech",
        "Taille": "51-200",
        "Email": "ceo@company.fr",
    }
    icp = {
        "job_titles": ["CEO", "Directeur Général"],
        "sectors": ["Services B2B", "Tech"],
        "company_size": ["51-200"],
    }
    assert _calculate_score(prospect, icp)["total"] <= 100


def test_score_empty_icp():
    # ICP vide : pas de titres/secteurs/tailles à matcher
    # Score = taille présente (10) + email vérifié (10) = 20
    prospect = {
        "Poste": "CEO",
        "Secteur": "Tech",
        "Taille": "11-50",
        "Email": "ceo@company.fr",
    }
    icp = {"job_titles": [], "sectors": [], "company_size": []}
    assert _calculate_score(prospect, icp)["total"] == 20
