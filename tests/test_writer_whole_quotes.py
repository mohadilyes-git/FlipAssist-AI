"""A reason worded from the reader's whole sentence (26 Sep): with the safety checks only, the app no longer cuts the
reader's quotes, so the writer gets the seller's whole sentence, asides and praise included."""
import pytest

from flip.writer import flaw_phrase


@pytest.mark.parametrize("quote, phrase", [
    ("Small hairline crack on the bottom left corner can’t tell whilst screen is on", "the small hairline crack on the bottom left corner"),
    ("scratch on the back only visible while charging", "the scratch on the back"),
    ("light scratches only visible in certain light", "the light scratches"),
    ("small dent on the corner unless you look closely", "the small dent on the corner"),
    ("Small ink leak on the left side of the screen (visible in photos)", "the small ink leak on the left side of the screen"),
    ("Slight black Mark on screen (Hence low price) but doesn’t affect use.", "the slight black mark on the screen"),
    ("Light marks on the frame, screen is perfect.", "the light marks on the frame"),
    ("Small scuffs on the edges, screen mint", "the small scuffs on the edges"),
    ("Back glass cracked, camera works fine", "that the back glass is cracked"),
    ("Cracked screen, Face ID works", "the cracked screen"),
    ("Crack on the screen, touch works fine", "the crack on the screen"),
    ("Won't charge, cable works", "that it won't charge"),
])
def test_an_aside_or_praise_after_the_flaw_is_left_out(quote, phrase):
    assert flaw_phrase(quote) == phrase


@pytest.mark.parametrize("quote, phrase", [
    ("Cracked screen, camera not working", "the cracked screen, camera not working"),
    ("Scratches on the back, speakers don't work", "that the scratches on the back, speakers don't work"),
])
def test_a_second_fault_after_the_comma_stays(quote, phrase):
    assert flaw_phrase(quote) == phrase


@pytest.mark.parametrize("quote, phrase", [  # the second red team (26 Sep): a fault's own condition stays
    ("Doesn't charge unless you wiggle the cable.", "that it doesn't charge unless you wiggle the cable"),
    ("Mic doesn't work while on speaker", "that the mic doesn't work while on speaker"),
    ("Face ID doesn't work unless in good light", "that the Face ID doesn't work unless in good light"),
    ("Small crack on the back only when you look closely", "the small crack on the back"),
    ("Faint mark on the screen while it's off", "the faint mark on the screen"),
])
def test_when_a_mark_shows_goes_but_a_faults_condition_stays(quote, phrase):
    assert flaw_phrase(quote) == phrase
