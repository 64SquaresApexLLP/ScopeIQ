"""Deleting a site removes its files from the folders the app is configured to use."""
import shutil
from pathlib import Path

from scopeiq.config import get_settings
from scopeiq.services.site_management import delete_site_cascade


def test_deleting_a_site_removes_its_files_from_the_configured_folders(repo):
    """A path built from where the code sits finds nothing on a server, so the files would stay behind."""
    st, sid = get_settings(), "TXZZ4321"
    output = Path(st.path("paths.output_dir"))
    roots = [output / "sites" / sid, output / "evidence" / sid, Path(st.path("paths.upload_dir")) / sid, Path(st.path("paths.sites_dir")) / sid,
             Path(st.path("sharepoint.local_root")) / str(st.get("sharepoint.library_root", "Ericsson-Scoping/Sites")) / sid]
    try:
        for r in roots:
            (r / "inner").mkdir(parents=True, exist_ok=True)
            (r / "inner" / "file.txt").write_text("x")
        res = delete_site_cascade(repo, sid)
        assert not res["failed_paths"]
        assert not any(r.exists() for r in roots)
        assert len(res["removed_paths"]) == len(roots)
    finally:
        for r in roots:
            shutil.rmtree(r, ignore_errors=True)
