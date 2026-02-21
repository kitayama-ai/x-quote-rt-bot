"""
X Auto Post System — ペルソナ分析器

Xアカウントの過去ツイートを分析し、文体・口調・言い回しを完全コピーするための
ペルソナプロファイルを自動生成する。

使い方:
    analyzer = PersonaAnalyzer(config)
    profile = analyzer.analyze_account(tweets)
    # → プロンプトテンプレートに注入可能な形式で返す
"""
import re
import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Optional

from google import genai

from src.config import Config


@dataclass
class PersonaProfile:
    """Xアカウントの文体プロファイル"""

    # 基本情報
    username: str = ""
    display_name: str = ""
    bio: str = ""
    tweet_count_analyzed: int = 0

    # 一人称
    first_person: str = ""  # 「僕」「私」「俺」「自分」等
    first_person_frequency: float = 0.0  # 使用率

    # 文末パターン（トップ10）
    sentence_endings: list[str] = field(default_factory=list)

    # 頻出フレーズ・口癖
    catchphrases: list[str] = field(default_factory=list)

    # 感情表現
    emotion_words: list[str] = field(default_factory=list)

    # 文体特徴
    avg_tweet_length: float = 0.0
    avg_line_count: float = 0.0
    uses_emoji: bool = False
    emoji_frequency: float = 0.0
    top_emojis: list[str] = field(default_factory=list)
    uses_hashtags: bool = False
    punctuation_style: str = ""  # 「句読点多い」「改行多め」「体言止め多い」等
    kanji_ratio: float = 0.0  # 漢字率

    # トーン分析
    tone: str = ""  # 「カジュアル」「知的」「熱量高い」等
    formality_level: str = ""  # 「タメ口」「敬語まじり」「完全敬語」

    # 投稿パターン
    topics: list[str] = field(default_factory=list)
    content_types: dict = field(default_factory=dict)  # 意見/情報共有/質問/報告 の比率

    # AIプロンプト用の要約
    prompt_summary: str = ""

    # サンプルツイート（プロンプト例示用）
    sample_tweets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_injection(self) -> str:
        """プロンプトテンプレートに注入可能な形式に変換"""
        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("■ ペルソナプロファイル（自動分析）")
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("")

        if self.first_person:
            lines.append(f"- 一人称: 「{self.first_person}」")

        if self.sentence_endings:
            endings = "、".join([f"「{e}」" for e in self.sentence_endings[:7]])
            lines.append(f"- 文末パターン: {endings}")

        if self.catchphrases:
            phrases = "、".join([f"「{p}」" for p in self.catchphrases[:10]])
            lines.append(f"- 口癖・頻出フレーズ: {phrases}")

        if self.emotion_words:
            emo = "、".join([f"「{e}」" for e in self.emotion_words[:8]])
            lines.append(f"- 感情表現: {emo}")

        if self.tone:
            lines.append(f"- トーン: {self.tone}")

        if self.formality_level:
            lines.append(f"- 敬語レベル: {self.formality_level}")

        if self.punctuation_style:
            lines.append(f"- 句読点・改行: {self.punctuation_style}")

        if self.uses_emoji and self.top_emojis:
            emojis = "".join(self.top_emojis[:5])
            lines.append(f"- よく使う絵文字: {emojis}（頻度: {self.emoji_frequency:.0%}）")
        elif not self.uses_emoji:
            lines.append("- 絵文字: ほぼ使わない")

        lines.append(f"- 平均ツイート長: 約{self.avg_tweet_length:.0f}文字")
        lines.append(f"- 平均行数: 約{self.avg_line_count:.1f}行")

        if self.prompt_summary:
            lines.append("")
            lines.append("### AI要約")
            lines.append(self.prompt_summary)

        if self.sample_tweets:
            lines.append("")
            lines.append("### お手本ツイート（実際の投稿から抜粋）")
            for i, tweet in enumerate(self.sample_tweets[:5], 1):
                lines.append(f"\n--- 例{i} ---")
                lines.append(tweet)

        return "\n".join(lines)


