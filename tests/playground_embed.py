"""Playground for testing embeddings. Run with: uv run python tests/playground_embed.py"""

from pathlib import Path

from mm.store import MmDatabase
from mm.store.embed import (
    audio_parts,
    document_part,
    embed_file_chunks,
    embed_parts,
    embed_texts,
    image_part,
    text_part,
    video_parts,
)

SAMPLE = Path("sample_files")


def _run(label: str, fn):
    try:
        fn()
    except Exception as e:
        print(f"[{label}] error: {e}")


def test_text():
    vecs = embed_texts(["What is machine learning?", "A cat on a mat."])
    print(f"[text]  {len(vecs)} vectors, dim={len(vecs[0])}, first3={vecs[0][:3]}")


def test_image():
    vecs = embed_parts([image_part(SAMPLE / "image.png")])
    print(f"[image] {len(vecs)} vectors, dim={len(vecs[0])}, first3={vecs[0][:3]}")


def test_audio():
    audio = SAMPLE / "audio.mp3"
    if not audio.exists():
        print("[audio] skipped — sample_files/audio.mp3 not found")
        return

    parts = audio_parts(audio)
    vecs = embed_parts(parts)
    print(f"[audio] {len(parts)} segments, {len(vecs)} vectors, dim={len(vecs[0])}")


def test_document():
    pdf = SAMPLE / "document.pdf"
    if not pdf.exists():
        print("[doc]   skipped — sample_files/document.pdf not found")
        return
    vecs = embed_parts([document_part(pdf)])
    print(f"[doc]   {len(vecs)} vectors, dim={len(vecs[0])}, first3={vecs[0][:3]}")


def test_video():
    vid = SAMPLE / "video.mp4"
    if not vid.exists():
        print("[video] skipped — sample_files/video.mp4 not found")
        return
    vecs = embed_parts(video_parts(vid))
    print(f"[video] {len(vecs)} vectors, dim={len(vecs[0])}, first3={vecs[0][:3]}")


def test_mixed_batch():
    parts = [text_part("hello"), image_part(SAMPLE / "image.png")]
    vecs = embed_parts(parts)
    print(f"[mixed] {len(vecs)} vectors, dim={len(vecs[0])}")


def test_embed_file_chunks():
    db = MmDatabase()
    lt = db._l2_table()
    if lt.count_rows() == 0:
        print("[chunks] skipped — no L2 results in DB. Run: mm cat sample_files/document.txt -l 2")
        return
    t = lt.to_arrow()
    uri = t.column("uri")[0].as_py()
    content_hash = t.column("content_hash")[0].as_py()
    profile = t.column("profile")[0].as_py()
    model = t.column("model")[0].as_py()
    n = embed_file_chunks(uri, content_hash, profile, model)
    print(f"[chunks] embedded {n} chunks for {Path(uri).name}")


def inspect_db():
    db = MmDatabase()
    print("\n--- DB state ---")
    print(f"  l2_results: {db._l2_table().count_rows()} rows")
    print(f"  chunks:     {db._chunks_table().count_rows()} rows")

    ct = db._chunks_table()
    t = ct.to_arrow()
    has_vec = "vector" in t.column_names
    embedded = 0
    if has_vec:
        for i in range(t.num_rows):
            if t.column("vector")[i].as_py() is not None:
                embedded += 1

    print(f"  with vectors: {embedded}/{t.num_rows}")


if __name__ == "__main__":
    _run("text", test_text)
    _run("image", test_image)
    _run("doc", test_document)
    _run("audio", test_audio)
    _run("video", test_video)
    _run("mixed", test_mixed_batch)
    _run("chunks", test_embed_file_chunks)
    inspect_db()
