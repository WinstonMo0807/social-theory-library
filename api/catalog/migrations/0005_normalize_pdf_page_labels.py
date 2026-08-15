from django.db import migrations


def normalize_pdf_page_labels(apps, schema_editor):
    Page = apps.get_model("catalog", "Page")
    for page in Page.objects.filter(printed_label__startswith="<FEFF").iterator():
        value = (page.printed_label or "").strip()
        if not (value.startswith("<FEFF") and value.endswith(">")):
            continue
        payload = value[5:-1]
        if not payload or len(payload) % 4:
            continue
        try:
            decoded = "".join(
                chr(int(payload[index : index + 4], 16))
                for index in range(0, len(payload), 4)
            ).replace("\ufeff", "")
        except ValueError:
            continue
        if decoded:
            page.printed_label = decoded
            page.save(update_fields=["printed_label"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_add_curated_page_data"),
    ]

    operations = [
        migrations.RunPython(normalize_pdf_page_labels, migrations.RunPython.noop),
    ]
