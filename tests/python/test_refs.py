"""Tests for the ``mm.refs`` module and the Context session/ref pipeline.

Covers:

* Per-kind prefix mapping (mirrors ``vlmrun-python-sdk``'s ``refs.py``)
* Deterministic ref id generation from a stable seed
* Format validation (``<prefix>_<6 alnum>``)
* ``GlobalRef`` parsing + round-trip
* Uniqueness within a session (collision-free across many files)
* Cross-session refs differ for the same uri
* Schema migration is idempotent on existing databases
* End-to-end Context.save -> Context.resolve round-trip
* CLI ``mm ref`` resolver
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from mm.cli import app
from mm.context import Context
from mm.refs import (
    GLOBAL_REF_RE,
    REF_ID_RE,
    GlobalRef,
    is_valid_global_ref,
    is_valid_ref_id,
    kind_for_prefix,
    make_ref_id,
    new_session_id,
    prefix_for,
)
from mm.store.db import MmDatabase
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def session_id() -> str:
    return new_session_id()


@pytest.fixture
def isolated_db(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect MmDatabase to a tmp path so tests don't touch ~/.local/share/mm.

    Uses ``tmp_path_factory`` so the DB lives outside ``small_tree``'s
    ``tmp_path`` -- otherwise the DB files (mm.db, mm.db-wal, ...) would be
    scanned and tagged, polluting session results.
    """
    db_dir = tmp_path_factory.mktemp("mmdb")
    db_path = db_dir / "mm.db"
    monkeypatch.setattr(MmDatabase, "DB_PATH", db_path)
    monkeypatch.setattr(MmDatabase, "DB_DIR", db_dir)
    return db_path


# ── Prefix table ──────────────────────────────────────────────────────


class TestPrefixes:
    def test_known_kinds_have_prefixes(self):
        for kind in ("image", "video", "audio", "document", "code", "data", "config", "text"):
            assert prefix_for(kind), f"missing prefix for {kind!r}"

    def test_unknown_kind_falls_back_to_obj(self):
        assert prefix_for("nonsense") == "obj"
        assert prefix_for("") == "obj"

    @pytest.mark.parametrize(
        "kind,prefix",
        [
            ("image", "img"),
            ("video", "vid"),
            ("audio", "aud"),
            ("document", "doc"),
        ],
    )
    def test_aligned_with_vlmrun_sdk(self, kind: str, prefix: str):
        """Image/video/audio/document prefixes match vlmrun-python-sdk/refs.py."""
        assert prefix_for(kind) == prefix

    def test_kind_for_prefix_round_trip(self):
        for kind in ("image", "video", "audio", "document", "code"):
            assert kind_for_prefix(prefix_for(kind)) == kind


# ── make_ref_id ───────────────────────────────────────────────────────


class TestMakeRefId:
    @pytest.mark.parametrize("kind", ["image", "video", "audio", "document", "code", "text"])
    def test_format(self, kind: str):
        ref = make_ref_id(kind, seed="seed-1")
        assert is_valid_ref_id(ref), ref
        m = REF_ID_RE.match(ref)
        assert m is not None
        assert m.group("prefix") == prefix_for(kind)
        assert len(m.group("suffix")) == 6

    def test_deterministic_with_seed(self):
        a = make_ref_id("image", seed="abc")
        b = make_ref_id("image", seed="abc")
        assert a == b

    def test_different_seeds_yield_different_ids(self):
        ids = {make_ref_id("image", seed=f"s-{i}") for i in range(50)}
        assert len(ids) == 50

    def test_random_when_seed_omitted(self):
        ids = {make_ref_id("image") for _ in range(50)}
        assert len(ids) >= 49

    def test_kind_changes_prefix_only(self):
        a = make_ref_id("image", seed="x")
        b = make_ref_id("video", seed="x")
        assert a.split("_")[0] == "img"
        assert b.split("_")[0] == "vid"

    def test_suffix_is_alphanumeric_lowercase(self):
        ref = make_ref_id("image", seed="anything")
        suffix = ref.split("_", 1)[1]
        assert suffix.islower() or suffix.isdigit() or all(c.isalnum() for c in suffix)
        assert all(c in "0123456789abcdefghijklmnopqrstuvwxyz" for c in suffix)


