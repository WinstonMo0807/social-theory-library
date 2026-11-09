"""Trusted SSH/console entry to the same encrypted model configuration service."""
import getpass
import sys
import warnings
from types import SimpleNamespace
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.exceptions import APIException

from accounts.ownership import is_library_owner
from reading import runtime_configuration as configuration
from reading.runtime_serializers import AIRuntimeProfileDocumentSerializer, AIRuntimeProfileSerializer


class Command(BaseCommand):
    help = "Configure Intelligence through a trusted interactive console. Does not call a model."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Existing library owner username")
        parser.add_argument("--base-url", required=True, help="Public HTTPS OpenAI-compatible API base URL")
        parser.add_argument("--model", required=True)
        parser.add_argument("--json-mode", choices=["json_schema", "json_object"], default="json_schema")
        parser.add_argument("--enable", action="store_true", help="Explicitly enable subsequent administrator-started runs")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if not actor or not is_library_owner(actor):
            raise CommandError("须指定现有馆长账户。")
        if not sys.stdin.isatty():
            raise CommandError("请通过可信交互终端运行；不接受命令行参数或管道传入密钥。")
        document = configuration.validated_document()
        key = document["active"].get("curation_reasoning", "")
        profile = next((p for p in document["profiles"] if p["key"] == key), None)
        if not profile or profile["capability"] != "curation_reasoning":
            raise CommandError("当前没有策展配置档，请先修复现有模型管理配置。")
        expected = configuration.configuration_version()
        profile.update(provider="openai_compatible", model=options["model"], enabled=options["enable"],
            credential_alias="intelligence-console", reasoning={**profile.get("reasoning", {}), "json_mode": options["json_mode"]})
        self.stdout.write("只保存到当前连接的数据库；不会测试接口、启动分析或发布内容。")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                secret = getpass.getpass("API Key（隐藏输入）: ")
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt) as exc:
            raise CommandError("未取得安全的交互输入，配置未更改。") from exc
        try:
            fields = set(AIRuntimeProfileSerializer().fields)
            serializer = AIRuntimeProfileDocumentSerializer(data={"active": document["active"],
                "profiles": [{k: v for k, v in p.items() if k in fields} for p in document["profiles"]], "expected_version": expected,
                "endpoint": {"profile_key": key, "base_url": options["base_url"]},
                "credential": {"action": "set", "profile_key": key, "alias": profile["credential_alias"], "secret": secret}})
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                actor = configuration.locked_actor(SimpleNamespace(user=actor, headers={"X-Editor-Owner": str(actor.pk)}), expected)
                configuration.save(actor, serializer.validated_data, request_id=f"intelligence-console:{uuid4()}")
        except (APIException, ValueError) as exc:
            # Do not print serializer input, endpoint or transport exception text.
            raise CommandError("配置未保存；请核对地址、模型、馆长权限和配置版本。原配置保留。") from exc
        finally:
            secret = ""
        self.stdout.write(self.style.SUCCESS("配置和加密凭据已保存。启用状态：" + ("已启用" if options["enable"] else "关闭")))
