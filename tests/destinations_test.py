"""Offline test for the destinations config loader. No network, no Telegram."""

from nomadbot.destinations import load_destinations


def run():
    # unset -> empty, not a crash
    assert load_destinations({}) == {}
    print("PASS  no TARGET_CHATS_JSON set -> empty dict, not an error")

    # malformed JSON -> empty, not a crash
    assert load_destinations({"TARGET_CHATS_JSON": "{not json"}) == {}
    print("PASS  malformed JSON -> empty dict, logged, not raised")

    # covers both shapes: forum topics (same chat_id, different thread_id)
    # and separate group chats (different chat_id, no thread_id)
    raw = """
    [
        {"key": "nomad_lounge", "chat_id": -100111, "thread_id": 42, "label": "Nomad Lounge"},
        {"key": "event_drops", "chat_id": -100111, "thread_id": 7},
        {"key": "announcements", "chat_id": -100222}
    ]
    """
    dest = load_destinations({"TARGET_CHATS_JSON": raw})
    assert set(dest) == {"nomad_lounge", "event_drops", "announcements"}, dest

    lounge = dest["nomad_lounge"]
    assert lounge.chat_id == -100111 and lounge.thread_id == 42 and lounge.label == "Nomad Lounge"

    announcements = dest["announcements"]
    assert announcements.chat_id == -100222 and announcements.thread_id is None
    assert announcements.label == "announcements", "label should default to the key"
    print("PASS  loads both forum-topic and separate-chat shapes from one config")

    # one bad entry must not take down the good ones
    mixed = """
    [
        {"key": "good", "chat_id": -1},
        {"key": "bad_missing_chat_id"}
    ]
    """
    dest = load_destinations({"TARGET_CHATS_JSON": mixed})
    assert set(dest) == {"good"}, dest
    print("PASS  one malformed entry is skipped without dropping the rest")


run()
print("\nALL DESTINATIONS CHECKS PASSED")
