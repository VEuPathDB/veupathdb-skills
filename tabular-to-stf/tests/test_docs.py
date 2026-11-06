"""The docs agree with the code: commands, options, links, and the pinned version."""

import re

import _constants
import stf
from _container import STUDY_WRANGLER_VERSION
from conftest import SKILL

STF_SETS = {
    name: getattr(_constants, name)
    for name in ("DATA_TYPES", "DATA_SHAPES", "DISPLAY_TYPES", "HIDDEN")
}


def read(p):
    return (SKILL / p).read_text(encoding="utf-8")


def docs():
    """SKILL.md and every Markdown file under resources/, relative to the skill, as posix paths."""
    found = [p.relative_to(SKILL).as_posix() for p in (SKILL / "resources").rglob("*.md")]
    return ["SKILL.md", *sorted(found)]


def subcommand_options():
    parser = stf.build_parser()
    sub = next(a for a in parser._actions if a.choices and hasattr(a, "_name_parser_map"))
    return {
        name: {o for action in p._actions for o in action.option_strings if o.startswith("--")}
        for name, p in sub.choices.items()
    }


def test_every_constant_value_is_documented_in_the_bundled_metadata_fields():
    text = read("resources/stf/metadata-fields.md")
    missing = [f"{s}: {v}" for s, values in STF_SETS.items() for v in values if f"`{v}`" not in text]
    assert missing == []


def test_source_md_names_the_pinned_study_wrangler_version_and_no_other():
    text = read("resources/stf/SOURCE.md")
    assert f"v{STUDY_WRANGLER_VERSION}" in text
    assert set(re.findall(r"v\d+\.\d+\.\d+", text)) == {f"v{STUDY_WRANGLER_VERSION}"}


def test_version_number_appears_only_in_source_md():
    hits = [p for p in docs() if STUDY_WRANGLER_VERSION in read(p)]
    assert hits == ["resources/stf/SOURCE.md"]


def test_version_number_is_written_once_in_the_scripts():
    hits = sorted(p.name for p in (SKILL / "scripts").iterdir()
                  if p.is_file() and STUDY_WRANGLER_VERSION in p.read_text(encoding="utf-8"))
    assert hits == ["_container.py"]


def test_every_relative_link_in_skill_md_and_resources_resolves_inside_the_skill():
    broken = []
    for doc in docs():
        for target in re.findall(r"\]\(([^)\s]+)\)", read(doc)):
            if re.match(r"^[a-z]+:", target, re.I) or target.startswith("#"):
                continue
            path = ((SKILL / doc).parent / target.split("#")[0]).resolve()
            if not path.is_relative_to(SKILL) or not path.exists():
                broken.append(f"{doc}: {target}")
    assert broken == []


def test_skill_md_frontmatter_names_the_skill_tabular_to_stf():
    m = re.match(r"^---\n(.*?)\n---\n", read("SKILL.md"), re.S)
    assert m, "SKILL.md has no frontmatter"
    assert re.search(r"^name: tabular-to-stf$", m.group(1), re.M)
    assert re.search(r"^description: \S", m.group(1), re.M)


def test_every_stf_py_subcommand_the_docs_mention_exists_with_every_option_used_beside_it():
    options = subcommand_options()
    problems, seen = [], set()
    for doc in [d for d in docs() if not d.startswith("resources/stf/")]:
        for line in read(doc).split("\n"):
            for sub in re.findall(r"stf\.py (?:([a-z][a-z-]*))", line):
                seen.add(sub)
                if sub not in options:
                    problems.append(f"{doc}: stf.py has no subcommand {sub}")
                    continue
                for flag in re.findall(r"--[a-z][a-z-]*", line):
                    if flag not in options[sub]:
                        problems.append(f"{doc}: stf.py {sub} has no {flag}")
    assert problems == []
    assert seen == set(options), "the docs should mention every subcommand"


def test_no_doc_mentions_node_js_files_or_the_old_lib_directory():
    problems = [
        f"{doc}: {word}"
        for doc in docs()
        if not doc.startswith("resources/stf/")
        for word in (r"\bnode ", r"\.js\b", r"scripts/lib/")
        if re.search(word, read(doc))
    ]
    assert problems == []
