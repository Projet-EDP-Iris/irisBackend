from app.nlp.preprocessor import truncate_email, zero_shot_classify


def test_truncate_combines_subject_and_body():
    result = truncate_email("Hello", "A" * 1000)
    assert result.startswith("Hello")
    assert len(result) <= len("Hello\n") + 800


def test_truncate_short_body_unchanged():
    result = truncate_email("Subject", "Short body")
    assert result == "Subject\nShort body"


def test_zero_shot_noreply_sender_returns_info():
    assert zero_shot_classify("noreply@company.com", "Your invoice", "see attached") == "info"


def test_zero_shot_no_reply_hyphenated_returns_info():
    assert zero_shot_classify("no-reply@shop.com", "Order update", "details inside") == "info"


def test_zero_shot_noreply_promo_subject_returns_bonsplans():
    assert (
        zero_shot_classify("noreply@shop.com", "50% promo soldes flash", "unsubscribe below")
        == "bonsplans"
    )


def test_zero_shot_list_unsubscribe_header_returns_info():
    assert (
        zero_shot_classify(
            "news@company.com",
            "Weekly digest",
            "here is the update",
            headers={"List-Unsubscribe": "<mailto:unsub@company.com>"},
        )
        == "info"
    )


def test_zero_shot_unsubscribe_in_body_returns_info():
    assert (
        zero_shot_classify(
            "someone@example.com",
            "Update",
            "manage preferences here to opt-out",
        )
        == "info"
    )


def test_zero_shot_normal_sender_returns_none():
    assert zero_shot_classify("boss@company.com", "Meeting tomorrow", "let's meet at 3pm") is None


def test_zero_shot_empty_sender_no_headers_normal_body_returns_none():
    assert zero_shot_classify("", "Hello", "Just checking in") is None
