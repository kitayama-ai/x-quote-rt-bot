"""
X Auto Post System — 投稿スコアリング

x-monetize-project/quality_scoring.md の8点満点スコアリングをPython実装。
"""
import re
from dataclasses import dataclass


@dataclass
class ScoreResult:
    """スコアリング結果"""
    total: float
    hook: int          # 0-2
    specificity: int   # 0-2
    humanity: int      # 0-2
    structure: int     # 0-1
    cta: int           # 0-1
    penalty: int       # 0 or -1 per violation
    details: dict

    @property
    def rank(self) -> str:
        if self.total >= 8:
            return "S"
        elif self.total >= 6:
            return "A"
        elif self.total >= 4:
            return "B"
        else:
            return "C"


class PostScorer:
    """投稿の品質をスコアリング"""

    # フック（書き出し）のパターン
    STRONG_HOOKS = [
        r'^(ぶっちゃけ|正直|マジで|結論|断言)',
        r'^「.+」',                          # 引用形式
        r'^\d+[時間分万円%]',                  # 数字始まり
        r'^(やばい|えぐい|これ)',              # 感情爆発
        r'^(知らない|まだ.+してる)',           # 問いかけ系
    ]

    MEDIUM_HOOKS = [
        r'^(最近|今月|この前)',                 # 時間軸
        r'^AI[でがは]',                        # テーマ直球
        r'^.{1,10}[。、]$',                    # 短い体言止め1行目
    ]

    def score(self, text: str, post_type: str = "") -> ScoreResult:
        """
        8点満点でスコアリング

        - フック力 (0-2)
        - 具体性 (0-2)
        - 人間味 (0-2)
        - 構成 (0-1)
        - CTA (0-1)
        - ペナルティ (-1 per violation)
        """
        details = {}
        lines = text.strip().split('\n')
        first_line = lines[0] if lines else ""

        # === フック力 (0-2) ===
        hook = 0
        if any(re.search(p, first_line) for p in self.STRONG_HOOKS):
            hook = 2
            details["hook"] = "強フック検出"
        elif any(re.search(p, first_line) for p in self.MEDIUM_HOOKS):
            hook = 1
            details["hook"] = "中フック検出"
        else:
            details["hook"] = "フック弱い"

        # === 具体性 (0-2) ===
        specificity = 0
        numbers = re.findall(r'\d+[時間分万円%倍個件本日週月]', text)
        comparisons = re.findall(r'[→⇒]|から|が.+に', text)
        tools = re.findall(
            r'(Claude|ChatGPT|GAS|Gemini|note|スプシ|スプレッドシート|Python|GitHub)',
            text, re.IGNORECASE
        )

        if len(numbers) >= 2 or (numbers and comparisons):
            specificity = 2
            details["specificity"] = f"数字{len(numbers)}個, 比較表現あり"
        elif numbers or tools:
            specificity = 1
            details["specificity"] = f"数字{len(numbers)}個 / ツール名{len(tools)}個"
        else:
            details["specificity"] = "具体性不足"

        # === 人間味 (0-2) ===
        humanity = 0
        casual_markers = [
            'ぶっちゃけ', 'マジで', 'ガチ', 'なんだよね', 'してた',
            'だよな', 'じゃん', 'えぐい', 'やばい', 'なんだけど',
            '正直', '結論から', 'これは'
        ]
        ai_markers = [
            '素晴らしい', '革新的', '画期的', 'いかがでしたか',
            '活用してみてください', '重要です', '解説します',
            'しましょう', 'おすすめです'
        ]

        casual_count = sum(1 for m in casual_markers if m in text)
        ai_count = sum(1 for m in ai_markers if m in text)

        if casual_count >= 2 and ai_count == 0:
            humanity = 2
            details["humanity"] = f"カジュアル表現{casual_count}個, AI感ゼロ"
        elif casual_count >= 1 and ai_count <= 1:
            humanity = 1
            details["humanity"] = f"カジュアル{casual_count}個, AI感{ai_count}個"
        else:
            details["humanity"] = f"人間味不足 (カジュアル{casual_count}, AI感{ai_count})"

        # === 構成 (0-1) ===
        structure = 0
        text_len = len(text.replace('\n', ''))
        line_count = len([l for l in lines if l.strip()])

        if 40 <= text_len <= 280 and line_count >= 3:
            structure = 1
            details["structure"] = f"{text_len}字, {line_count}行 — OK"
        else:
            details["structure"] = f"{text_len}字, {line_count}行 — 要改善"

        # === CTA (0-1) ===
        cta = 0
        last_lines = '\n'.join(lines[-2:]) if len(lines) >= 2 else text
        cta_patterns = [
            r'ブクマ', r'保存', r'プロフ', r'リンク',
            r'べき[。．]?$', r'一択[。．]?$', r'間違いない[。．]?$',
            r'ガチ[。．]?$', r'マジ[。．]?$',
            r'[。．]$',
        ]
        if any(re.search(p, last_lines) for p in cta_patterns):
            cta = 1
            details["cta"] = "CTA検出"
        else:
            details["cta"] = "CTAなし"

        # === ペナルティ ===
        penalty = 0
        penalties = []

        # URL検出
        if re.search(r'https?://', text):
            penalty -= 1
            penalties.append("URL含有")

        # ハッシュタグ過多
        hashtags = re.findall(r'#\S+', text)
        if len(hashtags) > 3:
            penalty -= 1
            penalties.append(f"ハッシュタグ{len(hashtags)}個")

        # 文字数オーバー
        if text_len > 280:
            penalty -= 1
            penalties.append(f"文字数超過({text_len}字)")

        details["penalty"] = penalties if penalties else "なし"

        total = max(0, hook + specificity + humanity + structure + cta + penalty)

        return ScoreResult(
            total=total,
            hook=hook,
            specificity=specificity,
            humanity=humanity,
            structure=structure,
            cta=cta,
            penalty=penalty,
            details=details
        )

    def format_score(self, result: ScoreResult) -> str:
        """スコアをDiscord通知用にフォーマット"""
        return (
            f"📊 スコア: {result.total}/8 [{result.rank}]\n"
            f"├ フック力: {result.hook}/2 ({result.details.get('hook', '')})\n"
            f"├ 具体性: {result.specificity}/2 ({result.details.get('specificity', '')})\n"
            f"├ 人間味: {result.humanity}/2 ({result.details.get('humanity', '')})\n"
            f"├ 構成: {result.structure}/1 ({result.details.get('structure', '')})\n"
            f"├ CTA: {result.cta}/1 ({result.details.get('cta', '')})\n"
            f"└ ペナルティ: {result.penalty} ({result.details.get('penalty', '')})"
        )
