#!/usr/bin/env python3
"""神煞(Shensha)deterministic 单测 —— canonical 手验正反例。

神煞存在性 = 查表(非此即彼),无流派模糊,故用 canonical 手验单测,不套
validate_liuqin_det.py 那种模糊 master-gold。每颗星 ≥1 正例 + 验证反例。
所有预期值已按主流子平口径手算核对(参见 shensha.py docstring 流派约定)。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.bazi_ai.shensha import shensha_profile  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _prof(bazi: str, gender: str = "male") -> dict:
    return shensha_profile(bazi, gender=gender) or {}


def _star(prof: dict, name: str) -> dict:
    for s in prof.get("stars", []):
        if s["name"] == name:
            return s
    return {}


def _pos_chars(star: dict) -> set:
    """命中柱位的 (pillar,position,char) 集合。"""
    return {(l["pillar"], l["position"], l["char"]) for l in star.get("locations", [])}


# ---------------------------------------------------------------------------
# 基础契约
# ---------------------------------------------------------------------------
def test_invalid_bazi_returns_none():
    assert shensha_profile("这不是八字") is None
    assert shensha_profile("甲子 乙丑") is None  # 不足四柱
    assert shensha_profile("") is None


def test_profile_shape():
    prof = _prof("乙卯 戊寅 庚子 丙子")
    assert set(prof) >= {"day_master", "stars", "by_pillar", "summary", "summary_text"}
    assert prof["day_master"] == "庚"
    assert set(prof["by_pillar"]) == {"年柱", "月柱", "日柱", "时柱"}
    assert set(prof["summary"]) == {"auspicious", "neutral", "malefic", "counts"}
    # 每颗星结构完整
    for s in prof["stars"]:
        assert set(s) >= {"name", "category", "tier", "rule", "present", "locations", "description"}
        assert s["category"] in ("吉神", "平星", "凶神")
        assert s["tier"] in ("core", "secondary")
        assert isinstance(s["present"], bool)


def test_all_22plus_stars_listed():
    """v1 一级星盘每颗都应列出(无命中 present=False)。"""
    prof = _prof("乙卯 戊寅 庚子 丙子")
    names = {s["name"] for s in prof["stars"]}
    expected = {
        # 吉神 9
        "天乙贵人", "天德贵人", "月德贵人", "文昌", "学堂", "词馆", "金舆", "禄", "太极贵人",
        # 平星 4
        "驿马", "桃花", "华盖", "将星",
        # 凶神 10
        "羊刃", "空亡", "劫煞", "亡神", "灾煞", "孤辰", "寡宿", "魁罡", "血刃", "天罗地网",
    }
    missing = expected - names
    assert not missing, f"缺星: {missing}"


# ---------------------------------------------------------------------------
# 综合正例:乙卯 戊寅 庚子 丙子(已逐星手验)
# 年乙卯 月戊寅 日庚子 时丙子
# ---------------------------------------------------------------------------
def test_demo_present_set():
    prof = _prof("乙卯 戊寅 庚子 丙子")
    present = {s["name"] for s in prof["stars"] if s["present"]}
    # 年干乙阳贵子(日支/时支);月支寅→月德丙(时干/月支藏干);乙卯纳音水帝旺子(词馆)
    # 驿马:日支子三合→寅(月支);桃花:年支卯→子(日/时支);将星:卯(年)+子(日/时);亡神:年支卯→寅(月支)
    assert present == {"天乙贵人", "月德贵人", "词馆", "驿马", "桃花", "将星", "亡神"}


def test_demo_tianyi_year_stem_derivation():
    """天乙来自年干乙(阳贵子),非日干庚(丑未)。"""
    star = _star(_prof("乙卯 戊寅 庚子 丙子"), "天乙贵人")
    assert star["present"]
    chars = {l["char"] for l in star["locations"]}
    assert chars == {"子"}  # 庚贵人是丑未,均不在;乙阳贵是子


def test_demo_absent_stars():
    prof = _prof("乙卯 戊寅 庚子 丙子")
    # 庚→文昌亥/羊刃酉/禄申,均不在(branches=卯寅子子)
    for name in ("文昌", "羊刃", "禄", "天德贵人", "学堂", "金舆", "太极贵人",
                 "空亡", "劫煞", "灾煞", "孤辰", "寡宿", "魁罡", "血刃", "天罗地网", "华盖"):
        assert not _star(prof, name)["present"], f"{name} 应不现"


# ---------------------------------------------------------------------------
# 天乙贵人(年干+日干双查,阳贵/阴贵)
# ---------------------------------------------------------------------------
def test_tianyi_day_stem_甲_丑():
    """日干甲→丑未;时支丑命中(阳贵)。"""
    star = _star(_prof("甲子 丙寅 甲辰 乙丑"), "天乙贵人")
    assert star["present"]
    assert ("时柱", "时支", "丑") in _pos_chars(star)


def test_tianyi_乙_子申():
    """日干乙→子申;年支申 + 时支子命中。"""
    star = _star(_prof("壬申 丙寅 乙亥 丙子"), "天乙贵人")
    assert star["present"]


# ---------------------------------------------------------------------------
# 天德 / 月德(月支系)
# ---------------------------------------------------------------------------
def test_tiande_月支辰_壬():
    """月支辰 → 天德壬(干);日干壬命中。"""
    star = _star(_prof("甲子 戊辰 壬午 丙寅"), "天德贵人")
    assert star["present"]
    assert ("日柱", "日干", "壬") in _pos_chars(star)


def test_tiande_月支卯_申支():
    """月支卯 → 天德申(支,八卦坤位)。"""
    star = _star(_prof("甲子 癸卯 庚午 甲申"), "天德贵人")
    assert star["present"]
    assert ("时柱", "时支", "申") in _pos_chars(star)


def test_yuede_月支寅_丙():
    """月支寅三合 → 月德丙。"""
    star = _star(_prof("壬子 壬寅 庚午 丙子"), "月德贵人")
    assert star["present"]


# ---------------------------------------------------------------------------
# 日干 → 支 吉神:文昌 / 金舆 / 禄 / 羊刃
# ---------------------------------------------------------------------------
def test_wenchang_庚_亥():
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "文昌")
    assert star["present"]
    assert ("时柱", "时支", "亥") in _pos_chars(star)


def test_jinyu_庚_戌():
    star = _star(_prof("甲子 丙寅 庚午 丙戌"), "金舆")
    assert star["present"]
    assert ("时柱", "时支", "戌") in _pos_chars(star)


def test_lu_庚_申():
    star = _star(_prof("甲子 丙寅 庚午 甲申"), "禄")
    assert star["present"]
    assert ("时柱", "时支", "申") in _pos_chars(star)


def test_yangren_庚_酉():
    star = _star(_prof("甲子 丙寅 庚午 乙酉"), "羊刃")
    assert star["present"]
    assert ("时柱", "时支", "酉") in _pos_chars(star)


def test_yangren_甲_卯():
    """甲羊刃在卯(主流:阳干帝旺)。"""
    star = _star(_prof("甲子 丙寅 甲午 丁卯"), "羊刃")
    assert star["present"]
    assert ("时柱", "时支", "卯") in _pos_chars(star)


# ---------------------------------------------------------------------------
# 纳音学堂 / 词馆(年柱纳音五行 长生 / 帝旺)
# ---------------------------------------------------------------------------
def test_xuetang_nayin_木_亥():
    """年柱戊辰纳音木 → 学堂=木长生亥。"""
    star = _star(_prof("戊辰 庚申 甲午 乙亥"), "学堂")
    assert star["present"]
    assert ("时柱", "时支", "亥") in _pos_chars(star)


def test_ciguan_nayin_水_子():
    """年柱乙卯纳音水 → 词馆=水帝旺子。"""
    star = _star(_prof("乙卯 戊寅 庚子 丙子"), "词馆")
    assert star["present"]
    assert ("日柱", "日支", "子") in _pos_chars(star)


# ---------------------------------------------------------------------------
# 太极贵人(支对须同现)
# ---------------------------------------------------------------------------
def test_taiji_庚_寅亥_同现():
    """日干庚→寅亥须同现;月支寅 + 时支亥。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "太极贵人")
    assert star["present"]
    chars = {l["char"] for l in star["locations"]}
    assert chars == {"寅", "亥"}


