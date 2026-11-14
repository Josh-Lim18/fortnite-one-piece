import csv
import json
from pathlib import Path

from arena.cli import main

REGISTRY = str(Path(__file__).resolve().parents[1] / "bots.toml")


def only_run_dir(out):
    (run,) = list(Path(out).iterdir())
    return run


def test_list_prints_every_bot(capsys):
    assert main(["list", "--bots", REGISTRY]) == 0
    assert {"checkfold", "call", "allin", "random", "example-json"} <= set(capsys.readouterr().out.split())


def test_table_writes_hands_and_leaderboard(tmp_path, capsys):
    code = main(["table", "call", "allin", "example-json", "--deals", "5", "--bots", REGISTRY, "--out", str(tmp_path)])
    assert code == 0
    run = only_run_dir(tmp_path)
    hands = [json.loads(line) for line in (run / "hands.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(hands) == 15  # 5 deals x 3 rotations
    rows = list(csv.DictReader(open(run / "leaderboard.csv", encoding="utf-8")))
    assert sorted(r["bot"] for r in rows) == ["allin", "call", "example-json"]
    assert sum(int(r["chips"]) for r in rows) == 0
    assert "mbb/hand" in capsys.readouterr().out


def test_roundrobin_writes_pairwise_matrix(tmp_path):
    code = main(["roundrobin", "call", "checkfold", "allin", "--deals", "10", "--bots", REGISTRY, "--out", str(tmp_path)])
    assert code == 0
    run = only_run_dir(tmp_path)
    matrix = list(csv.reader(open(run / "pairwise.csv", encoding="utf-8")))
    assert matrix[0] == ["bot vs opponent", "call", "checkfold", "allin"]
    assert len(matrix) == 4


def test_unknown_bot_is_an_error(tmp_path, capsys):
    assert main(["table", "call", "nobody", "--bots", REGISTRY, "--out", str(tmp_path)]) == 2
    assert "unknown bots: nobody" in capsys.readouterr().err


def test_view_builds_a_self_contained_replay(tmp_path, capsys):
    main(["table", "call", "allin", "--deals", "3", "--bots", REGISTRY, "--out", str(tmp_path)])
    run = only_run_dir(tmp_path)
    assert json.loads((run / "run.json").read_text(encoding="utf-8"))["config"]["starting_stack"] == 1000
    assert main(["view", "--out", str(tmp_path), "--no-open"]) == 0
    page = (run / "viewer.html").read_text(encoding="utf-8")
    assert "__ARENA_DATA__" not in page
    assert '"players": ["call", "allin"]' in page or '"players": ["allin", "call"]' in page
    assert "Replay written" in capsys.readouterr().out


def test_view_without_runs_is_an_error(tmp_path):
    assert main(["view", "--out", str(tmp_path / "none"), "--no-open"]) == 2


def test_roundrobin_until_decided_reports_a_winner(tmp_path, capsys):
    code = main(["roundrobin", "call", "checkfold", "--until-decided", "--deals", "50", "--max-deals", "1000",
                 "--bots", REGISTRY, "--out", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "after 50 deals per pair" in out and "Winner: call" in out
    info = json.loads((only_run_dir(tmp_path) / "run.json").read_text(encoding="utf-8"))
    assert info["decided"] and info["winner"] == "call"


def test_table_until_decided_reports_a_winner(tmp_path, capsys):
    code = main(["table", "call", "checkfold", "allin", "--until-decided", "--deals", "40", "--max-deals", "2000",
                 "--bots", REGISTRY, "--out", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "after 40 deals:" in out and ("Winner:" in out or "No clear winner" in out)
    info = json.loads((only_run_dir(tmp_path) / "run.json").read_text(encoding="utf-8"))
    assert "decided" in info and info["deals"] >= 40
