from django.db import migrations

from apps.network.seed import PLACES

SHEET_SQL = """
CREATE VIEW network_tariff_sheet AS
SELECT
    t.id,
    t.company_id,
    t.kind,
    t.price,
    oc.name AS origin_city,
    dc.name AS destination_city,
    od.name AS origin_district,
    dd.name AS destination_district
FROM network_tariff t
LEFT JOIN network_city oc ON oc.id = t.origin_city_id
LEFT JOIN network_city dc ON dc.id = t.destination_city_id
LEFT JOIN network_district od ON od.id = t.origin_district_id
LEFT JOIN network_district dd ON dd.id = t.destination_district_id;
"""

WAREHOUSE_SQL = """
CREATE VIEW network_warehouse_sheet AS
SELECT
    w.id,
    w.company_id,
    w.name,
    w.kind,
    c.name AS city,
    d.name AS district,
    w.is_active
FROM network_warehouse w
JOIN network_city c ON c.id = w.city_id
LEFT JOIN network_district d ON d.id = w.district_id;
"""


def seed_places(apps, schema_editor):
    city_model = apps.get_model("network", "City")
    district_model = apps.get_model("network", "District")
    for city_name, districts in PLACES:
        city, _created = city_model.objects.get_or_create(name=city_name)
        for name in districts:
            district_model.objects.get_or_create(city=city, name=name)


def install_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION network_warehouse_district_city()
        RETURNS trigger AS $$
        DECLARE
            district_city bigint;
        BEGIN
            IF NEW.district_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT city_id INTO district_city FROM network_district WHERE id = NEW.district_id;
            IF district_city IS DISTINCT FROM NEW.city_id THEN
                RAISE EXCEPTION 'district does not belong to this city';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    schema_editor.execute("DROP TRIGGER IF EXISTS warehouse_district_city ON network_warehouse;")
    schema_editor.execute(
        """
        CREATE TRIGGER warehouse_district_city
        BEFORE INSERT OR UPDATE ON network_warehouse
        FOR EACH ROW EXECUTE FUNCTION network_warehouse_district_city();
        """
    )


def remove_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS warehouse_district_city ON network_warehouse;")
    schema_editor.execute("DROP FUNCTION IF EXISTS network_warehouse_district_city();")


class Migration(migrations.Migration):

    dependencies = [
        ("network", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_places, migrations.RunPython.noop),
        migrations.RunSQL(SHEET_SQL, "DROP VIEW IF EXISTS network_tariff_sheet;"),
        migrations.RunSQL(WAREHOUSE_SQL, "DROP VIEW IF EXISTS network_warehouse_sheet;"),
        migrations.RunPython(install_trigger, remove_trigger),
    ]
