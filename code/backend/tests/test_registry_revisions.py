"""Which file of a site is picked: duplicates by content, then the highest revision. Pure logic, no data or database."""
from scopeiq.domain import Document
from scopeiq.extract.registry import resolve_current


def doc(name, rank, digest, doc_type="CD", fmt="PDF"):
    return Document(doc_id=name, site_id="TXAA0001", doc_type=doc_type, file_name=name, rel_path=f"sites/TXAA0001/cds/{name}", file_format=fmt,
                    revision=f"REV {rank}", revision_rank=rank, file_hash=digest, size_bytes=1)


def status(docs):
    return {d.file_name: d.status for d in resolve_current(docs)}


def test_the_highest_revision_is_picked_and_older_ones_are_superseded():
    assert status([doc("a_REV1.pdf", 1, "h1"), doc("a_REV2.pdf", 2, "h2"), doc("a_REV3.pdf", 3, "h3")]) == {
        "a_REV1.pdf": "SUPERSEDED", "a_REV2.pdf": "SUPERSEDED", "a_REV3.pdf": "CURRENT"}


def test_a_drawing_reissued_unchanged_under_a_newer_revision_still_counts_as_the_newer_one():
    """REV 4 has the same content as REV 2. Before, the file name that sorted first (REV 2) kept the content and REV 4 was thrown out as a duplicate,
    so REV 3 stayed picked. The newer revision is the one that counts."""
    got = status([doc("a_CD_REV2.dxf", 2, "same", fmt="DXF"), doc("a_CD_REV3.pdf", 3, "h3"), doc("a_CD_REV4.dxf", 4, "same", fmt="DXF")])
    assert got == {"a_CD_REV4.dxf": "CURRENT", "a_CD_REV2.dxf": "DUPLICATE", "a_CD_REV3.pdf": "SUPERSEDED"}


def test_identical_files_of_the_same_revision_keep_one_by_name():
    got = status([doc("a_CD_REV3_copy.pdf", 3, "same"), doc("a_CD_REV3.pdf", 3, "same")])
    assert got == {"a_CD_REV3.pdf": "CURRENT", "a_CD_REV3_copy.pdf": "DUPLICATE"}


def test_files_without_revisions_are_kept_once_per_content():
    got = status([doc("b.jpg", 0, "p", doc_type="DRONE_IMAGE", fmt="JPG"), doc("a.jpg", 0, "p", doc_type="DRONE_IMAGE", fmt="JPG"), doc("c.jpg", 0, "q", doc_type="DRONE_IMAGE", fmt="JPG")])
    assert got == {"a.jpg": "CURRENT", "b.jpg": "DUPLICATE", "c.jpg": "CURRENT"}
