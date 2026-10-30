"""FAO-56 Tables 11 and 12, parsed - on a fragment shaped like the real page."""
from scripts import build_crop_stages as b

PAGE = """
<p>TABLE 11. Lengths of crop development stages</p>
<table>
<tr><td>Crop</td><td>Init.</td><td>Dev.</td><td>Mid</td><td>Late</td><td>Total</td><td>Plant Date</td><td>Region</td></tr>
<tr><td>a. Small Vegetables</td></tr>
<tr><td>Carrots</td><td>20</td><td>30</td><td>50/30</td><td>20</td><td>100</td><td>Oct/Jan</td><td>Arid climate</td></tr>
<tr><td>30</td><td>40</td><td>60</td><td>20</td><td>150</td><td>Feb/Mar</td><td>Mediterranean</td></tr>
<tr><td>Crucifers<SUP>1</SUP></td><td>20</td><td>30</td><td>20</td><td>10</td><td>80</td><td>April</td><td>Mediterranean</td></tr>
</table>
<p>TABLE 12. Single (time-averaged) crop coefficients</p>
<table>
<tr><td>Crop</td><td></td><td>Kc mid</td><td>Kc end</td><td>Height</td></tr>
<tr><td>b. Vegetables - Solanum Family</td><td>0.6</td><td>1.15</td><td>0.80</td><td></td></tr>
<tr><td COLSPAN=2>Sweet Peppers (bell)</td><td><br></td><td>1.05<SUP>2</SUP></td><td>0.90</td><td>0.7</td></tr>
<tr><td COLSPAN=2>Cantaloupe</td><td>0.5</td><td>0.85</td><td>0.60</td><td>0.3</td></tr>
<tr><td COLSPAN=2>Onions</td><td></td><td></td><td></td><td></td></tr>
<tr><td></td><td>- dry</td><td></td><td>1.05</td><td>0.75</td><td>0.4</td></tr>
</table>
<p>TABLE 13. something else</p>
"""


def test_a_continuation_row_belongs_to_the_crop_above():
    rows = b.parse_stages(PAGE)
    assert [(r["crop"], r["region"]) for r in rows] == [
        ("Carrots", "Arid climate"), ("Carrots", "Mediterranean"),
        ("Crucifers", "Mediterranean")]
    assert rows[1]["plant"] == "Feb/Mar" and rows[1]["total"] == "150"


def test_published_alternatives_stay_as_published():
    assert b.parse_stages(PAGE)[0]["mid"] == "50/30"


def test_a_footnote_mark_never_fuses_into_the_number():
    """"1.05" with footnote 2 must not read "1.052"."""
    pepper = next(r for r in b.parse_kc(PAGE) if r["crop"] == "Sweet Peppers (bell)")
    assert pepper["kc_mid"] == "1.05"
    assert b.parse_stages(PAGE)[2]["crop"] == "Crucifers"


def test_a_blank_kc_ini_takes_the_groups_and_says_so():
    kc = {(r["crop"], r["variant"]): r for r in b.parse_kc(PAGE)}
    pepper = kc[("Sweet Peppers (bell)", None)]
    assert (pepper["kc_ini"], pepper["kc_ini_from_group"]) == ("0.6", True)
    melon = kc[("Cantaloupe", None)]
    assert (melon["kc_ini"], melon["kc_ini_from_group"]) == ("0.5", False)


def test_a_variant_row_is_named_under_its_crop():
    onion = next(r for r in b.parse_kc(PAGE) if r["variant"] == "- dry")
    assert (onion["crop"], onion["kc_mid"], onion["kc_end"]) == ("Onions", "1.05", "0.75")
    assert not any(r["crop"] == "Onions" and r["variant"] is None for r in b.parse_kc(PAGE))


def test_the_output_carries_its_source():
    meta = b.build(PAGE, "2026-10-30")["meta"]
    assert meta["url"] == b.SOURCE_URL and meta["retrieved"] == "2026-10-30"
