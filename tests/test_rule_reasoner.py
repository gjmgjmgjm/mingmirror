"""Regression tests for the symbolic rule reasoner.

These tests target three known failure cases from the BaziQA benchmark where
year-based symbolic scoring previously mis-ranked the options.
"""

from tools.bazi_ai.rule_reasoner import (
    Candidate,
    RuleReasoner,
    apply_rule_reasoner,
    arbitrate_shortlist,
    format_shortlist_block,
    is_year_asking_question,
    rank_domain_candidates,
    rank_year_candidates,
)


class TestRuleReasonerRegressions:
    def test_p025_q2_father_death_year(self):
        """P025-Q2: father death year should rank 1959 (A) highest."""
        reasoner = RuleReasoner(
            bazi="甲午 丁卯 癸酉 庚申",
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
        )
        options = [
            "A 1959 己亥年",
            "B 1963 癸卯年",
            "C 1964 甲辰年",
            "D 1969 己酉年",
        ]
        candidate = reasoner.reason_parent_death_year(
            "命主父亲于哪年去世?", options
        )
        assert candidate is not None
        assert candidate.option == "A"
        assert candidate.text == "A 1959 己亥年"

    def test_p026_q7_second_marriage_year(self):
        """P026-Q7: second marriage year should rank 2020 (D) highest."""
        reasoner = RuleReasoner(
            bazi="癸亥 壬戌 庚辰 辛巳",
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
        )
        options = ["2017", "2018", "2019", "2020"]
        candidate = reasoner.reason_marriage_year(
            "命主已经离婚，第二婚是哪一年？", options
        )
        assert candidate is not None
        assert candidate.option == "D"
        assert candidate.text == "2020"

    def test_p026_q8_children_year(self):
        """P026-Q8: child birth year should rank 2021 (D) highest."""
        reasoner = RuleReasoner(
            bazi="癸亥 壬戌 庚辰 辛巳",
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
        )
        options = ["2018", "2019", "2020", "2021"]
        candidate = reasoner.reason_children_year(
            "命主目前有一个孩子，那年出生？", options
        )
        assert candidate is not None
        assert candidate.option == "D"
        assert candidate.text == "2021"


