from pii.redact_names import redact_names


def test_redacts_name_after_honorific():
    text = "Mr. Ramesh Kumar was operating the crane when the incident occurred."
    result = redact_names(text)
    assert "Ramesh" not in result
    assert "Kumar" not in result
    assert result.startswith("Mr. [REDACTED]")


def test_redacts_mid_sentence_capitalized_name():
    text = "The supervisor, Anita Sharma, confirmed the isolation was not done."
    result = redact_names(text)
    assert "Anita" not in result
    assert "Sharma" not in result


def test_leaves_known_site_names_alone():
    text = "The incident occurred at Duliajan field during the night shift."
    assert "Duliajan" in redact_names(text)


def test_leaves_ordinary_report_text_unchanged_when_no_name_present():
    text = "the worker fell from the scaffold while erecting a pipe rack"
    assert redact_names(text) == text


def test_never_raises_on_garbage_or_empty_input():
    for bad in ["", "\x00", "a" * 5000, "!!! ??? 000"]:
        try:
            redact_names(bad)
        except Exception as error:  # noqa: BLE001 - the point of the test is "never raises"
            raise AssertionError(f"redact_names raised on {bad!r}: {error}") from error