def test_taiji_仅一支_不现():
    """只有寅、无亥 → 太极不现。"""
    star = _star(_prof("甲子 丙寅 庚午 丙子"), "太极贵人")
    assert not star["present"]


# ---------------------------------------------------------------------------
# 三合系(年支+日支双查):驿马 / 桃花 / 华盖 / 将星 / 劫煞 / 亡神 / 灾煞
# 用 甲子 丙寅 庚午 丁亥:branches=子寅午亥
# 年支子→申子辰(水);日支午→寅午戌(火)
# ---------------------------------------------------------------------------
def test_horse_驿马():
    """年支子→申子辰→驿马寅;日支午→寅午戌→驿马申。寅在月支命中。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "驿马")
    assert star["present"]
    assert ("月柱", "月支", "寅") in _pos_chars(star)


def test_peach_桃花():
    """年支子→申子辰→桃花酉;日支午→寅午戌→桃花卯。本盘酉卯皆不在 → 不现。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "桃花")
    assert not star["present"]


def test_huagai_华盖():
    """年支子→申子辰→华盖辰;日支午→寅午戌→华盖戌。本盘辰戌皆不在 → 不现。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "华盖")
    assert not star["present"]


def test_jiangxing_将星():
    """年支子→申子辰→将星子;子在年支命中。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "将星")
    assert star["present"]
    assert ("年柱", "年支", "子") in _pos_chars(star)