# ── GlobalRef ─────────────────────────────────────────────────────────


class TestGlobalRef:
    def test_parse_valid(self):
        ref = GlobalRef.parse("sess-123/img_a1b2c3")
        assert ref.session_id == "sess-123"
        assert ref.ref_id == "img_a1b2c3"
        assert ref.kind == "image"

    def test_parse_uuid_session(self):
        sid = new_session_id()
        ref = GlobalRef.parse(f"{sid}/vid_xyz123")
        assert ref.session_id == sid
        assert ref.kind == "video"

    @pytest.mark.parametrize(
        "bad",
        [
            "img_a1b2c3",
            "sess/img_short",
            "sess/img_TOOLONG",
            "sess/imgnounderscore",
            "/img_a1b2c3",
            "sess/img_a1b2c3/extra",
        ],
    )
    def test_parse_invalid(self, bad: str):
        with pytest.raises(ValueError):
            GlobalRef.parse(bad)

    def test_str_round_trip(self):
        s = "sess-1/doc_abcdef"
        assert str(GlobalRef.parse(s)) == s

    def test_validators(self):
        assert is_valid_ref_id("img_abcdef")
        assert not is_valid_ref_id("img_abc")
        assert is_valid_global_ref("sess/img_abcdef")
        assert not is_valid_global_ref("sess/imgnounderscore")
        assert GLOBAL_REF_RE.match("a/aud_000000")


# ── Context: session_id wiring ────────────────────────────────────────


class TestContextSession:
    def test_no_session_by_default(self, small_tree: Path):
        ctx = Context(small_tree)
        assert ctx.session_id is None
        assert ctx.refs == {}

    def test_explicit_session(self, small_tree: Path):
        sid = "ext-session-42"
        ctx = Context(small_tree, session_id=sid)
        assert ctx.session_id == sid
        assert sid in repr(ctx)

    def test_new_session_classmethod(self, small_tree: Path):
        ctx = Context.new_session(small_tree)
        assert ctx.session_id is not None
        uuid.UUID(ctx.session_id)

    def test_ref_for_requires_session(self, small_tree: Path):
        ctx = Context(small_tree)
        with pytest.raises(ValueError, match="session_id"):
            ctx.ref_for("src/main.py")

    def test_ref_for_is_deterministic(self, small_tree: Path):
        a = Context(small_tree, session_id="sess-1")
        b = Context(small_tree, session_id="sess-1")
        assert a.ref_for("src/main.py") == b.ref_for("src/main.py")

    def test_ref_for_changes_with_session(self, small_tree: Path):
        a = Context(small_tree, session_id="sess-A").ref_for("src/main.py")
        b = Context(small_tree, session_id="sess-B").ref_for("src/main.py")
        assert a != b

    def test_global_ref_format(self, small_tree: Path):
        sid = "sess-1"
        ctx = Context(small_tree, session_id=sid)
        gref = ctx.global_ref("src/main.py")
        parsed = GlobalRef.parse(gref)
        assert parsed.session_id == sid
        assert parsed.ref_id.startswith("code_") or parsed.ref_id.startswith("txt_")

    def test_refs_property_per_kind(self, small_tree: Path):
        ctx = Context(small_tree, session_id="sess-1")
        all_refs = ctx.refs
        assert len(all_refs) == ctx.num_files
        for path, gref in all_refs.items():
            parsed = GlobalRef.parse(gref)
            assert parsed.session_id == "sess-1"
            assert ctx.global_ref(path) == gref

    def test_refs_unique_within_session(self, mixed_1k_tree: Path):
        ctx = Context(mixed_1k_tree, session_id="sess-1")
        refs = list(ctx.refs.values())
        assert len(refs) == len(set(refs)), "ref collision within session"

    def test_filter_preserves_session(self, small_tree: Path):
        ctx = Context(small_tree, session_id="sess-1")
        py = ctx.filter(ext=".py")
        assert py.session_id == "sess-1"
        assert all(f.session_id == "sess-1" for f in py.files)

    def test_file_entry_ref_when_session_set(self, small_tree: Path):
        ctx = Context(small_tree, session_id="sess-1")
        for f in ctx.files:
            assert f.ref_id is not None and is_valid_ref_id(f.ref_id)
            assert f.global_ref == f"sess-1/{f.ref_id}"

    def test_file_entry_no_ref_without_session(self, small_tree: Path):
        ctx = Context(small_tree)
        f = ctx.files[0]
        assert f.session_id is None
        assert f.ref_id is None
        assert f.global_ref is None

    def test_file_entry_ref_matches_context_ref(self, small_tree: Path):
        """`ctx.global_ref(path)`, `ctx.refs[path]`, and `entry.global_ref`
        must all agree -- they are three views of the same identity."""
        ctx = Context(small_tree, session_id="agree-sess")
        all_refs = ctx.refs
        for f in ctx.files:
            assert f.global_ref == ctx.global_ref(f.path)
            assert f.global_ref == all_refs[f.path]


