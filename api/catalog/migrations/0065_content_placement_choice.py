from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0064_document_outline_revision")]

    operations = [
        migrations.AlterField(
            model_name="editorialrevision", name="target_type",
            field=models.CharField(max_length=32, db_index=True, choices=[
                ("work", "作品"), ("edition", "版本"), ("knowledge_node", "知识节点"),
                ("scholar_profile", "学者"), ("discipline", "学科"), ("subdiscipline", "子学科"),
                ("topic", "主题"), ("publisher", "出版社"), ("reading_path", "阅读路径"),
                ("knowledge_relation", "理论关系"), ("timeline_event", "时间线事件"),
                ("recommendation_issue", "书库推荐期"), ("site_content", "网站与关于书库"),
                ("evidence_curation", "原文策展"), ("scholar_relation", "学者关系"),
                ("content_placement", "页面内容编排"),
            ]),
        ),
    ]
