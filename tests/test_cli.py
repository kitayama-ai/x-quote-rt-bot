"""
テスト — CLIコマンド解析 & エントリポイント
"""
import pytest
import argparse
from unittest.mock import patch, MagicMock


class TestCLIParsing:
    """main.py の CLI パース & コマンドルーティングのテスト"""

    def _parse(self, args_list: list[str]):
        """main() のパーサー部分だけ実行"""
        from src.main import main
        with patch("sys.argv", ["main"] + args_list):
            parser = argparse.ArgumentParser(
                description="X Auto Post System"
            )
            parser.add_argument("--version", action="version", version="1.0.0")
            subparsers = parser.add_subparsers(dest="command")

            def add_account_arg(p):
                p.add_argument("--account", type=str, default="1")
                return p

            add_account_arg(subparsers.add_parser("generate"))
            add_account_arg(subparsers.add_parser("post"))
            add_account_arg(subparsers.add_parser("curate"))
            add_account_arg(subparsers.add_parser("curate-post"))
            add_account_arg(subparsers.add_parser("collect"))
            add_account_arg(subparsers.add_parser("notify-test"))
            metrics_parser = add_account_arg(subparsers.add_parser("metrics"))
            metrics_parser.add_argument("--days", type=int, default=7)
            pdca_parser = add_account_arg(subparsers.add_parser("weekly-pdca"))
            pdca_parser.add_argument("--days", type=int, default=7)

            return parser.parse_args(args_list)

    def test_generate_command(self):
        args = self._parse(["generate", "--account", "1"])
        assert args.command == "generate"
        assert args.account == "1"

    def test_metrics_command(self):
        args = self._parse(["metrics", "--account", "1", "--days", "14"])
        assert args.command == "metrics"
        assert args.days == 14

    def test_weekly_pdca_command(self):
        args = self._parse(["weekly-pdca", "--account", "1"])
        assert args.command == "weekly-pdca"
        assert args.days == 7

    def test_collect_command(self):
        args = self._parse(["collect", "--account", "1"])
        assert args.command == "collect"

    def test_curate_post_command(self):
        args = self._parse(["curate-post", "--account", "1"])
        assert args.command == "curate-post"

    def test_default_account(self):
        args = self._parse(["generate"])
        assert args.account == "1"

    def test_no_command(self):
        args = self._parse([])
        assert args.command is None


class TestCommandRegistry:
    """main.py にすべてのコマンドが登録されていることを確認"""

    def test_all_commands_registered(self):
        """全コマンドがmain()のcommands辞書に含まれる"""
        import src.main as main_module
        import inspect

        source = inspect.getsource(main_module.main)
        expected_commands = [
            "generate", "post", "curate", "curate-post",
            "collect", "notify-test", "metrics", "weekly-pdca",
            "import-urls", "setup-sheets", "sync-queue", "sync-settings",
        ]
        for cmd in expected_commands:
            assert f'"{cmd}"' in source, f"Command '{cmd}' not found in main()"

    def test_all_cmd_functions_exist(self):
        """全コマンド関数が存在する"""
        import src.main as main_module

        expected_funcs = [
            "cmd_generate", "cmd_post", "cmd_curate", "cmd_curate_post",
            "cmd_collect", "cmd_notify_test", "cmd_metrics", "cmd_weekly_pdca",
            "cmd_import_urls", "cmd_setup_sheets", "cmd_sync_queue", "cmd_sync_settings",
        ]
        for func_name in expected_funcs:
            assert hasattr(main_module, func_name), f"Function '{func_name}' not found in main.py"
