from harness.scripted import run_condition


def test_c4_scripted():
    rows = run_condition(True)
    assert all(row["passed"] for row in rows), rows


def test_c3_scripted():
    rows = run_condition(False)
    assert all(row["passed"] for row in rows), rows
