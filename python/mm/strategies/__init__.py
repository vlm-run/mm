"""User and agent-defined message serialization strategies.

Drop .py files with @strategy-decorated functions into this directory.
They will be auto-discovered at import time.

Example::

    # python/mm/strategies/my_custom.py
    from pathlib import Path
    from mm.serde import strategy

    @strategy(name="my_custom", media_types=("image",))
    def my_custom(path: Path, **kw):
        import base64, io
        from PIL import Image
        img = Image.open(path)
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        b64 = base64.b64encode(buf.getvalue()).decode()
        yield {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}
"""
