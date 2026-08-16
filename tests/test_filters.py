from src.config import get_config
from src.filters import check_location, experience_penalty, parse_experience


def test_us_only_rejected():
    config = get_config()
    result = check_location("This role requires candidates to be US citizens only.", config.location_rules)
    assert result.eligible is False
    assert result.confidence == "high"


def test_remote_worldwide_eligible():
    config = get_config()
    result = check_location("This is a Remote Worldwide position, work from anywhere.", config.location_rules)
    assert result.eligible is True
    assert result.confidence == "high"


def test_ambiguous_location_not_rejected():
    config = get_config()
    result = check_location("Job located in a nice office downtown.", config.location_rules)
    assert result.eligible is True
    assert result.confidence == "low"


def test_years_required_vs_preferred_penalty():
    config = get_config()
    rules = config.experience_rules

    exp_required = parse_experience("We need 5+ years required of backend engineering experience.")
    exp_preferred = parse_experience("5 years preferred but not mandatory for the right candidate.")

    assert exp_required.is_required is True
    assert exp_preferred.is_required is False

    penalty_required, _ = experience_penalty(
        2.5, exp_required, rules["penalty_by_gap"], rules["preferred_penalty_multiplier"]
    )
    penalty_preferred, _ = experience_penalty(
        2.5, exp_preferred, rules["penalty_by_gap"], rules["preferred_penalty_multiplier"]
    )
    assert penalty_required > penalty_preferred


def test_stray_remote_phrase_does_not_override_structured_non_remote_flag():
    """Regression: a hybrid/on-site job whose JD happens to mention 'fully
    remote' (e.g. describing the company in general) must not be marked
    location_confidence=high when the source's own remote flag says False."""
    config = get_config()
    text = "Great hybrid role in London. Our company culture supports fully remote work for some teams."
    result_non_remote = check_location(text, config.location_rules, remote_flag=False)
    assert result_non_remote.confidence == "low"

    result_remote = check_location(text, config.location_rules, remote_flag=True)
    assert result_remote.confidence == "high"


def test_no_years_mentioned_means_no_penalty():
    config = get_config()
    rules = config.experience_rules
    exp = parse_experience("We are looking for a passionate engineer.")
    assert exp.years_required is None
    penalty, label = experience_penalty(2.5, exp, rules["penalty_by_gap"], rules["preferred_penalty_multiplier"])
    assert penalty == 0
    assert label == "not specified"
