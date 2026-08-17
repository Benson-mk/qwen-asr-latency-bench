"""Plain-assert checks for segment merging. Run: python tests/test_transcript.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qwenbench.transcript import merge  # noqa: E402


def test_empty_sides():
    assert merge("", "hello") == "hello"
    assert merge("hello", "") == "hello"


def test_word_overlap_dropped():
    assert merge("the quick brown fox", "brown fox jumps") == "the quick brown fox jumps"


def test_word_overlap_ignores_punctuation():
    assert merge("we went home,", "Home, and slept") == "we went home, and slept"


def test_disjoint_words_are_spaced():
    assert merge("hello there", "general kenobi") == "hello there general kenobi"


def test_cjk_overlap_dropped():
    assert merge("我今日好肚痛", "好肚痛屙咗六七次") == "我今日好肚痛屙咗六七次"


def test_cjk_overlap_survives_differing_punctuation():
    assert merge("我今日好肚痛，", "好肚痛。屙咗六七次") == "我今日好肚痛，屙咗六七次"


def test_disjoint_cjk_joined_without_space():
    assert merge("你好", "唔該") == "你好唔該"


def test_no_false_overlap_on_short_tail():
    assert merge("abc def", "xyz") == "abc def xyz"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
