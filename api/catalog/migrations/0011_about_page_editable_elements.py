from django.db import migrations


def seed_editable_about_elements(apps, schema_editor):
    AboutPageBlock = apps.get_model("catalog", "AboutPageBlock")
    rows = [
        ("about-breadcrumb-home", "footer", "首页", "", "", 1),
        ("about-breadcrumb-current", "footer", "关于", "", "", 2),
        ("about-stat-documents", "stat", "种文献", "", "book-open", 11),
        ("about-stat-scholars", "stat", "位学者", "", "users", 12),
        ("about-stat-knowledge", "stat", "个理论与研究专题", "", "network", 13),
        ("about-stat-updated", "stat", "最后更新于", "", "refresh", 14),
        (
            "about-process-description",
            "process",
            "",
            "上传的文件会经历文本提取或 OCR、元数据识别、文本清理与结构化处理。系统提出关系建议，由管理员一次审核后发布到检索与阅读页面。",
            "",
            61,
        ),
        ("about-version-current", "footer", "当前版本", "", "", 110),
        ("about-version-updated", "footer", "最近更新", "", "", 111),
    ]
    for key, block_type, title, body, icon, sort_order in rows:
        AboutPageBlock.objects.get_or_create(
            key=key,
            defaults={
                "block_type": block_type,
                "title": title,
                "body": body,
                "icon": icon,
                "sort_order": sort_order,
                "visible": True,
            },
        )

    icon_defaults = {
        "about-feature-source": "search",
        "about-feature-reading": "book-open",
        "about-feature-knowledge": "network",
        "about-notice": "highlighter",
    }
    for key, icon in icon_defaults.items():
        AboutPageBlock.objects.filter(key=key, icon="").update(icon=icon)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_direct_discipline_relations")]

    operations = [migrations.RunPython(seed_editable_about_elements, migrations.RunPython.noop)]
