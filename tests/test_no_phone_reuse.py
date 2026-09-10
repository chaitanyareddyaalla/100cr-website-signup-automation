from backend.app import main as backend_main


def test_unique_phone_no_reuse_across_calls_and_batches(tmp_path, monkeypatch):
    test_db = tmp_path / "test_phone_reuse.db"
    monkeypatch.setattr(backend_main, "DATABASE_PATH", test_db)
    backend_main.global_used_phones.clear()
    backend_main.initialize_database()

    batch_1 = "batch-111"
    batch_2 = "batch-222"

    generated_phones = set()

    # Generate 50 unique phones for batch 1
    for _ in range(50):
        phone = backend_main.claim_unique_phone(batch_1)
        assert phone[0] in "0123456789"
        assert len(phone) == 10
        assert phone.isdigit()
        assert phone not in generated_phones
        generated_phones.add(phone)

    assert len(generated_phones) == 50

    # Generate 50 unique phones for batch 2
    for _ in range(50):
        phone = backend_main.claim_unique_phone(batch_2)
        assert phone[0] in "0123456789"
        assert len(phone) == 10
        assert phone.isdigit()
        assert phone not in generated_phones  # Guarantees batch 2 does not reuse numbers
        generated_phones.add(phone)

    assert len(generated_phones) == 100

    # Simulate restart: clear in-memory cache and reload from DB
    backend_main.global_used_phones.clear()
    assert len(backend_main.global_used_phones) == 0

    backend_main.load_used_phones()
    assert len(backend_main.global_used_phones) == 100

    # Any new phone claimed after restart must also NEVER be in the previous 100
    phone_new = backend_main.claim_unique_phone("batch-333")
    assert phone_new not in generated_phones


def test_generate_phone_full_digit_space():
    from worker.generators.phone_generator import generate_phone

    seen_prefixes = set()
    for _ in range(500):
        phone = generate_phone()
        assert len(phone) == 10
        assert phone.isdigit()
        assert phone[0] in "0123456789"
        seen_prefixes.add(phone[0])

    # Over 500 generations across 10B space, diverse digits (0-9) appear
    assert len(seen_prefixes) >= 5


