"""The Set 18 data source must retain real scaling and snapshot provenance."""
from copy import deepcopy

from scripts.fetch_tft_catalog import curve_star_values, curve_units_by_asset, normalize_curve_ability


def test_curves_use_explicit_step_values_including_missing_middle_stars():
    assert curve_star_values([[1, 3], [4, 3]]) == [0, 3, 3, 3, 3]
    assert curve_star_values([[1, 0.25], [3, 0.1], [4, 0.1]]) == [0, 0.25, 0.25, 0.1, 0.1]
    assert curve_star_values([[1, float("nan")]]) is None
    assert curve_star_values([[True, 100]]) is None
    assert curve_star_values([]) is None


def test_curve_tooltips_retain_calculations_and_do_not_invent_live_stacks():
    damage = {"terms": [{"op": "add", "type": "scaled", "scaling": "AbilityPower",
                          "coefficient": [175, 265, 395, 670]}],
              "values": [175, 265, 395, 670], "resolved": True}
    source = {"curveValues": {"HPThreshold": [[1, 0.3], [4, 0.3]], "APOnKill": [[1, 3], [4, 3]]},
              "ability": {"name": "Primordial Burst", "desc":
                  '<TFTAttribute attributeID="TFTCalculationAttributes.MagicDamageCalc1" icon="icon.AP"/>'
                  '<TFTCurveTable row="HPThreshold" format="percent"/>'
                  '<TFTCurveTable row="APOnKill"/>%'
                  '<TFTAttribute attributeID="TFTSpellAttributes.Stack"/>',
                  "attributeValues": {"TFTCalculationAttributes.MagicDamageCalc1": damage["values"]},
                  "attributeCalcs": {"TFTCalculationAttributes.MagicDamageCalc1": damage}}}
    before = deepcopy(source)
    result = normalize_curve_ability(source)
    assert result["description"] == (
        "@TFTCalculationAttributes.MagicDamageCalc1@ %i:scaleAP%@Curve.HPThreshold*100@%"
        "@Curve.APOnKill@%@TFTSpellAttributes.Stack@")
    assert result["calculations"]["TFTCalculationAttributes.MagicDamageCalc1"] == {
        "__type": "GameCalculationCurveTable", **damage}
    assert "TFTCalculationAttributes.MagicDamageCalc1" not in result["variables"]
    assert "TFTSpellAttributes.Stack" not in result["variables"]
    assert source == before


def test_mixed_scaling_terms_and_percent_minus_one_are_preserved():
    result = normalize_curve_ability({"curveValues": {"AttackSpeed": [[1, 1.6], [3, 2.0]]}, "ability": {
        "desc": '<TFTCurveTable row="AttackSpeed" format="percentMinusOne"/>'
                '<TFTAttribute attributeID="Damage" icon="Icon.AD, icon.AP"/>',
        "attributeCalcs": {"Damage": {"terms": [
            {"op": "add", "type": "scaled", "scaling": "AttackDamage", "coefficient": [160, 240, 410]},
            {"op": "add", "type": "scaled", "scaling": "AbilityPower", "coefficient": [10, 15, 25]}],
            "values": [170, 255, 435], "resolved": True}}}})
    assert result["description"].endswith("@Damage@ %i:scaleAD%%i:scaleAP%")
    assert [round(v) for v in result["variables"]["Curve.AttackSpeed.PercentMinusOne"]] == [0, 60, 60, 100, 100]
    assert len(result["calculations"]["Damage"]["terms"]) == 2


def test_extra_abilities_are_mapped_to_their_own_asset_and_local_values():
    first, second = {"desc": "base"}, {"apiName": "TFT18_Lux_Fae", "desc": "variant"}
    unit = {"apiName": "TFT18_Lux", "assetNames": ["DA_Lux18_Base", "DA_18_Lux_Fae"],
            "ability": first, "extraAbilities": {"Fae": second}}
    lookup = curve_units_by_asset({"units": [unit]})
    assert lookup["DA_Lux18_Base"] == (unit, first)
    assert lookup["DA_18_Lux_Fae"] == (unit, second)


def test_percent_minus_one_uses_only_explicit_resolved_attribute_values():
    unit = {"ability": {"desc": '<TFTAttribute attributeID="Buff" format="percentMinusOne"/>',
                        "attributeCalcs": {"Buff": {"values": [1.9, 2, 2.3], "resolved": True}}}}
    result = normalize_curve_ability(unit)
    assert [round(v) for v in result["variables"]["Buff.PercentMinusOne"]] == [0, 90, 100, 130]
    unit["ability"]["attributeCalcs"]["Buff"]["resolved"] = False
    assert "Buff.PercentMinusOne" not in normalize_curve_ability(unit)["variables"]