# ── DB persistence + resolver round-trip ──────────────────────────────


class TestResolver:
    def test_save_persists_session_and_ref(self, small_tree: Path, isolated_db: Path):
        ctx = Context(small_tree, session_id="sess-roundtrip")
        ctx.save()

        db = MmDatabase()
        rows = db.list_session_files("sess-roundtrip")
        assert len(rows) == ctx.num_files
        for r in rows:
            assert r["session_id"] == "sess-roundtrip"
            assert is_valid_ref_id(r["ref_id"])

    def test_resolve_global_ref(self, small_tree: Path, isolated_db: Path):
        ctx = Context(small_tree, session_id="sess-r")
        ctx.save()

        gref = ctx.global_ref("src/main.py")
        row = Context.resolve(gref)
        assert row is not None
        assert row["session_id"] == "sess-r"
        assert row["uri"].endswith("src/main.py")

    def test_resolve_unknown_returns_none(self, small_tree: Path, isolated_db: Path):
        ctx = Context(small_tree, session_id="sess-r")
        ctx.save()

        row = Context.resolve("sess-r/img_zzzzzz")
        assert row is None

    def test_resolve_validates_format(self, isolated_db: Path):
        with pytest.raises(ValueError):
            Context.resolve("not-a-ref")

    def test_save_without_session_leaves_session_null(self, small_tree: Path, isolated_db: Path):
        ctx = Context(small_tree)
        ctx.save()
        db = MmDatabase()
        rows = db.get_files()
        assert all(r["session_id"] is None and r["ref_id"] is None for r in rows)

    def test_resave_same_session_is_idempotent(self, small_tree: Path, isolated_db: Path):
        ctx = Context(small_tree, session_id="sess-x")
        ctx.save()
        db = MmDatabase()
        before = {r["uri"]: r["ref_id"] for r in db.list_session_files("sess-x")}

        ctx2 = Context(small_tree, session_id="sess-x")
        ctx2.save()
        after = {r["uri"]: r["ref_id"] for r in db.list_session_files("sess-x")}
        assert before == after

    def test_retag_to_new_session(self, small_tree: Path, isolated_db: Path):
        Context(small_tree, session_id="sess-old").save()
        Context(small_tree, session_id="sess-new").save()

        db = MmDatabase()
        old_rows = db.list_session_files("sess-old")
        new_rows = db.list_session_files("sess-new")
        assert old_rows == []
        assert len(new_rows) > 0

    def test_two_contexts_share_session(self, tmp_path: Path, isolated_db: Path):
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        (root_a / "x.py").write_text("a")
        (root_b / "y.py").write_text("b")

        sid = "shared-session"
        Context(root_a, session_id=sid).save()
        Context(root_b, session_id=sid).save()

        db = MmDatabase()
        rows = db.list_session_files(sid)
        uris = {r["uri"] for r in rows}
        assert any(u.endswith("/x.py") for u in uris)
        assert any(u.endswith("/y.py") for u in uris)


