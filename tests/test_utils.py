"""
テスト — 共通ユーティリティ（retry_with_backoff, safe_json_load, atomic_json_save）
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.utils import retry_with_backoff, safe_json_load, atomic_json_save


# ============================================================
# retry_with_backoff テスト
# ============================================================
class TestRetryWithBackoff:

    @patch("src.utils.time.sleep")
    def test_success_first_try(self, mock_sleep):
        """1回目で成功すればリトライしない"""
        result = retry_with_backoff(lambda: "ok", max_retries=3)
        assert result == "ok"
        mock_sleep.assert_not_called()

    @patch("src.utils.time.sleep")
    def test_success_after_retry(self, mock_sleep):
        """リトライ後に成功"""
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("timeout")
            return "recovered"

        result = retry_with_backoff(flaky, max_retries=3, base_delay=1.0)
        assert result == "recovered"
        assert call_count["n"] == 3
        assert mock_sleep.call_count == 2

    @patch("src.utils.time.sleep")
    def test_all_retries_fail(self, mock_sleep):
        """全リトライ失敗で例外が飛ぶ"""
        def always_fail():
            raise ValueError("permanent error")

        with pytest.raises(ValueError, match="permanent error"):
            retry_with_backoff(always_fail, max_retries=2, base_delay=0.1)
        # 初回 + 2リトライ = sleep 2回
        assert mock_sleep.call_count == 2

    @patch("src.utils.time.sleep")
    def test_exponential_delay(self, mock_sleep):
        """指数バックオフの待機時間が正しい"""
        def always_fail():
            raise RuntimeError("err")

        with pytest.raises(RuntimeError):
            retry_with_backoff(always_fail, max_retries=3, base_delay=2.0)

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [2.0, 4.0, 8.0]

    @patch("src.utils.time.sleep")
    def test_zero_retries(self, mock_sleep):
        """max_retries=0 でリトライなし"""
        def fail_once():
            raise RuntimeError("err")

        with pytest.raises(RuntimeError):
            retry_with_backoff(fail_once, max_retries=0)
        mock_sleep.assert_not_called()


# ============================================================
# atomic_json_save テスト
# ============================================================
class TestAtomicJsonSave:

    def test_basic_save(self, tmp_path):
        """基本的な保存"""
        path = tmp_path / "test.json"
        data = [{"id": 1, "name": "テスト"}]
        atomic_json_save(path, data)

        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_creates_parent_dir(self, tmp_path):
        """親ディレクトリがなければ作成"""
        path = tmp_path / "sub" / "dir" / "test.json"
        atomic_json_save(path, {"key": "value"})
        assert path.exists()

    def test_creates_backup(self, tmp_path):
        """既存ファイルのバックアップが作られる"""
        path = tmp_path / "test.json"
        atomic_json_save(path, [1, 2, 3])
        atomic_json_save(path, [4, 5, 6])

        backup = path.with_suffix(".json.bak")
        assert backup.exists()
        with open(backup, "r") as f:
            assert json.load(f) == [1, 2, 3]

    def test_tmp_file_cleaned_up(self, tmp_path):
        """一時ファイルが残らない"""
        path = tmp_path / "test.json"
        atomic_json_save(path, [1])
        tmp_file = path.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_japanese_content(self, tmp_path):
        """日本語が正しく保存される"""
        path = tmp_path / "test.json"
        data = {"message": "日本語テスト🎉"}
        atomic_json_save(path, data)
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f) == data


# ============================================================
# safe_json_load テスト
# ============================================================
class TestSafeJsonLoad:

    def test_load_valid_file(self, tmp_path):
        """正常なJSONを読み込み"""
        path = tmp_path / "valid.json"
        data = [{"id": 1}, {"id": 2}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        assert safe_json_load(path) == data

    def test_load_nonexistent_file(self, tmp_path):
        """存在しないファイルは空リスト"""
        path = tmp_path / "missing.json"
        assert safe_json_load(path) == []

    def test_recover_from_corrupted(self, tmp_path):
        """破損ファイルはバックアップから復元"""
        path = tmp_path / "broken.json"
        backup = path.with_suffix(".json.bak")

        # 破損したメインファイル
        with open(path, "w") as f:
            f.write("{invalid json...")

        # 正常なバックアップ
        backup_data = [{"id": "recovered"}]
        with open(backup, "w", encoding="utf-8") as f:
            json.dump(backup_data, f)

        result = safe_json_load(path)
        assert result == backup_data

    def test_corrupted_no_backup(self, tmp_path):
        """破損でバックアップもなし → 空リスト"""
        path = tmp_path / "broken.json"
        with open(path, "w") as f:
            f.write("not json")

        result = safe_json_load(path)
        assert result == []

    def test_corrupted_backup_also_broken(self, tmp_path):
        """メインもバックアップも破損 → 空リスト"""
        path = tmp_path / "broken.json"
        backup = path.with_suffix(".json.bak")

        with open(path, "w") as f:
            f.write("{bad")
        with open(backup, "w") as f:
            f.write("{also bad")

        result = safe_json_load(path)
        assert result == []
