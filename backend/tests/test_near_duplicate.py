from duplicates.near_duplicate import find_near_duplicate


def test_finds_near_duplicate_of_the_same_incident():
    original = "Worker fell from the scaffold while erecting a pipe rack at the Duliajan field."
    resubmission = (
        "Worker fell from the scaffold while erecting a pipe rack at the Duliajan field site."
    )
    assert find_near_duplicate(resubmission, [original]) == original


def test_distinguishes_two_unrelated_reports():
    a = "Worker fell from the scaffold while erecting a pipe rack at the Duliajan field."
    b = "A generator caught fire during routine maintenance at the Naharkatiya plant."
    assert find_near_duplicate(b, [a]) is None


def test_empty_or_blank_input_is_never_a_duplicate():
    assert find_near_duplicate("", ["some existing report"]) is None
    assert find_near_duplicate("   ", ["some existing report"]) is None
    assert find_near_duplicate("some existing report", []) is None


def test_checks_against_every_existing_report_not_just_the_first():
    unrelated = "A generator caught fire during routine maintenance at the Naharkatiya plant."
    original = "Worker fell from the scaffold while erecting a pipe rack at the Duliajan field."
    resubmission = (
        "Worker fell from the scaffold while erecting a pipe rack at the Duliajan field site."
    )
    assert find_near_duplicate(resubmission, [unrelated, original]) == original