"""
Firebase サービスアカウントキー → GitHub Secret 設定スクリプト

使い方:
  1. Firebase Console → プロジェクト設定 → サービスアカウント → 新しい秘密鍵を生成
  2. ダウンロードしたJSONファイルのパスを引数に指定:
     python3 tools/setup_firebase_secret.py /path/to/isai-11f7b-xxxxx.json

  自動で:
    - Base64エンコード
    - GitHub Secret (FIREBASE_CREDENTIALS_BASE64) に設定
    - ローカルの config/ にもコピー
"""
import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 2:
        print("❌ 使い方: python3 tools/setup_firebase_secret.py <サービスアカウントJSONのパス>")
        print()
        print("📋 取得方法:")
        print("   1. https://console.firebase.google.com/project/isai-11f7b/settings/serviceaccounts/adminsdk")
        print("   2. 「新しい秘密鍵を生成」をクリック")
        print("   3. ダウンロードされたJSONファイルのパスを指定")
        sys.exit(1)

    json_path = Path(sys.argv[1]).expanduser()

    if not json_path.exists():
        print(f"❌ ファイルが見つかりません: {json_path}")
        sys.exit(1)

    # JSONの妥当性チェック
    try:
        with open(json_path, "r") as f:
            data = json.load(f)

        required_keys = ["type", "project_id", "private_key_id", "private_key", "client_email"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"❌ 無効なサービスアカウントJSON（キーが不足: {missing}）")
            sys.exit(1)

        print(f"✅ サービスアカウント: {data['client_email']}")
        print(f"   プロジェクト: {data['project_id']}")
    except json.JSONDecodeError:
        print("❌ JSONの解析に失敗しました")
        sys.exit(1)

    # Base64エンコード
    with open(json_path, "rb") as f:
        raw = f.read()
    b64_encoded = base64.b64encode(raw).decode("utf-8")

    print(f"📦 Base64エンコード: {len(b64_encoded)} 文字 (mod4={len(b64_encoded) % 4})")

    # ローカルにコピー
    local_path = PROJECT_ROOT / "config" / "firebase-service-account.json"
    shutil.copy2(json_path, local_path)
    print(f"📁 ローカルにコピー: {local_path}")

    # .gitignore に追加されているか確認
    gitignore_path = PROJECT_ROOT / ".gitignore"
    if gitignore_path.exists():
        gitignore_content = gitignore_path.read_text()
        if "firebase-service-account" not in gitignore_content:
            with open(gitignore_path, "a") as f:
                f.write("\n# Firebase service account (sensitive)\nconfig/firebase-service-account.json\n")
            print("📝 .gitignore に追加しました")

    # GitHub Secret に設定
    print("\n🔐 GitHub Secret (FIREBASE_CREDENTIALS_BASE64) を設定中...")
    try:
        result = subprocess.run(
            ["gh", "secret", "set", "FIREBASE_CREDENTIALS_BASE64"],
            input=b64_encoded,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("✅ GitHub Secret を設定しました！")
        else:
            print(f"❌ GitHub Secret 設定エラー: {result.stderr}")
            print(f"\n💡 手動で設定する場合:")
            print(f"   echo '{b64_encoded[:20]}...' | gh secret set FIREBASE_CREDENTIALS_BASE64")
    except FileNotFoundError:
        print("⚠️ gh CLI が見つかりません。手動でGitHub Secretsに設定してください:")
        print(f"   Base64値: {b64_encoded[:50]}...（全{len(b64_encoded)}文字）")

    print("\n✅ 完了！GitHub Actions (process-operations) を手動実行してテストしてください:")
    print("   gh workflow run process-operations.yml")


if __name__ == "__main__":
    main()
