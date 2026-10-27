"""B9: fl_help — on-demand domain docs (read-only, local).

Verified offline:
  - every one of the 11 domains returns its docs (actions, tier, transport, gaps)
  - an unknown domain is rejected with the valid list
  - the docs carry the critical gotchas (2-arg rename, §6b handshake,
    open=destructive, batch-never-destructive)
"""


from fl_studio_mcp.tools.help_v2 import _DOCS, DOMAINS, fl_help


def test_all_eleven_domains_documented():
    for d in DOMAINS:
        assert d in _DOCS
        r = fl_help(d)
        assert r["success"] is True
        assert r["domain"] == d
        assert "actions" in r
        assert "tier" in r


def test_all_domain_tools_present():
    # the 8 domain tools from B1-B8 plus help/delete/batch
    tools = {v["tool"] for v in _DOCS.values()}
    for t in ("fl_state", "fl_transport", "fl_mixer", "fl_channel",
              "fl_pattern", "fl_notes", "fl_plugin", "fl_file",
              "fl_help", "fl_delete", "fl_batch"):
        assert t in tools, f"{t} not documented"


def test_unknown_domain_rejected_with_list():
    r = fl_help("quantum")
    assert r["success"] is False
    assert "transport" in r["error"]
    assert "state" in r["error"]


def test_case_insensitive():
    assert fl_help("TRANSPORT")["success"] is True
    assert fl_help("  Mixer  ".strip())["success"] is True


def test_pattern_docs_carry_the_two_arg_gotcha():
    """C4: the docs must warn that rename is 2-arg (3-arg crashes FL)."""
    r = fl_help("pattern")
    actions = {a["action"]: a for a in r["actions"]}
    assert "2-arg" in actions["rename"]["params"]
    assert any("3-arg" in g and "crash" in g.lower() for g in r["gaps"])


def test_notes_docs_carry_the_handshake():
    """§6b: the docs must warn about the open_roll_verified handshake."""
    r = fl_help("notes")
    text = r["summary"] + " ".join(a.get("note", "") for a in r["actions"]) + " ".join(r["gaps"])
    assert "open_roll_verified" in text
    assert "6b" in text


def test_file_docs_mark_open_destructive():
    r = fl_help("file")
    assert r["tier"] == "write (open=destructive)"
    actions = {a["action"]: a for a in r["actions"]}
    assert "DESTRUCTIVE" in actions["open"]["params"]


def test_batch_docs_say_never_destructive():
    r = fl_help("batch")
    assert "NEVER" in r["tier"].upper() or "never" in str(r["gaps"]).lower()


def test_delete_docs_list_all_five_targets():
    r = fl_help("delete")
    targets = {a["action"] for a in r["actions"]}
    assert targets == {"channel", "pattern", "pattern_data", "fx", "roll_notes"}


def test_no_arg_returns_full_index():
    """Discovery entry point: no arg (or empty) = index of ALL domains."""
    r = fl_help()
    assert r["success"] is True
    names = {d["domain"] for d in r["domains"]}
    assert names == set(DOMAINS)
    for d in r["domains"]:
        assert d["tool"] in _DOCS[d["domain"]]["tool"]
        assert d["summary"]
    # empty string behaves the same as no arg
    assert fl_help("")["success"] is True
    assert {d["domain"] for d in fl_help("")["domains"]} == set(DOMAINS)


def test_select_script_in_index_and_notes_cross_reference():
    """The LLM self-heals: notes docs point at fl_select_script when note_count stays 0."""
    r = fl_help()
    assert any(d["tool"] == "fl_select_script" for d in r["domains"])
    n = fl_help("notes")
    assert any("fl_select_script" in g for g in n["gaps"])


def test_select_script_docs_say_machine_independent():
    r = fl_help("select_script")
    text = " ".join(g.lower() for g in r["gaps"])
    assert "window frame" in text  # no longer "pixel search / positional fallback"
