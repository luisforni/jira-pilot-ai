from core.git_manager import GitManager


def test_branch_name_for_ticket():
    gm = GitManager("git@github.com:company/api.git", "PROJ-145")
    branch = gm.branch_name_for_ticket("Fix login timeout in auth service")
    assert branch.startswith("feat/proj-145-")
    assert " " not in branch
    assert len(branch) <= 70


def test_branch_name_special_chars():
    gm = GitManager("git@github.com:company/api.git", "PROJ-99")
    branch = gm.branch_name_for_ticket("Fix: user@email validation & error!")
    assert " " not in branch
    assert "@" not in branch
    assert "&" not in branch
