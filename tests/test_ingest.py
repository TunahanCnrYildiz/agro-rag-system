from src.ingest import _is_junk_chunk

# The exact fertilizer table chunk that is wrongly dropped today.
NPK_CHUNK = (
    "Material Analysis N (%) P2O5 (%) K2O (%) "
    "Complete 14-14-14 14 14 14 Urea [CO(NH2)2] 46-0-0 46 0 0 Solophos"
)
GLYPH_GARBAGE = "Table 1 Schnute y e ei xi /g32 /g14 /g11 /g12 /g69 model"
PURE_NUMBERS = "12 34 56 78 90 12 34 56 78 90 12 34 56 78 90 12 34 56"
NORMAL_PROSE = (
    "Azotlu gübreleme bitki büyümesini artırır ve toprak besin dengesini "
    "korumak için önemlidir."
)


def test_npk_table_is_kept():
    assert _is_junk_chunk(NPK_CHUNK) is False


def test_glyph_garbage_is_dropped():
    assert _is_junk_chunk(GLYPH_GARBAGE) is True


def test_pure_numbers_dropped():
    assert _is_junk_chunk(PURE_NUMBERS) is True


def test_normal_prose_is_kept():
    assert _is_junk_chunk(NORMAL_PROSE) is False
