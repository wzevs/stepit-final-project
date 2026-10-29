from apps.integrations.models import ApiKey


def test_issue_and_resolve(client_shop):
    key, raw = ApiKey.issue(client_shop, name="ERP")
    assert raw.startswith(f"lgx_{key.prefix}_")
    assert ApiKey.resolve(raw).pk == key.pk


def test_inactive_key_does_not_resolve(client_shop):
    key, raw = ApiKey.issue(client_shop, name="ERP")
    key.is_active = False
    key.save(update_fields=["is_active"])
    assert ApiKey.resolve(raw) is None


def test_inactive_client_blocks_key(client_shop):
    _, raw = ApiKey.issue(client_shop, name="ERP")
    client_shop.is_active = False
    client_shop.save(update_fields=["is_active"])
    assert ApiKey.resolve(raw) is None
