"""site/build.py's name check: one closure, one id space — a collision is refused at build time, never found on screen."""
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build", ROOT / "site/build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_duplicate_id_in_html_is_a_collision():
    bad = build.check_names('<div id="planner"></div><div id="planner"></div>', "", {})
    assert bad == ['id="planner" in inner.html, inner.html']


def test_literal_id_in_a_script_clashing_with_html_is_a_collision():
    bad = build.check_names('<div id="lotPlanner"></div>', "", {"x.js": 'h.innerHTML = `<div id="lotPlanner">`'})
    assert bad == ['id="lotPlanner" in inner.html, x.js']


def test_templated_ids_and_script_only_ids_are_not_counted():
    assert build.check_names('<div id="a"></div>', 'x = `<i id="${esc(p.id)}">`', {"y.js": '`<b id="wlIn">`'}) == []


def test_same_function_name_in_app_and_an_include_is_a_collision():
    bad = build.check_names("", "function renderPlanner() {}\n", {"planner.js": "async function renderPlanner() {}\n"})
    assert bad == ["function renderPlanner() in app.js, planner.js"]


def test_nested_functions_do_not_count():
    assert build.check_names("", "function a() {\n  function helper() {}\n}\n", {"b.js": "function b() {\n  function helper() {}\n}\n"}) == []


def test_the_real_page_has_no_collisions():
    src = ROOT / "site/src"
    app = (src / "app.js").read_text(encoding="utf8")
    includes = {m: (src / m).read_text(encoding="utf8") for m in re.findall(r"/\* @include ([\w.-]+) \*/", app)}
    assert build.check_names((src / "inner.html").read_text(encoding="utf8"), app, includes) == []
