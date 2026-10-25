"""Keep retained 3.0.9.1 columns compatible with the current insert shape."""
from django.db import migrations


def preserve_legacy_insert_defaults(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    # These columns exist in deployed 0067_v3091 databases, but are not fields
    # in STL 4.0. Retain their data; supply the same empty values as the old ORM.
    defaults = {"summary_source": "''", "core_concepts": "'[]'::jsonb", "keywords": "'[]'::jsonb"}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "AND is_nullable = 'NO' AND column_default IS NULL",
            ["catalog_knowledgenode"],
        )
        retained = {row[0] for row in cursor.fetchall()}
        for name, default in defaults.items():
            if name in retained:
                schema_editor.execute(
                    f"ALTER TABLE {schema_editor.quote_name('catalog_knowledgenode')} "
                    f"ALTER COLUMN {schema_editor.quote_name(name)} SET DEFAULT {default}"
                )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0088_timeline_merge_record")]
    # Defaults are harmless to the old ORM and intentionally retained on an
    # application rollback. No legacy column, value or migration record is removed.
    operations = [migrations.RunPython(preserve_legacy_insert_defaults, migrations.RunPython.noop)]