class TestRuleShortlist:
    """Phase 4: top-k year shortlist for soft LLM guidance."""

    def test_rank_returns_sorted_top_candidates(self):
        ranked = rank_year_candidates(
            "癸亥 壬戌 庚辰 辛巳",
            "命主已经离婚，第二婚是哪一年？",
            ["2017", "2018", "2019", "2020"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
            top_k=2,
        )
        assert len(ranked) == 2
        assert ranked[0].score >= ranked[1].score
        assert ranked[0].option == "D"
        # Gold (2020) must be inside the top-2 shortlist for this known case.
        assert {c.option for c in ranked} == {"C", "D"} or ranked[0].option == "D"

    def test_format_shortlist_block_mentions_options(self):
        ranked = rank_year_candidates(
            "甲午 丁卯 癸酉 庚申",
            "命主父亲于哪年去世?",
            [
                "A 1959 己亥年",
                "B 1963 癸卯年",
                "C 1964 甲辰年",
                "D 1969 己酉年",
            ],
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
            top_k=2,
        )
        block = format_shortlist_block(ranked, top_k=2)
        assert "规则引擎应期 shortlist" in block
        assert "选项A" in block or "选项" in block
        assert ranked[0].option in block

    def test_hard_override_disabled_pending_recalibration(self):
        """Hard override is intentionally off; ranking still works for shortlist."""
        answer = apply_rule_reasoner(
            "甲午 丁卯 癸酉 庚申",
            "命主父亲于哪年去世?",
            [
                "A 1959 己亥年",
                "B 1963 癸卯年",
                "C 1964 甲辰年",
                "D 1969 己酉年",
            ],
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
            min_confidence="low",
        )
        assert answer is None
        ranked = rank_year_candidates(
            "甲午 丁卯 癸酉 庚申",
            "命主父亲于哪年去世?",
            [
                "A 1959 己亥年",
                "B 1963 癸卯年",
                "C 1964 甲辰年",
                "D 1969 己酉年",
            ],
            gender="male",
            birth_date="1954-03-18",
            birth_time="15:00",
            for_shortlist=False,
        )
        assert ranked and ranked[0].option == "A"

    def test_rank_empty_for_non_year_question(self):
        ranked = rank_year_candidates(
            "甲午 丁卯 癸酉 庚申",
            "命主适合从事什么职业？",
            ["A 公务员", "B 创业", "C 技术", "D 自由职业"],
            gender="male",
            birth_date="1954-03-18",
        )
        assert ranked == []

    def test_extract_years_from_chinese_suffix(self):
        """Regression: ``2010年`` must parse (Unicode \\b previously broke this)."""
        from tools.bazi_ai.rule_reasoner import _extract_years

        assert _extract_years("A 2010年结婚，两个小孩") == [2010]
        assert _extract_years("2020") == [2020]
        assert _extract_years("A 1959 己亥年") == [1959]

    def test_expanded_events_are_shortlist_only(self):
        """move/legal must not hard-override the LLM even at high confidence."""
        # 搬迁 year question — covered for shortlist but not hard override
        answer = apply_rule_reasoner(
            "癸亥 壬戌 庚辰 辛巳",
            "命主于哪一年有家宅搬迁？",
            ["2017", "2018", "2019", "2020"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
            min_confidence="low",
        )
        assert answer is None
        ranked = rank_year_candidates(
            "癸亥 壬戌 庚辰 辛巳",
            "命主于哪一年有家宅搬迁？",
            ["2017", "2018", "2019", "2020"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
        )
        assert len(ranked) >= 1

    def test_children_gated_soft_shortlist_known_case(self):
        """Children is score-gated (not hard-excluded); this case gold is top-1."""
        ranked = rank_year_candidates(
            "癸亥 壬戌 庚辰 辛巳",
            "命主目前有一个孩子，那年出生？",
            ["2018", "2019", "2020", "2021"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
            for_shortlist=True,
        )
        assert ranked and ranked[0].option == "D"
        assert ranked[0].score >= 0.2
        ranked_all = rank_year_candidates(
            "癸亥 壬戌 庚辰 辛巳",
            "命主目前有一个孩子，那年出生？",
            ["2018", "2019", "2020", "2021"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
            for_shortlist=False,
        )
        assert ranked_all and ranked_all[0].option == "D"

    def test_status_mcq_not_year_asking(self):
        """Status questions must not receive year shortlist (P033-Q39 class)."""
        assert not is_year_asking_question(
            "截至2017年9月，哪项符合命主感情与婚姻状况？",
            ["A 已婚", "B 离婚", "C 恋爱中", "D 从未结婚"],
        )
        assert is_year_asking_question(
            "命主在那一年结婚？",
            ["2017", "2018", "2019", "2020"],
        )

    def test_status_marriage_no_shortlist_injection(self):
        ranked = rank_year_candidates(
            "癸亥 壬戌 庚辰 辛巳",
            "截至2017年9月，哪项符合命主感情与婚姻状况？",
            ["A 2015结婚", "B 2016离婚", "C 2017再婚", "D 从未结婚"],
            gender="male",
            birth_date="1983-10-19",
            birth_time="09:58",
            for_shortlist=True,
        )
        assert ranked == []

    def test_arbitrate_prefers_free_when_shortlist_weak(self):
        weak = [
            Candidate(option="A", text="2017", score=0.1, confidence="low"),
            Candidate(option="B", text="2018", score=0.0, confidence="low"),
        ]
        chosen, reason = arbitrate_shortlist("D", "A", weak)
        assert chosen == "D"
        assert reason == "free_fallback"

    def test_arbitrate_prefers_guided_when_high_conf_conflict(self):
        strong = [
            Candidate(option="A", text="2017", score=1.2, confidence="high"),
            Candidate(option="B", text="2018", score=0.3, confidence="low"),
        ]
        chosen, reason = arbitrate_shortlist("C", "A", strong)
        assert chosen == "A"
        # free outside shortlist + guided hits top-1 → guided (tag may be
        # guided_top1_free_out or guided_high_conf depending on path order).
        assert reason in ("guided_high_conf", "guided_top1_free_out", "guided_high_conf_sl")

    def test_arbitrate_agree_and_free_in_shortlist(self):
        sl = [
            Candidate(option="A", text="2017", score=0.8, confidence="medium"),
            Candidate(option="B", text="2018", score=0.4, confidence="low"),
        ]
        assert arbitrate_shortlist("A", "A", sl)[1] == "agree"
        # Free is shortlist #2 (weak); policy prefers guided top-1 when score≥0.4.
        chosen, reason = arbitrate_shortlist("B", "A", sl)
        assert chosen == "A"
        assert reason in ("guided_top1_over_weak_free", "guided_high_conf")

    def test_near_tie_shortlist_prompt_warns(self):
        close = [
            Candidate(option="D", text="2020", score=0.9, confidence="medium", reasons=["半三合"]),
            Candidate(option="C", text="2018", score=0.7, confidence="low", reasons=["大运"]),
        ]
        block = format_shortlist_block(close, top_k=2)
        assert "近并列" in block
        assert "禁止默认选排序第一" in block

    def test_domain_career_ranks_options_offline(self):
        ranked = rank_domain_candidates(
            "甲午 丁卯 癸酉 庚申",
            "命主目前的职业是什么？",
            ["A 自己创业做贸易", "B 公务员", "C 自由职业艺术家", "D 无业"],
            gender="male",
            top_k=2,
            for_injection=False,
        )
        # Diagnostics only; injection path always empty.
        assert rank_domain_candidates(
            "甲午 丁卯 癸酉 庚申",
            "命主目前的职业是什么？",
            ["A 自己创业做贸易", "B 公务员"],
            for_injection=True,
        ) == []
        if ranked:
            assert ranked[0].score >= ranked[-1].score

    def test_domain_hint_block_for_career(self):
        from tools.bazi_ai.rule_reasoner import format_domain_hint_block

        block = format_domain_hint_block(
            "甲午 丁卯 癸酉 庚申",
            "命主目前的职业是什么？",
            gender="male",
        )
        assert "结构取象提示" in block
        assert "职业" in block or "十神" in block
        # Must NOT rank option letters (no A/B shortlist).
        assert "选项A" not in block

    def test_domain_skips_year_questions(self):
        ranked = rank_domain_candidates(
            "癸亥 壬戌 庚辰 辛巳",
            "命主在那一年结婚？",
            ["2017", "2018", "2019", "2020"],
            gender="male",
        )
        assert ranked == []
