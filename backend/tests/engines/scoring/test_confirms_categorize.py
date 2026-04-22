"""Tests de categorize + apply_confirm_weights (Fase 5.3b).

Port literal de Observatory `scoring.py:_categorize_confirm()` líneas
203-215 y del bloque de dedup L310-318.

Casos cubiertos:
- Cada categoría Observatory matchea el prefijo correcto
- VolHigh usa substring `"x avg"` (no prefix)
- Unknown descriptions → None (paridad Observatory: peso 0)
- Dedup: mismo cat aparece 2 veces → solo el primero suma
- Orden del input determina cuál gana en duplicados
- Categoría sin peso en fixture → peso 0
"""

from __future__ import annotations

from engines.scoring.confirms import apply_confirm_weights, categorize_confirm

# ═══════════════════════════════════════════════════════════════════════════
# categorize_confirm
# ═══════════════════════════════════════════════════════════════════════════


class TestCategorizeAllCategories:
    def test_fzarel(self) -> None:
        assert categorize_confirm("FzaRel +1.5% vs SPY") == "FzaRel"

    def test_bb_sup_d(self) -> None:
        assert categorize_confirm("BB sup D ($450.0)") == "BBsup_D"

    def test_bb_inf_d(self) -> None:
        assert categorize_confirm("BB inf D ($400.0)") == "BBinf_D"

    def test_bb_sup_1h(self) -> None:
        assert categorize_confirm("BB sup 1H ($445.5)") == "BBsup_1H"

    def test_bb_inf_1h(self) -> None:
        assert categorize_confirm("BB inf 1H ($410.5)") == "BBinf_1H"

    def test_vol_creciente(self) -> None:
        assert categorize_confirm("Vol creciente 4 velas") == "VolSeq"

    def test_vol_high_via_substring(self) -> None:
        # Observatory: `"x avg" in desc` — NO startswith.
        assert categorize_confirm("Vol 1.6x avg") == "VolHigh"

    def test_gap(self) -> None:
        assert categorize_confirm("Gap alcista +1.25%") == "Gap"
        assert categorize_confirm("Gap bajista -1.5%") == "Gap"

    def test_squeeze(self) -> None:
        assert categorize_confirm("Squeeze → Expansión (ruptura)") == "SqExp"

    def test_div_spy(self) -> None:
        assert categorize_confirm(
            "Div SPY (QQQ:-1.0% vs SPY:+0.5%) → VERIFICAR CATALIZADOR"
        ) == "DivSPY"


class TestCategorizeUnknown:
    def test_unknown_returns_none(self) -> None:
        assert categorize_confirm("Some random confirm text") is None

    def test_empty_returns_none(self) -> None:
        assert categorize_confirm("") is None

    def test_trigger_pattern_not_a_confirm_returns_none(self) -> None:
        # Descripciones de triggers (Doji, Martillo, etc.) no deben
        # clasificarse como confirms.
        assert categorize_confirm("Doji BB sup") is None
        assert categorize_confirm("Envolvente alcista 1H") is None


class TestCategorizeOrderPrecedence:
    def test_bb_d_before_bb_1h_in_ordering(self) -> None:
        # El orden observatory chequea "BB sup D" antes que "BB sup 1H"
        # — un hipotético "BB sup D 1H" iría a BBsup_D. Verificamos que
        # los prefijos sean no ambiguos en la práctica.
        assert categorize_confirm("BB sup D ($450)") == "BBsup_D"
        assert categorize_confirm("BB sup 1H ($450)") == "BBsup_1H"


# ═══════════════════════════════════════════════════════════════════════════
# apply_confirm_weights
# ═══════════════════════════════════════════════════════════════════════════