# ── Migration idempotency ─────────────────────────────────────────────


class TestMigration:
    def test_migration_adds_columns_to_legacy_db(self, tmp_path: Path):
        """A pre-existing DB without session_id/ref_id should migrate cleanly.

        Builds a schema that matches mm's pre-refs ``files`` DDL (all L0/L1
        columns, no session_id/ref_id), seeds a row, then opens via
        ``MmDatabase`` and verifies the new columns appear with NULL values.
        """
        legacy_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(legacy_path))
        conn.execute(
            """
            CREATE TABLE files (
                uri TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                stem TEXT NOT NULL DEFAULT '',
                ext TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                modified INTEGER NOT NULL DEFAULT 0,
                created INTEGER NOT NULL DEFAULT 0,
                mime TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'other',
                is_binary INTEGER NOT NULL DEFAULT 0,
                depth INTEGER NOT NULL DEFAULT 0,
                parent TEXT NOT NULL DEFAULT '',
                width INTEGER,
                height INTEGER,
                content_hash TEXT,
                text_preview TEXT,
                line_count INTEGER,
                word_count INTEGER,
                language TEXT,
                dimensions TEXT,
                pages INTEGER,
                duration_s REAL,
                fps REAL,
                magic_mime TEXT,
                exif_camera TEXT,
                exif_date TEXT,
                exif_gps TEXT,
                exif_orientation TEXT,
                video_codec TEXT,
                audio_codec TEXT,
                has_audio INTEGER,
                phash TEXT,
                indexed_at INTEGER NOT NULL DEFAULT 0,
                l1_indexed_at INTEGER
            )
            """
        )
        conn.execute("INSERT INTO files (uri) VALUES (?)", ("/legacy/file.txt",))
        conn.commit()
        conn.close()

        db = MmDatabase(db_path=legacy_path)
        rows = db.get_files()
        assert len(rows) == 1
        assert "session_id" in rows[0]
        assert "ref_id" in rows[0]
        assert rows[0]["session_id"] is None
        assert rows[0]["ref_id"] is None

    def test_migration_is_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "fresh.db"
        db = MmDatabase(db_path=db_path)
        db._connect  # noqa: B018 -- trigger creation
        # Re-trigger by creating another instance pointing to the same file
        db2 = MmDatabase(db_path=db_path)
        db2._connect  # noqa: B018
        cols = {r["name"] for r in db2._connect.execute("PRAGMA table_info(files)").fetchall()}
        assert "session_id" in cols
        assert "ref_id" in cols


# ── CLI: mm ref ───────────────────────────────────────────────────────


class TestRefCli:
    def test_resolve_handle(self, small_tree: Path, isolated_db: Path):
        ctx = Context(small_tree, session_id="cli-sess")
        ctx.save()
        gref = ctx.global_ref("src/main.py")

        r = runner.invoke(app, ["ref", gref, "--format", "json"])
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["session_id"] == "cli-sess"
        assert data[0]["uri"].endswith("src/main.py")

    def test_list_session(self, small_tree: Path, isolated_db: Path):
        Context(small_tree, session_id="cli-sess-2").save()
        r = runner.invoke(app, ["ref", "--session", "cli-sess-2", "--format", "json"])
        assert r.exit_code == 0, r.output
        data = json.loads(r.output)
        assert len(data) > 0
        assert all(row["session_id"] == "cli-sess-2" for row in data)

    def test_unknown_ref_exits_nonzero(self, isolated_db: Path):
        r = runner.invoke(app, ["ref", "missing-sess/img_zzzzzz"])
        assert r.exit_code != 0

    def test_bad_handle_exits_nonzero(self, isolated_db: Path):
        r = runner.invoke(app, ["ref", "not-a-ref"])
        assert r.exit_code != 0

    def test_no_args_exits_nonzero(self, isolated_db: Path):
        r = runner.invoke(app, ["ref"])
        assert r.exit_code != 0
