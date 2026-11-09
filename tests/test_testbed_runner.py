from testbed.run_switch_calibration import build_run_plan
from testbed.scenario import load_scenario


def test_runner_plan_has_stable_run_identifiers(tmp_path):
    scenario = load_scenario("testbed/scenarios/smoke.json")
    plan = build_run_plan(scenario, tmp_path / "run", repetitions=3)

    assert [item.run_id for item in plan] == ["e00-r00", "e00-r01", "e00-r02"]
    assert [item.repetition for item in plan] == [0, 1, 2]
    assert plan[0].old_path == "bb"
    assert plan[0].new_path == "five_g"
