from app.storage.local import LocalStorage


def test_local_storage_save_get_delete(tmp_path):
    storage = LocalStorage(str(tmp_path))

    content = b"hello world"
    storage_path = storage.save(content, "invoice.pdf")

    assert storage.exists(storage_path)
    assert storage.get(storage_path) == content
    assert storage_path.endswith(".pdf")

    storage.delete(storage_path)

    assert not storage.exists(storage_path)


def test_local_storage_avoids_filename_collisions(tmp_path):
    storage = LocalStorage(str(tmp_path))

    path_a = storage.save(b"file a", "invoice.pdf")
    path_b = storage.save(b"file b", "invoice.pdf")

    assert path_a != path_b
    assert storage.get(path_a) == b"file a"
    assert storage.get(path_b) == b"file b"
