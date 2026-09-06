from pathlib import Path

import pytest

from murn.providers.workspace import WorkspaceProvider


def test_workspace_reads_text_inside_allowed_root(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    source = project / "main.py"
    source.write_text("print('murn')\n", encoding="utf-8")

    workspace = WorkspaceProvider([str(project)])
    result = workspace.read("main.py")

    assert "print('murn')" in result["content"]
    assert result["total_lines"] == 1


def test_workspace_blocks_absolute_path_outside_root(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")

    workspace = WorkspaceProvider([str(project)])
    with pytest.raises(ValueError):
        workspace.read(str(outside))


def test_workspace_list_does_not_follow_symlink_outside_root(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("SECRET = True\n", encoding="utf-8")
    (project / "escape").symlink_to(outside, target_is_directory=True)
    (project / "safe.py").write_text("SAFE = True\n", encoding="utf-8")

    workspace = WorkspaceProvider([str(project)])
    listing = workspace.list(depth=3)
    paths = {item["path"] for item in listing["items"]}

    assert "safe.py" in paths
    assert "escape" not in paths
    assert all("secret.py" not in path for path in paths)


def test_workspace_search_skips_symlinked_external_tree(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("MAGIC_NEEDLE = 1\n", encoding="utf-8")
    (project / "escape").symlink_to(outside, target_is_directory=True)
    (project / "real.py").write_text("MAGIC_NEEDLE = 2\n", encoding="utf-8")

    workspace = WorkspaceProvider([str(project)])
    result = workspace.search("MAGIC_NEEDLE")

    assert len(result["results"]) == 1
    assert result["results"][0]["path"].endswith("real.py")
