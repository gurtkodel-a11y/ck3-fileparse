"""
ck3.geography
~~~~~~~~~~~~~
Region definitions and proximity zones for CK3's map.

Regions are coarse groupings of kingdom-tier title keys.  The "proximity"
or "zone" computed here is not purely a measure of physical distance.
It is better understood as an approximation of *likely contact and
interaction* between polities — a composite of many factors:

  - Literal geographic distance
  - Terrain barriers (mountains, seas, deserts) that impede or channel movement
  - The de-jure title network, which reflects historical patterns of political
    organisation, trade, and cultural exchange
  - Shared coastlines and navigable routes (e.g. the Irish Sea, North Sea)
  - The fact that some political boundaries follow natural chokepoints that
    also limit interaction

Because we derive zone membership partly from the de-jure hierarchy, we
will naturally capture some of these non-physical factors — a duchy deep
in the Alps "feels" farther than the same straight-line distance across
open steppe.  That is a feature, not a bug.

The zone_between() function returns a numeric proximity zone (0–3):
    0 = local       — same broad region; regular contact expected
    1 = nearby      — directly adjacent region; significant but less frequent contact
    2 = continental — two hops; known at the level of trade/diplomacy/rumour
    3 = global      — three or more hops; known only in the abstract, if at all

Future work could refine this further with terrain costs, sea-lane weights,
or cultural affinity modifiers.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Kingdom key → region name
# ---------------------------------------------------------------------------

#: Maps every CK3 kingdom / empire title key to a broad geographic region.
#: Not exhaustive — unknown keys fall back to "global".
KINGDOM_TO_REGION: dict[str, str] = {
    # British Isles
    "k_ireland":       "british_isles",
    "k_england":       "british_isles",
    "k_scotland":      "british_isles",
    "k_wales":         "british_isles",
    "k_brittany":      "british_isles",   # culturally Celtic; close sea-crossing
    "e_britannia":     "british_isles",

    # Scandinavia
    "k_norway":        "scandinavia",
    "k_denmark":       "scandinavia",
    "k_sweden":        "scandinavia",
    "k_finland":       "scandinavia",
    "k_gotland":       "scandinavia",
    "e_scandinavia":   "scandinavia",

    # Western Europe
    "k_france":        "western_europe",
    "k_west_francia":  "western_europe",
    "k_burgundy":      "western_europe",
    "k_lotharingia":   "western_europe",
    "k_frisia":        "western_europe",
    "k_germany":       "western_europe",
    "k_east_francia":  "western_europe",
    "k_italy":         "western_europe",
    "k_lombardy":      "western_europe",
    "k_swiss":         "western_europe",
    "e_france":        "western_europe",
    "e_hre":           "western_europe",
    "e_italia":        "western_europe",

    # Iberia
    "k_castille":      "iberia",
    "k_aragon":        "iberia",
    "k_portugal":      "iberia",
    "k_navarra":       "iberia",
    "k_leon":          "iberia",
    "k_galicia":       "iberia",
    "k_asturias":      "iberia",
    "k_badajoz":       "iberia",
    "k_murcia":        "iberia",
    "k_valencia":      "iberia",
    "k_toledo":        "iberia",
    "k_granada":       "iberia",
    "e_spain":         "iberia",
    "e_hispania":      "iberia",

    # Mediterranean islands / southern Italy
    "k_sicily":        "mediterranean",
    "k_sardinia":      "mediterranean",
    "k_corsica":       "mediterranean",
    "k_cyprus":        "mediterranean",
    "k_crete":         "mediterranean",
    "k_majorca":       "mediterranean",
    "k_naples":        "mediterranean",
    "k_calabria":      "mediterranean",
    "k_apulia":        "mediterranean",

    # Balkans
    "k_croatia":       "balkans",
    "k_dalmatia":      "balkans",
    "k_serbia":        "balkans",
    "k_bulgaria":      "balkans",
    "k_greece":        "balkans",
    "k_albania":       "balkans",
    "k_bosnia":        "balkans",
    "k_rascia":        "balkans",
    "k_hungary":       "balkans",     # geographically overlaps; treat as Balkans-adjacent
    "e_byzantium":     "balkans",
    "e_latin_empire":  "balkans",

    # Eastern Europe
    "k_poland":        "eastern_europe",
    "k_bohemia":       "eastern_europe",
    "k_moravia":       "eastern_europe",
    "k_pomerania":     "eastern_europe",
    "k_silesia":       "eastern_europe",
    "k_austria":       "eastern_europe",
    "k_carinthia":     "eastern_europe",
    "k_wallachia":     "eastern_europe",
    "k_moldavia":      "eastern_europe",
    "k_transylvania":  "eastern_europe",
    "e_carpathia":     "eastern_europe",

    # Baltics
    "k_lithuania":     "baltics",
    "k_livonia":       "baltics",
    "k_estonia":       "baltics",
    "k_latgalia":      "baltics",
    "k_prussia":       "baltics",
    "k_courland":      "baltics",

    # Rus / Steppe
    "k_rus":           "rus",
    "k_novgorod":      "rus",
    "k_kiev":          "rus",
    "k_ryazan":        "rus",
    "k_vladimir":      "rus",
    "k_moscow":        "rus",
    "k_cumania":       "rus",
    "k_volga_bulgaria":"rus",
    "e_russia":        "rus",
    "e_ruthenia":      "rus",

    # Caucasus
    "k_georgia":       "caucasus",
    "k_armenia":       "caucasus",
    "k_alania":        "caucasus",
    "k_azerbaijan":    "caucasus",
    "k_abkhazia":      "caucasus",

    # Middle East / Levant
    "k_syria":         "middle_east",
    "k_jerusalem":     "middle_east",
    "k_egypt":         "middle_east",
    "k_arabia":        "middle_east",
    "k_mesopotamia":   "middle_east",
    "k_anatolia":      "middle_east",
    "k_rum":           "middle_east",
    "k_oman":          "middle_east",
    "k_yemen":         "middle_east",
    "k_hejaz":         "middle_east",
    "k_najd":          "middle_east",
    "e_arabia":        "middle_east",
    "e_byzantium_successor": "middle_east",

    # Persia / Central Asia border
    "k_persia":        "persia",
    "k_khurasan":      "persia",
    "k_khorasan":      "persia",
    "k_transoxiana":   "persia",
    "k_khiva":         "persia",
    "k_tabriz":        "persia",
    "k_shirvan":       "persia",
    "k_mazandaran":    "persia",
    "k_fars":          "persia",
    "k_isfahan":       "persia",
    "e_persia":        "persia",

    # North Africa
    "k_morocco":       "north_africa",
    "k_ifriqiya":      "north_africa",
    "k_algeria":       "north_africa",
    "k_tripolitania":  "north_africa",
    "k_fezzan":        "north_africa",
    "k_nubia":         "north_africa",
    "k_sahara":        "north_africa",
    "e_maghreb":       "north_africa",

    # Sub-Saharan Africa
    "k_mali":          "sub_saharan_africa",
    "k_ghana":         "sub_saharan_africa",
    "k_songhai":       "sub_saharan_africa",
    "k_fula":          "sub_saharan_africa",
    "k_kanem_bornu":   "sub_saharan_africa",
    "k_ethiopia":      "sub_saharan_africa",
    "k_somalia":       "sub_saharan_africa",
    "k_swahili":       "sub_saharan_africa",
    "k_kongo":         "sub_saharan_africa",
    "e_ethiopia":      "sub_saharan_africa",

    # Central Asia
    "k_khwarezm":      "central_asia",
    "k_fergana":       "central_asia",
    "k_samarkand":     "central_asia",
    "k_bokhara":       "central_asia",
    "k_kabulistan":    "central_asia",
    "k_merv":          "central_asia",

    # South Asia
    "k_gujarat":       "south_asia",
    "k_delhi":         "south_asia",
    "k_sindh":         "south_asia",
    "k_rajputana":     "south_asia",
    "k_bengal":        "south_asia",
    "k_malwa":         "south_asia",
    "k_deccan":        "south_asia",
    "k_lanka":         "south_asia",
    "k_punjab":        "south_asia",
    "k_orissa":        "south_asia",
    "e_india":         "south_asia",

    # Southeast Asia
    "k_pagan":         "southeast_asia",
    "k_khmer":         "southeast_asia",
    "k_champa":        "southeast_asia",
    "k_java":          "southeast_asia",
    "k_vietnam":       "southeast_asia",
    "k_dai_viet":      "southeast_asia",

    # Far East
    "k_tibet":         "far_east",
    "k_yunnan":        "far_east",
    "k_qocho":         "far_east",
    "k_tangut":        "far_east",
}

# ---------------------------------------------------------------------------
# Region adjacency (approximate, land/short-sea)
# ---------------------------------------------------------------------------

REGION_ADJACENCY: dict[str, set[str]] = {
    "british_isles":    {"western_europe", "scandinavia"},
    "scandinavia":      {"british_isles", "western_europe", "baltics", "rus"},
    "western_europe":   {"british_isles", "scandinavia", "iberia", "mediterranean", "eastern_europe"},
    "iberia":           {"western_europe", "north_africa"},
    "mediterranean":    {"western_europe", "iberia", "balkans", "middle_east", "north_africa"},
    "balkans":          {"western_europe", "eastern_europe", "caucasus", "middle_east", "mediterranean"},
    "eastern_europe":   {"western_europe", "scandinavia", "baltics", "rus", "balkans"},
    "baltics":          {"scandinavia", "eastern_europe", "rus"},
    "rus":              {"scandinavia", "baltics", "eastern_europe", "caucasus", "central_asia"},
    "caucasus":         {"rus", "balkans", "middle_east", "persia"},
    "middle_east":      {"mediterranean", "north_africa", "persia", "caucasus", "south_asia"},
    "persia":           {"middle_east", "caucasus", "central_asia", "south_asia"},
    "north_africa":     {"iberia", "mediterranean", "middle_east", "sub_saharan_africa"},
    "sub_saharan_africa": {"north_africa"},
    "central_asia":     {"rus", "persia", "south_asia", "far_east"},
    "south_asia":       {"middle_east", "persia", "central_asia", "southeast_asia"},
    "southeast_asia":   {"south_asia", "far_east"},
    "far_east":         {"central_asia", "south_asia", "southeast_asia"},
}

_ALL_REGIONS = set(REGION_ADJACENCY)

# ---------------------------------------------------------------------------
# Zone computation
# ---------------------------------------------------------------------------

def zone_between(player_region: str, faith_region: str) -> int:
    """
    Return the interaction-proximity zone (0–3) between two regions.

    This is not a pure measure of physical distance.  It approximates the
    *expected level of contact* between polities — shaped by geography,
    terrain, sea routes, and the de-jure title network.

      0  — local      (same region)
      1  — nearby     (directly adjacent region)
      2  — continental (two hops — known through diplomacy / trade / rumour)
      3  — global     (three or more hops — known only in the abstract)
    """
    if player_region == faith_region:
        return 0
    adj = REGION_ADJACENCY.get(player_region, set())
    if faith_region in adj:
        return 1
    # BFS one more hop
    two_hop: set[str] = set()
    for r in adj:
        two_hop |= REGION_ADJACENCY.get(r, set())
    two_hop -= adj
    two_hop.discard(player_region)
    if faith_region in two_hop:
        return 2
    return 3


def kingdom_to_region(kingdom_key: str) -> str:
    """Return the region for a kingdom/empire title key, or 'global' if unknown."""
    return KINGDOM_TO_REGION.get(kingdom_key, "global")