def test_jiesha_劫煞():
    """年支子→申子辰→劫煞巳;日支午→寅午戌→劫煞亥。亥在时支命中。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "劫煞")
    assert star["present"]
    assert ("时柱", "时支", "亥") in _pos_chars(star)


def test_zhaisha_灾煞():
    """年支子→申子辰→灾煞午;日支午→寅午戌→灾煞子。子/午皆在。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "灾煞")
    assert star["present"]


def test_wangshen_亡神():
    """年支子→申子辰→亡神亥;日支午→寅午戌→亡神巳。亥在时支。"""
    star = _star(_prof("甲子 丙寅 庚午 丁亥"), "亡神")
    assert star["present"]


# ---------------------------------------------------------------------------
# 空亡(日柱旬空,复用 kong_wang)
# ---------------------------------------------------------------------------
def test_kongwang_present():
    """日柱庚子旬空→辰巳;年支辰命中。"""
    star = _star(_prof("甲辰 丙寅 庚子 丙子"), "空亡")
    assert star["present"]
    assert star.get("kong_wang") == ["辰", "巳"]
    assert ("年柱", "年支", "辰") in _pos_chars(star)


def test_kongwang_absent():
    """日柱庚子旬空辰巳,branches=卯寅子子 无辰巳 → 不现但仍列出。"""
    star = _star(_prof("乙卯 戊寅 庚子 丙子"), "空亡")
    assert not star["present"]
    assert star.get("kong_wang") == ["辰", "巳"]


# ---------------------------------------------------------------------------
# 年支系:孤辰寡宿 / 血刃
# ---------------------------------------------------------------------------
def test_guchen_年支亥_孤寅():
    """年支亥→亥子丑三会→孤辰寅、寡宿戌;寅在月支 → 孤辰现。"""
    star = _star(_prof("癸亥 甲寅 庚午 丁亥"), "孤辰")
    assert star["present"]
    assert ("月柱", "月支", "寅") in _pos_chars(star)


def test_guasu_年支亥_寡戌_absent():
    """同盘寡宿戌不在 → 寡宿不现。"""
    star = _star(_prof("癸亥 甲寅 庚午 丁亥"), "寡宿")
    assert not star["present"]


def test_xueren_年支卯_巳():
    """年支卯→血刃巳;时支巳命中。"""
    star = _star(_prof("乙卯 戊寅 庚午 辛巳"), "血刃")
    assert star["present"]
    assert ("时柱", "时支", "巳") in _pos_chars(star)


# ---------------------------------------------------------------------------
# 日柱 / 性别系:魁罡 / 天罗地网
# ---------------------------------------------------------------------------
def test_kuigang_庚辰():
    star = _star(_prof("甲子 丙寅 庚辰 丙子"), "魁罡")
    assert star["present"]


def test_kuigang_absent():
    star = _star(_prof("乙卯 戊寅 庚子 丙子"), "魁罡")
    assert not star["present"]


def test_tianluodiwang_male_天罗():
    """男命忌天罗(戌亥);年支戌 + 时支亥 → 现。"""
    star = _star(_prof("甲戌 丙寅 庚午 丁亥", gender="male"), "天罗地网")
    assert star["present"]


def test_tianluodiwang_female_地网():
    """女命忌地网(辰巳);年支辰 → 现。男命同盘看天罗(戌亥)不现。"""
    prof_f = _prof("甲辰 丙寅 庚午 丙子", gender="female")
    assert _star(prof_f, "天罗地网")["present"]
    prof_m = _prof("甲辰 丙寅 庚午 丙子", gender="male")
    # 男命看天罗(戌亥),branches=辰寅午子 无戌亥
    assert not _star(prof_m, "天罗地网")["present"]


# ---------------------------------------------------------------------------
# 反向索引 / 汇总
# ---------------------------------------------------------------------------
def test_by_pillar_and_summary():
    prof = _prof("乙卯 戊寅 庚子 丙子")
    # 日柱应有天乙/词馆/桃花/将星
    assert "天乙贵人" in prof["by_pillar"]["日柱"]
    assert "桃花" in prof["by_pillar"]["日柱"]
    # 月柱:月德/驿马/亡神
    assert set(["月德贵人", "驿马", "亡神"]).issubset(set(prof["by_pillar"]["月柱"]))
    counts = prof["summary"]["counts"]
    assert counts["吉神"] == 3  # 天乙/月德/词馆
    assert counts["平星"] == 3  # 驿马/桃花/将星
    assert counts["凶神"] == 1  # 亡神
    assert "天乙贵人" in prof["summary_text"]


def test_summary_neutral_key():
    """平星走 neutral 键(非 malefic)。"""
    prof = _prof("乙卯 戊寅 庚子 丙子")
    assert "驿马" in prof["summary"]["neutral"]
    assert "驿马" not in prof["summary"]["malefic"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
