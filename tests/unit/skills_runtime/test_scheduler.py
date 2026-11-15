import warnings

import pytest

from fibu.skills_runtime.loader import SkillManifest
from fibu.skills_runtime.scheduler import topological_waves


def _m(skill_id: str, runs_after: list[str] | None = None) -> SkillManifest:
    return SkillManifest(skill_id=skill_id, runs_after=runs_after or [])


def test_single_skill_one_wave() -> None:
    waves = topological_waves([_m("a")])
    assert len(waves) == 1
    assert waves[0][0].skill_id == "a"


def test_two_independent_skills_one_wave() -> None:
    waves = topological_waves([_m("a"), _m("b")])
    assert len(waves) == 1
    assert len(waves[0]) == 2


def test_chain_two_waves() -> None:
    waves = topological_waves([_m("a"), _m("b", ["a"])])
    assert len(waves) == 2
    assert waves[0][0].skill_id == "a"
    assert waves[1][0].skill_id == "b"


def test_chain_three_waves() -> None:
    waves = topological_waves([_m("a"), _m("b", ["a"]), _m("c", ["b"])])
    assert len(waves) == 3
    ids = [[m.skill_id for m in w] for w in waves]
    assert ids == [["a"], ["b"], ["c"]]


def test_diamond_three_waves() -> None:
    # a → b, a → c, b+c → d
    manifests = [_m("a"), _m("b", ["a"]), _m("c", ["a"]), _m("d", ["b", "c"])]
    waves = topological_waves(manifests)
    assert len(waves) == 3
    assert waves[0][0].skill_id == "a"
    assert {m.skill_id for m in waves[1]} == {"b", "c"}
    assert waves[2][0].skill_id == "d"


def test_unknown_dep_ignored() -> None:
    # "unbekannt" ist kein bekannter Skill → wird ignoriert, kein Blocking
    waves = topological_waves([_m("a", ["unbekannt"])])
    assert len(waves) == 1


def test_empty_list() -> None:
    assert topological_waves([]) == []


def test_circular_dep_warns_and_proceeds() -> None:
    # a → b → a: Zyklus → RuntimeWarning, aber kein crash
    with pytest.warns(RuntimeWarning, match="Zirkuläre"):
        waves = topological_waves([_m("a", ["b"]), _m("b", ["a"])])
    assert len(waves) == 1
    assert len(waves[0]) == 2


def test_mixed_deps_and_independent() -> None:
    # e ist unabhängig, startet in Welle 1 zusammen mit a
    manifests = [_m("a"), _m("b", ["a"]), _m("e")]
    waves = topological_waves(manifests)
    assert len(waves) == 2
    assert {m.skill_id for m in waves[0]} == {"a", "e"}
    assert waves[1][0].skill_id == "b"
