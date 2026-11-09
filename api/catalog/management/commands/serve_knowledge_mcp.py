from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Run official MCP stdio tools as an explicitly selected existing account (trusted local launcher only)."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Existing account username; never a password/token.")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if not user:
            raise CommandError("指定的MCP账户不存在或已停用。")
        from catalog.services.knowledge_mcp import build_server
        build_server(user.pk).run(transport="stdio")
