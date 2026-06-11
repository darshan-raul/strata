"""Tests for the tools: schemas, return shapes, edge cases."""
from __future__ import annotations

import os

import pytest

from linux_tui.tools import ALL_TOOLS, MUTATING_TOOLS, READ_ONLY_TOOLS
from linux_tui.tools.disk_usage import disk_usage
from linux_tui.tools.grep import grep
from linux_tui.tools.list_dir import list_dir
from linux_tui.tools.read_file import read_file
from linux_tui.tools.run_command import is_dangerous, run_command
from linux_tui.tools.system_info import system_info


# ---- list_dir --------------------------------------------------------------


def test_list_dir_existing(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "b").mkdir()
    out = list_dir.invoke({"path": str(tmp_path)})
    assert "a.txt" in out
    assert "b" in out


def test_list_dir_not_found() -> None:
    out = list_dir.invoke({"path": "/nonexistent/this/should/not/exist"})
    assert "NOT_FOUND" in out


def test_list_dir_file_not_dir(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("x")
    out = list_dir.invoke({"path": str(f)})
    assert "NOT_A_DIRECTORY" in out


# ---- read_file -------------------------------------------------------------


def test_read_file_basic(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("a\nb\nc\n")
    out = read_file.invoke({"path": str(f), "max_lines": 200, "from_end": False})
    assert "a" in out and "b" in out and "c" in out


def test_read_file_max_lines(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("\n".join(f"line{i}" for i in range(100)))
    out = read_file.invoke({"path": str(f), "max_lines": 3, "from_end": False})
    assert "line0" in out
    assert "line1" in out
    assert "line2" in out
    assert "line99" not in out


def test_read_file_from_end(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("\n".join(f"line{i}" for i in range(100)))
    out = read_file.invoke({"path": str(f), "max_lines": 3, "from_end": True})
    assert "line99" in out
    assert "line0" not in out


def test_read_file_not_found() -> None:
    out = read_file.invoke({"path": "/nope.txt"})
    assert "NOT_FOUND" in out


# ---- grep ------------------------------------------------------------------


def test_grep_finds_match(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("foo\nbar\nbaz")
    out = grep.invoke({"pattern": "bar", "path": str(f)})
    assert "bar" in out
    assert "NO_MATCHES" not in out


def test_grep_no_match(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("foo\nbar")
    out = grep.invoke({"pattern": "qux", "path": str(f)})
    assert "NO_MATCHES" in out


def test_grep_bad_pattern(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("anything")
    out = grep.invoke({"pattern": "[invalid", "path": str(f)})
    assert "BAD_PATTERN" in out


def test_grep_recursive(tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("target here")
    (tmp_path / "sub" / "b.txt").write_text("target also here")
    out = grep.invoke({"pattern": "target", "path": str(tmp_path), "recursive": True})
    assert "a.txt" in out
    assert "b.txt" in out


# ---- system_info -----------------------------------------------------------


def test_system_info_shape() -> None:
    out = system_info.invoke({})
    assert "hostname:" in out
    assert "os:" in out
    assert "kernel:" in out
    assert "arch:" in out
    assert "python:" in out
    assert "cwd:" in out


# ---- disk_usage ------------------------------------------------------------


def test_disk_usage_existing() -> None:
    out = disk_usage.invoke({"path": "/"})
    assert "total:" in out
    assert "used:" in out
    assert "free:" in out


def test_disk_usage_not_found() -> None:
    out = disk_usage.invoke({"path": "/nope/nope/nope"})
    assert "NOT_FOUND" in out


# ---- run_command -----------------------------------------------------------


def test_run_command_simple() -> None:
    out = run_command.invoke({"cmd": "echo hello"})
    assert "exit_code: 0" in out
    assert "hello" in out


def test_run_command_exit_code() -> None:
    out = run_command.invoke({"cmd": "sh -c 'exit 42'"})
    assert "exit_code: 42" in out


def test_run_command_stderr() -> None:
    out = run_command.invoke({"cmd": "sh -c 'echo bad >&2; exit 1'"})
    assert "exit_code: 1" in out
    assert "stderr" in out
    assert "bad" in out


def test_run_command_invalid() -> None:
    out = run_command.invoke({"cmd": "this-command-does-not-exist-xyz"})
    # Either exit code != 0 or SPAWN_ERROR; both are acceptable.
    assert "exit_code:" in out or "SPAWN_ERROR" in out


def test_is_dangerous() -> None:
    assert is_dangerous("rm -rf /tmp/foo")[0] is True
    assert is_dangerous("mv a b")[0] is True
    assert is_dangerous("chmod 777 /etc/passwd")[0] is True
    assert is_dangerous("kill -9 1234")[0] is True
    assert is_dangerous("shutdown -r now")[0] is True
    assert is_dangerous("sudo apt install foo")[0] is True
    assert is_dangerous("ls -la")[0] is False
    assert is_dangerous("cat /etc/hostname")[0] is False
    assert is_dangerous("echo hello")[0] is False


# ---- registry --------------------------------------------------------------


def test_tool_registry_complete() -> None:
    """The ALL_TOOLS / READ_ONLY_TOOLS / MUTATING_TOOLS sets should be sane."""
    assert len(ALL_TOOLS) == 6
    # READ_ONLY_TOOLS is a subset.
    for t in READ_ONLY_TOOLS:
        assert t in ALL_TOOLS
    # MUTATING_TOOLS contains only the names of mutating tools.
    assert "run_command" in MUTATING_TOOLS
    for t in ALL_TOOLS:
        if t.name in MUTATING_TOOLS:
            assert t.name not in {x.name for x in READ_ONLY_TOOLS}


def test_all_tools_have_names() -> None:
    for t in ALL_TOOLS:
        assert t.name
        assert t.description
