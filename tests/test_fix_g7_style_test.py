"""The hard style test's own tools (evals/style): what score.py --ask saves, and when it stops, how an AI's answer is
scored, and where briefs.py writes its plan. No model runs: Ollama is a stand-in here, and every file is written in
pytest's own folder, never over the answers or the plan saved with the test."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import flip.ai
from flip.ai import Reply

STYLE = Path(__file__).resolve().parent.parent / "evals" / "style"
spec = importlib.util.spec_from_file_location("evals_style_score", STYLE / "score.py")  # a script, not a package
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def ollama(*answers):
    """A stand-in for flip.ai.LocalModel giving these answers in turn, one a buyer. None is one Ollama didn't give: when
    it's off or hasn't got the model, LocalModel hands back a Reply with no answer."""
    left = list(answers)

    class StandIn:
        def __init__(self, name, **settings):
            self.name = name

        def ask(self, system, user, photos, schema, vary=False):
            answer = left.pop(0)
            if answer is None:
                return Reply(self.name, error=f"Ollama refused {self.name} (404): model not found", reachable=False)
            return Reply(self.name, answer=answer)
    return StandIn


def ask(tmp_path, monkeypatch, *answers, model="gemma3:4b"):
    """score.py --ask on the test's first buyers, one an answer, copied into tmp_path."""
    buyers = json.loads((STYLE / "writers.json").read_text(encoding="utf-8"))[:len(answers)]
    writers = tmp_path / "writers.json"
    writers.write_text(json.dumps(buyers, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(flip.ai, "LocalModel", ollama(*answers))
    monkeypatch.setattr(sys, "argv", ["score.py", "--ask", model, "--writers", str(writers)])
    score.main()


def test_ask_stops_without_saving_when_no_buyer_gets_an_answer(tmp_path, monkeypatch, capsys):
    # a model that isn't installed, or Ollama off: 3 of 3 with no answer once printed "ai found 0" and exited 0
    with pytest.raises(SystemExit) as stopped:
        ask(tmp_path, monkeypatch, None, None, None, model="not-installed:4b")
    assert stopped.value.code == 1
    said = capsys.readouterr()
    assert "3 of 3 buyers got no answer from not-installed:4b" in said.err
    assert "ALL" not in said.out  # not scored
    assert [path.name for path in tmp_path.iterdir()] == ["writers.json"]  # nothing saved


def test_ask_never_writes_over_the_answers_saved_with_the_test(tmp_path, monkeypatch, capsys):
    ours = tmp_path / "answers-gemma3-4b.json"
    ours.write_text('{"w01": "ours"}', encoding="utf-8")
    ask(tmp_path, monkeypatch, {"greeting": "Hiya"}, {})
    assert ours.read_text(encoding="utf-8") == '{"w01": "ours"}'
    saved = list(tmp_path.glob("answers-gemma3-4b-*.json"))  # dated, beside the buyers asked
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8")).keys() == {"w01", "w02"}
    assert f"saved {saved[0].name}" in capsys.readouterr().out


def test_ask_says_how_many_buyers_got_no_answer_and_still_scores(tmp_path, monkeypatch, capsys):
    ask(tmp_path, monkeypatch, None, {}, {})
    said = capsys.readouterr()
    assert "1 of 3 buyers got no answer from gemma3:4b" in said.err
    assert "ALL" in said.out
    saved = json.loads(next(tmp_path.glob("answers-gemma3-4b-*.json")).read_text(encoding="utf-8"))
    assert saved["w01"]["proposals"] is None and saved["w02"]["proposals"] == {}


def test_an_after_offer_part_listed_again_counts_once():
    # plain Gemma lists w12's "can collect today" four times: the habit found once, not found and then wrong three times
    messages = [{"my_message": f"hiya would you take {price}? can collect today"} for price in (90, 100, 120, 150, 80)]
    key = {"after": ["can collect today"], "short": []}
    listed = {"after_offer": ["can collect today", "Can collect today!", "can collect today"]}
    assert score.ai_raw(listed, key, messages) == [("after", "found")]
    # ...and a made-up part listed twice is one made up
    assert score.ai_raw({"after_offer": ["cash ready", "cash ready"]}, key, messages) == \
        [("after", "invented"), ("after", "missed")]


def run_briefs(tmp_path):
    """A copy of briefs.py in a folder of its own, run from another folder (as from the repository's root): both."""
    script, elsewhere = tmp_path / "script", tmp_path / "elsewhere"
    script.mkdir()
    elsewhere.mkdir()
    shutil.copy(STYLE / "briefs.py", script)
    subprocess.run([sys.executable, "-I", "-B", str(script / "briefs.py")], cwd=elsewhere, check=True,
                   capture_output=True)
    return script, elsewhere


def test_briefs_writes_its_plan_beside_itself(tmp_path):
    # run from the repository's root, it left a new briefs.json there and evals/style's as it was
    script, elsewhere = run_briefs(tmp_path)
    assert (script / "briefs.json").exists()
    assert not (elsewhere / "briefs.json").exists()


def test_briefs_makes_the_plan_the_buyers_were_written_to(tmp_path):
    # a hard case brings the habit it needs: without that step, 6 sign-offs and 2 likes habits were missing
    script, _ = run_briefs(tmp_path)
    made = (script / "briefs.json").read_text(encoding="utf-8")
    shipped = (STYLE / "briefs.json").read_text(encoding="utf-8")
    assert [b["habits"] for b in json.loads(made)] == [b["habits"] for b in json.loads(shipped)]
    assert made == shipped
