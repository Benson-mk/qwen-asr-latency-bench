from __future__ import annotations

PUNCTUATION = ",.!?;: ，。！？；：、"


def _normalize(text: str) -> str:
    return "".join(c for c in text.lower() if c not in PUNCTUATION)


def merge(previous: str, incoming: str) -> str:
    """Join consecutive segment transcripts, dropping the repeated overlap.

    Segments are cut with padding on both sides, so consecutive results share
    a few words. Spaced languages are matched word-wise; CJK has no spaces, so
    it falls back to character-wise matching with punctuation ignored, because
    the two segments rarely agree on where a comma belongs.
    """
    if not previous:
        return incoming
    if not incoming:
        return previous

    old_words, new_words = previous.split(), incoming.split()
    for size in range(min(len(old_words), len(new_words)), 0, -1):
        if [_normalize(w) for w in old_words[-size:]] == [
            _normalize(w) for w in new_words[:size]
        ]:
            return " ".join(old_words + new_words[size:])

    old_chars, new_chars = _normalize(previous), _normalize(incoming)
    for size in range(min(len(old_chars), len(new_chars)), 2, -1):
        if old_chars[-size:] != new_chars[:size]:
            continue
        seen = 0
        for position, char in enumerate(incoming):
            if char not in PUNCTUATION:
                seen += 1
            if seen == size:
                # Both segments punctuate the seam, so the remainder often
                # opens with a mark that `previous` already ended with.
                return previous + incoming[position + 1 :].lstrip(PUNCTUATION)

    separator = "" if ord(previous[-1]) > 0x2E7F else " "
    return previous + separator + incoming
