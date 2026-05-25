from core.indexer import _chunk_text, _stable_id


def test_chunk_text_single_chunk():
    text = "a" * 100
    chunks = _chunk_text(text, "src/app.py")
    assert len(chunks) == 1
    assert chunks[0]["file_path"] == "src/app.py"
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["start_char"] == 0


def test_chunk_text_multiple_chunks():
    text = "x" * 4000
    chunks = _chunk_text(text, "src/big.py")
    assert len(chunks) > 1
    assert all(c["file_path"] == "src/big.py" for c in chunks)
    assert all(len(c["text"]) <= 1500 for c in chunks)


def test_chunk_text_overlap():
    text = "a" * 1500 + "b" * 1500
    chunks = _chunk_text(text, "overlap.py")
    assert len(chunks) >= 2
    # second chunk starts before end of first (overlap)
    assert chunks[1]["start_char"] < 1500


def test_stable_id_deterministic():
    id1 = _stable_id("repo-abc", "auth/service.py", 0)
    id2 = _stable_id("repo-abc", "auth/service.py", 0)
    assert id1 == id2


def test_stable_id_unique_per_chunk():
    id1 = _stable_id("repo-abc", "auth/service.py", 0)
    id2 = _stable_id("repo-abc", "auth/service.py", 1)
    assert id1 != id2