class TestApplyConfirmWeightsBasic:
    def test_empty_list_zero_sum(self) -> None:
        weights = {"FzaRel": 4.0}
        total, items = apply_confirm_weights([], weights)
        assert total == 0.0
        assert items == []

    def test_single_confirm_sums(self) -> None:
        confirms = [{"d": "FzaRel +1.5% vs SPY", "tf": "D", "sg": "CONFIRM"}]
        weights = {"FzaRel": 4.0}
        total, items = apply_confirm_weights(confirms, weights)
        assert total == 4.0
        assert len(items) == 1
        assert items[0]["category"] == "FzaRel"
        assert items[0]["weight"] == 4.0

    def test_multiple_distinct_categories_all_sum(self) -> None:
        confirms = [
            {"d": "FzaRel +1.5% vs SPY", "tf": "D", "sg": "CONFIRM"},
            {"d": "BB inf 1H ($410.5)", "tf": "1H", "sg": "CALL"},
            {"d": "Vol 1.6x avg", "tf": "15M", "sg": "CONFIRM"},
        ]
        weights = {"FzaRel": 4.0, "BBinf_1H": 3.0, "VolHigh": 2.0}
        total, items = apply_confirm_weights(confirms, weights)
        assert total == 9.0
        assert len(items) == 3

    def test_unknown_category_skipped(self) -> None:
        confirms = [
            {"d": "FzaRel +1.5% vs SPY", "tf": "D", "sg": "CONFIRM"},
            {"d": "Unknown blob", "tf": "D", "sg": "CONFIRM"},
        ]
        weights = {"FzaRel": 4.0}
        total, items = apply_confirm_weights(confirms, weights)
        assert total == 4.0
        assert len(items) == 1

    def test_missing_weight_defaults_zero(self) -> None:
        # Categoría válida pero fixture no la declara → peso 0
        confirms = [{"d": "FzaRel +1.5% vs SPY", "tf": "D", "sg": "CONFIRM"}]
        weights = {"BBinf_1H": 3.0}  # sin FzaRel
        total, items = apply_confirm_weights(confirms, weights)
        assert total == 0.0
        assert items[0]["weight"] == 0.0


class TestApplyConfirmWeightsDedup:
    def test_duplicate_category_first_wins(self) -> None:
        # Dos BB inf 1H con precios distintos — solo el primero suma
        confirms = [
            {"d": "BB inf 1H ($410.5)", "tf": "1H", "sg": "CALL"},
            {"d": "BB inf 1H ($409.0)", "tf": "1H", "sg": "CALL"},
        ]
        weights = {"BBinf_1H": 3.0}
        total, items = apply_confirm_weights(confirms, weights)
        assert total == 3.0
        assert len(items) == 1
        assert items[0]["desc"] == "BB inf 1H ($410.5)"

    def test_input_order_determines_winner(self) -> None:
        # Mismo par con orden invertido — gana el primero del input
        confirms = [
            {"d": "BB inf 1H ($409.0)", "tf": "1H", "sg": "CALL"},
            {"d": "BB inf 1H ($410.5)", "tf": "1H", "sg": "CALL"},
        ]
        weights = {"BBinf_1H": 3.0}
        _, items = apply_confirm_weights(confirms, weights)
        assert items[0]["desc"] == "BB inf 1H ($409.0)"

    def test_all_10_categories_each_sums_once(self) -> None:
        # Un confirm de cada categoría — total = suma de todos los pesos
        confirms = [
            {"d": "FzaRel +1.5% vs SPY", "tf": "D", "sg": "CONFIRM"},
            {"d": "BB sup D ($450.0)", "tf": "D", "sg": "PUT"},
            {"d": "BB inf D ($400.0)", "tf": "D", "sg": "CALL"},
            {"d": "BB sup 1H ($445.5)", "tf": "1H", "sg": "PUT"},
            {"d": "BB inf 1H ($410.5)", "tf": "1H", "sg": "CALL"},
            {"d": "Vol creciente 4 velas", "tf": "15M", "sg": "CONFIRM"},
            {"d": "Vol 1.6x avg", "tf": "15M", "sg": "CONFIRM"},
            {"d": "Gap alcista +1.25%", "tf": "D", "sg": "CALL"},
            {"d": "Squeeze → Expansión (ruptura)", "tf": "1H", "sg": "CONFIRM"},
            {"d": "Div SPY (QQQ:-1.0% vs SPY:+0.5%) → VERIFICAR CATALIZADOR",
             "tf": "D", "sg": "PUT"},
        ]
        # Pesos canonical QQQ
        weights = {
            "FzaRel": 4.0, "BBinf_1H": 3.0, "BBsup_1H": 1.0,
            "BBinf_D": 1.0, "BBsup_D": 1.0, "VolHigh": 2.0,
            "VolSeq": 0.0, "Gap": 1.0, "SqExp": 0.0, "DivSPY": 1.0,
        }
        total, items = apply_confirm_weights(confirms, weights)
        # 4 + 1 + 1 + 1 + 3 + 0 + 2 + 1 + 0 + 1 = 14
        assert total == 14.0
        assert len(items) == 10

    def test_sum_rounded_to_two_decimals(self) -> None:
        confirms = [{"d": "FzaRel +1.5% vs SPY", "tf": "D", "sg": "CONFIRM"}]
        weights = {"FzaRel": 4.333}
        total, _ = apply_confirm_weights(confirms, weights)
        assert total == 4.33