class PersonaAnalyzer:
    """Xアカウントの文体を分析してPersonaProfileを生成"""

    # 一人称候補
    FIRST_PERSONS = ["僕", "俺", "私", "自分", "ワイ", "わし", "うち", "あたし", "おれ", "ぼく", "わたし"]

    # 感情語候補
    EMOTION_WORDS = [
        "マジで", "ガチで", "ガチ", "まじで", "えぐい", "やばい", "ヤバい", "やばくない",
        "最強", "最高", "神", "鬼", "半端ない", "めちゃくちゃ", "めっちゃ", "すごい",
        "凄い", "ありえない", "ありえん", "しんどい", "つらい", "嬉しい", "楽しい",
        "面白い", "おもろい", "怖い", "こわい", "ぶっちゃけ", "正直", "率直に",
        "控えめに言って", "割と", "結構", "かなり", "なかなか", "相当",
        "圧倒的", "激しく", "猛烈に", "劇的に", "爆速", "秒速",
    ]

    # 文末パターン
    ENDING_PATTERNS = [
        (r"[だよ。]+$", "だよ。"),
        (r"[だな。]+$", "だな。"),
        (r"[だね。]+$", "だね。"),
        (r"[だよね。]+$", "だよね。"),
        (r"[じゃん。]+$", "じゃん。"),
        (r"[よな。]+$", "よな。"),
        (r"[よね。]+$", "よね。"),
        (r"[けど。]+$", "けど。"),
        (r"[けどね。]+$", "けどね。"),
        (r"してる。?$", "してる。"),
        (r"している。?$", "している。"),
        (r"と思う。?$", "と思う。"),
        (r"かもしれない。?$", "かもしれない。"),
        (r"一択。?$", "一択。"),
        (r"な気がする。?$", "な気がする。"),
        (r"[ですね。]+$", "ですね。"),
        (r"[ですよ。]+$", "ですよ。"),
        (r"[ますね。]+$", "ますね。"),
        (r"[ました。]+$", "ました。"),
        (r"[でした。]+$", "でした。"),
    ]

    def __init__(self, config: Config):
        self.config = config
        if config.gemini_api_key:
            self.client = genai.Client(api_key=config.gemini_api_key)
            self.model_name = config.gemini_model
        else:
            self.client = None
            self.model_name = None

    def analyze_account(
        self,
        tweets: list[str],
        username: str = "",
        display_name: str = "",
        bio: str = "",
    ) -> PersonaProfile:
        """
        ツイート群からペルソナプロファイルを生成

        Args:
            tweets: ツイートテキストのリスト（多いほど精度が上がる、50-200推奨）
            username: Xユーザー名
            display_name: 表示名
            bio: プロフィール文

        Returns:
            PersonaProfile
        """
        profile = PersonaProfile(
            username=username,
            display_name=display_name,
            bio=bio,
            tweet_count_analyzed=len(tweets),
        )

        if not tweets:
            return profile

        # === 統計的分析 ===
        self._analyze_first_person(tweets, profile)
        self._analyze_sentence_endings(tweets, profile)
        self._analyze_emotion_words(tweets, profile)
        self._analyze_emoji(tweets, profile)
        self._analyze_structure(tweets, profile)
        self._analyze_punctuation(tweets, profile)
        self._select_sample_tweets(tweets, profile)

        # === AI分析（Gemini） ===
        if self.client:
            self._ai_analyze(tweets, profile)

        return profile

    def _analyze_first_person(self, tweets: list[str], profile: PersonaProfile):
        """一人称の特定"""
        counter = Counter()
        total = len(tweets)

        for tweet in tweets:
            for fp in self.FIRST_PERSONS:
                if fp in tweet:
                    counter[fp] += 1

        if counter:
            most_common = counter.most_common(1)[0]
            profile.first_person = most_common[0]
            profile.first_person_frequency = most_common[1] / total

    def _analyze_sentence_endings(self, tweets: list[str], profile: PersonaProfile):
        """文末パターンの分析"""
        ending_counter = Counter()

        for tweet in tweets:
            # 改行で分割して各行の文末を分析
            lines = [l.strip() for l in tweet.split("\n") if l.strip()]
            for line in lines:
                # 体言止めチェック
                if re.search(r'[一-龥ァ-ヶー]+[。．]?$', line):
                    ending_counter["体言止め"] += 1

                # パターンマッチ
                for pattern, label in self.ENDING_PATTERNS:
                    if re.search(pattern, line):
                        ending_counter[label] += 1
                        break

        profile.sentence_endings = [e for e, _ in ending_counter.most_common(10)]

    def _analyze_emotion_words(self, tweets: list[str], profile: PersonaProfile):
        """感情語・口癖の分析"""
        word_counter = Counter()
        all_text = " ".join(tweets)

        for word in self.EMOTION_WORDS:
            count = all_text.count(word)
            if count > 0:
                word_counter[word] = count

        profile.emotion_words = [w for w, _ in word_counter.most_common(15)]

        # 頻出フレーズ（2-4文字のN-gram分析）
        phrase_counter = Counter()
        for tweet in tweets:
            # 句読点・改行で分割
            segments = re.split(r'[。\n、！？!?]', tweet)
            for seg in segments:
                seg = seg.strip()
                if 4 <= len(seg) <= 15:
                    phrase_counter[seg] += 1

        # 3回以上出現するフレーズを口癖として抽出
        profile.catchphrases = [
            phrase for phrase, count in phrase_counter.most_common(20)
            if count >= 3
        ][:10]

    def _analyze_emoji(self, tweets: list[str], profile: PersonaProfile):
        """絵文字使用分析"""
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF\U00002600-\U000026FF"
            "\U0000FE00-\U0000FE0F\U0000200D]+",
            flags=re.UNICODE
        )

        emoji_counter = Counter()
        tweets_with_emoji = 0

        for tweet in tweets:
            emojis = emoji_pattern.findall(tweet)
            if emojis:
                tweets_with_emoji += 1
                for e in emojis:
                    emoji_counter[e] += 1

        profile.uses_emoji = tweets_with_emoji > len(tweets) * 0.1
        profile.emoji_frequency = tweets_with_emoji / len(tweets) if tweets else 0
        profile.top_emojis = [e for e, _ in emoji_counter.most_common(10)]

    def _analyze_structure(self, tweets: list[str], profile: PersonaProfile):
        """構造分析（長さ、行数等）"""
        lengths = [len(t) for t in tweets]
        line_counts = [len(t.split("\n")) for t in tweets]

        profile.avg_tweet_length = sum(lengths) / len(lengths) if lengths else 0
        profile.avg_line_count = sum(line_counts) / len(line_counts) if line_counts else 0

        # 漢字率
        total_chars = sum(lengths)
        kanji_count = sum(
            1 for t in tweets for c in t
            if '\u4e00' <= c <= '\u9fff'
        )
        profile.kanji_ratio = kanji_count / total_chars if total_chars else 0

    def _analyze_punctuation(self, tweets: list[str], profile: PersonaProfile):
        """句読点・改行スタイル分析"""
        total = len(tweets)
        period_count = sum(t.count("。") for t in tweets)
        comma_count = sum(t.count("、") for t in tweets)
        newline_count = sum(t.count("\n") for t in tweets)
        taigen_dome = sum(
            1 for t in tweets
            for line in t.split("\n")
            if re.search(r'[一-龥ァ-ヶー]+[。．]?\s*$', line.strip())
        )

        styles = []
        if period_count / total < 1.0:
            styles.append("句点少なめ")
        else:
            styles.append("句点使う")

        if newline_count / total > 2.0:
            styles.append("改行多め")

        if taigen_dome / total > 1.0:
            styles.append("体言止め多用")

        # 敬語レベル判定
        desu_masu = sum(
            1 for t in tweets
            if re.search(r'(です|ます|ました|でした|ません)[。！？!?\s]*$', t, re.MULTILINE)
        )
        casual = sum(
            1 for t in tweets
            if re.search(r'(だよ|だな|じゃん|よな|してる|してた)[。！？!?\s]*$', t, re.MULTILINE)
        )

        if desu_masu > casual * 2:
            profile.formality_level = "敬語ベース"
        elif casual > desu_masu * 2:
            profile.formality_level = "タメ口ベース"
        else:
            profile.formality_level = "敬語とタメ口ミックス"

        profile.punctuation_style = "、".join(styles)

    def _select_sample_tweets(self, tweets: list[str], profile: PersonaProfile):
        """プロンプト例示用のサンプルツイートを選定"""
        # 文字数が50-250字で、いい感じのものを選ぶ
        candidates = [
            t for t in tweets
            if 50 <= len(t) <= 250
            and "\n" in t  # 改行を含む（構造的な投稿）
            and not t.startswith("RT ")
            and not t.startswith("@")
            and "http" not in t
        ]

        if not candidates:
            candidates = [t for t in tweets if 30 <= len(t) <= 280 and "http" not in t]

        # 多様性を持たせてサンプリング
        import random
        random.shuffle(candidates)
        profile.sample_tweets = candidates[:8]

    def _ai_analyze(self, tweets: list[str], profile: PersonaProfile):
        """Geminiを使ったAI文体分析"""
        # 分析用にサンプルを取得（最大30件）
        import random
        sample = random.sample(tweets, min(30, len(tweets)))
        tweets_text = "\n---\n".join(sample)

        prompt = f"""
以下は@{profile.username}のツイート{len(sample)}件です。
このアカウントの文体・口調・言い回しを徹底分析してください。

━━━━━━━━━━━━
■ 分析対象ツイート
━━━━━━━━━━━━
{tweets_text}

━━━━━━━━━━━━
■ 分析してほしいこと
━━━━━━━━━━━━

以下のJSON形式で出力してください。余計な説明は不要。

{{
  "tone": "トーン（例: カジュアルだが知的、熱量高い、冷静な分析者、etc.）",
  "topics": ["主なトピック1", "主なトピック2", "主なトピック3"],
  "content_types": {{
    "意見・主張": 0.3,
    "情報共有": 0.4,
    "実体験報告": 0.2,
    "質問・問いかけ": 0.1
  }},
  "prompt_summary": "このアカウントの投稿文を完璧にコピーするために、AIが守るべき文体ルールを200字以内で簡潔にまとめてください。一人称、語尾、改行の使い方、感情表現、避けるべき表現を含めてください。"
}}
"""

        try:
            from src.utils import retry_with_backoff

            def _call():
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                text = response.text.strip()
                # JSON部分を抽出
                match = re.search(r'\{[\s\S]*\}', text)
                if match:
                    return json.loads(match.group())
                return None

            result = retry_with_backoff(_call, max_retries=2, label="ペルソナAI分析")
            if result:
                profile.tone = result.get("tone", "")
                profile.topics = result.get("topics", [])
                profile.content_types = result.get("content_types", {})
                profile.prompt_summary = result.get("prompt_summary", "")

        except Exception as e:
            print(f"[PersonaAnalyzer] AI分析失敗（統計分析結果は有効）: {e}")
