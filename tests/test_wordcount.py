from __future__ import annotations

from datetime import datetime, timedelta

from pelican.plugins.stat import wordcount
from pelican.plugins.stat.collector import PelicanArticleDataCollector


def test_count_cjk_chars_pure_chinese():
    assert wordcount.count_cjk_chars("這是一段純中文的內容") == 10


def test_count_cjk_chars_pure_english():
    assert wordcount.count_cjk_chars("This is pure English content") == 0


def test_count_english_words_pure_english():
    assert wordcount.count_english_words("This is pure English content") == 5


def test_count_english_words_pure_chinese():
    assert wordcount.count_english_words("這是一段純中文的內容") == 0


def test_count_english_words_hyphenated_word_splits_into_two():
    assert wordcount.count_english_words("well-known") == 2


def test_mixed_chinese_english_with_punctuation():
    text = "這是中文，mixed with English, 還有標點符號！"
    assert wordcount.count_cjk_chars(text) == 10
    assert wordcount.count_english_words(text) == 3


def test_count_total_chars_includes_punctuation_and_whitespace():
    text = "a b, c."
    assert wordcount.count_total_chars(text) == len(text) == 7


def test_pre_block_code_stripped_out():
    """`<pre>` (block code) must be removed entirely before text extraction
    -- it's pasted-in material, not prose, and shouldn't count toward any
    of CJK chars, English words, or total chars."""
    html = "<p>content</p><pre><code>def foo(): pass</code></pre>"
    text = wordcount._strip_html(html)
    assert "def foo(): pass" not in text
    assert text == "content"


def test_pre_block_code_stripped_out_with_separator():
    """Both `_strip_html()` call sites (with and without a separator) go
    through the same function, so the `<pre>` exclusion must hold for the
    separator path too, not just the default one."""
    html = "<p>content</p><pre><code>def foo(): pass</code></pre>"
    text = wordcount._strip_html(html, separator=" ")
    assert "def foo(): pass" not in text
    assert wordcount.count_english_words(text) == 1  # only "content"


def test_inline_code_not_filtered():
    """Inline `<code>` spans (not wrapped in `<pre>`) are NOT stripped --
    unlike block code, they sit mid-sentence and are kept counted as prose."""
    html = "<p>use <code>git rebase</code> to rewrite history</p>"
    text = wordcount._strip_html(html, separator=" ")
    assert "git rebase" in text
    assert wordcount.count_english_words(text) == 6


def test_strip_html_block_code_flag_off_keeps_pre_content():
    """`strip_block_code=False` is the escape hatch a site opts into via
    `PELICAN_STAT_INCLUDE_CODE_BLOCKS` -- `<pre>` content must survive when
    it's explicitly turned off, unlike the default (`True`)."""
    html = "<p>content</p><pre><code>def foo(): pass</code></pre>"
    text = wordcount._strip_html(html, strip_block_code=False)
    assert "def foo(): pass" in text
    assert text == "contentdef foo(): pass"


def test_strip_html_separator_avoids_adjacent_tag_word_gluing():
    """Without a separator, `<b>hello</b><i>world</i>` collapses into "helloworld",
    under-counting English words. Word/CJK counting must use a separator."""
    html = "<b>hello</b><i>world</i>"
    word_count_text = wordcount._strip_html(html, separator=" ")
    assert wordcount.count_english_words(word_count_text) == 2


def test_strip_html_no_separator_keeps_total_char_count_accurate():
    """Total char counting must NOT use a separator, or the injected
    whitespace would inflate the count beyond the article's own content."""
    html = "<b>hello</b><i>world</i>"
    char_count_text = wordcount._strip_html(html)
    assert wordcount.count_total_chars(char_count_text) == len("helloworld") == 10


def test_now_handles_missing_tzinfo():
    result = wordcount._now(tz=None)
    assert result.tzinfo is None


def test_aggregator_empty_list_guard():
    aggregator = wordcount.ArticleWordCountAggregator([])
    result = aggregator.compute()

    assert result == {
        "post_count": 0,
        "cjk_char_count": 0,
        "english_word_count": 0,
        "total_char_count": 0,
        "writing_years": 0.0,
        "average_chars_per_article": 0.0,
        "median_chars_per_article": 0.0,
    }


def test_compute_handles_naive_article_date():
    """Integration path (through `compute()`, not just the `_now()` wrapper
    in isolation): `article.date` with no tzinfo must not raise, and
    `writing_years` must still come out as a usable number."""

    class _FakeArticle:
        def __init__(self, content: str, date: datetime) -> None:
            self.content = content
            self.date = date

    fake_article = _FakeArticle("<p>hello world</p>", datetime(2020, 1, 1))  # naive, no tzinfo

    aggregator = wordcount.ArticleWordCountAggregator([fake_article])
    result = aggregator.compute()

    assert result["post_count"] == 1
    assert isinstance(result["writing_years"], float)
    assert result["writing_years"] > 0


def test_aggregator_with_real_articles():
    data_collector = PelicanArticleDataCollector("tests/sample_pelican_project/pelicanconf.py")
    aggregator = wordcount.ArticleWordCountAggregator(data_collector.articles)
    result = aggregator.compute()

    assert result["post_count"] == 1
    assert result["total_char_count"] == len("content")
    assert result["average_chars_per_article"] == len("content")
    # Single-article site: median of one value equals that value, same as
    # the mean -- this alone doesn't distinguish median from average, see
    # `test_median_chars_per_article_differs_from_average_when_skewed` for
    # a case that does.
    assert result["median_chars_per_article"] == len("content")


def test_median_chars_per_article_odd_count_is_middle_value():
    class _FakeArticle:
        def __init__(self, content: str, date: datetime) -> None:
            self.content = content
            self.date = date

    articles = [
        _FakeArticle("<p>a</p>", datetime(2020, 1, 1)),  # 1 char
        _FakeArticle("<p>abcde</p>", datetime(2020, 1, 2)),  # 5 chars
        _FakeArticle("<p>abc</p>", datetime(2020, 1, 3)),  # 3 chars
    ]

    result = wordcount.ArticleWordCountAggregator(articles).compute()

    assert result["median_chars_per_article"] == 3
    assert result["average_chars_per_article"] == round((1 + 5 + 3) / 3, 1)


def test_median_chars_per_article_even_count_averages_two_middle_values():
    class _FakeArticle:
        def __init__(self, content: str, date: datetime) -> None:
            self.content = content
            self.date = date

    articles = [
        _FakeArticle("<p>a</p>", datetime(2020, 1, 1)),  # 1 char
        _FakeArticle("<p>abc</p>", datetime(2020, 1, 2)),  # 3 chars
        _FakeArticle("<p>abcde</p>", datetime(2020, 1, 3)),  # 5 chars
        _FakeArticle("<p>abcdefg</p>", datetime(2020, 1, 4)),  # 7 chars
    ]

    result = wordcount.ArticleWordCountAggregator(articles).compute()

    assert result["median_chars_per_article"] == 4  # (3 + 5) / 2


def test_median_chars_per_article_differs_from_average_when_skewed():
    """A single very long article should drag the mean up but not the
    median -- proving `median_chars_per_article` is genuinely computed
    per-article, not just re-deriving the mean."""

    class _FakeArticle:
        def __init__(self, content: str, date: datetime) -> None:
            self.content = content
            self.date = date

    articles = [
        _FakeArticle("<p>" + "a" * 10 + "</p>", datetime(2020, 1, 1)),
        _FakeArticle("<p>" + "a" * 10 + "</p>", datetime(2020, 1, 2)),
        _FakeArticle("<p>" + "a" * 1000 + "</p>", datetime(2020, 1, 3)),  # outlier
    ]

    result = wordcount.ArticleWordCountAggregator(articles).compute()

    assert result["median_chars_per_article"] == 10
    assert result["average_chars_per_article"] > 100
    assert result["median_chars_per_article"] < result["average_chars_per_article"]


def test_pre_block_excluded_from_median_and_average():
    """A `<pre>` block inflating one article's raw HTML must not inflate
    its counted char total -- regression check that the `<pre>` exclusion
    (`_strip_html()`) and the new median field compose correctly."""

    class _FakeArticle:
        def __init__(self, content: str, date: datetime) -> None:
            self.content = content
            self.date = date

    articles = [
        _FakeArticle("<p>abc</p>", datetime(2020, 1, 1)),  # 3 chars
        _FakeArticle(
            "<p>abc</p><pre><code>" + "x" * 1000 + "</code></pre>",
            datetime(2020, 1, 2),
        ),  # still 3 chars once <pre> is stripped
    ]

    result = wordcount.ArticleWordCountAggregator(articles).compute()

    assert result["total_char_count"] == 6
    assert result["median_chars_per_article"] == 3
    assert result["average_chars_per_article"] == 3


# --- `include_block_code` (backs `PELICAN_STAT_INCLUDE_CODE_BLOCKS`) -------
#
# Three scenarios, each asserting an actual differing number (not just that
# a flag was read): unspecified (default), explicitly `True`, explicitly
# `False`. `average_chars_per_article` is used as the observed number since
# it's a direct function of `total_char_count`, which is exactly what
# `include_block_code` controls.


def _make_pre_block_article() -> object:
    class _FakeArticle:
        def __init__(self, content: str, date: datetime) -> None:
            self.content = content
            self.date = date

    # 3 chars of prose + a 100-char `<pre>` block -- large enough that
    # "counted" (103) vs "excluded" (3) can never be mistaken for
    # measurement noise.
    return _FakeArticle("<p>abc</p><pre><code>" + "x" * 100 + "</code></pre>", datetime(2020, 1, 1))


def test_include_block_code_unspecified_defaults_to_excluded():
    """Not passing `include_block_code` at all must behave identically to
    the site never having set `PELICAN_STAT_INCLUDE_CODE_BLOCKS` -- i.e.
    block code excluded, same as before this setting existed."""
    aggregator = wordcount.ArticleWordCountAggregator([_make_pre_block_article()])
    result = aggregator.compute()

    assert result["total_char_count"] == 3
    assert result["average_chars_per_article"] == 3


def test_include_block_code_true_counts_pre_content():
    aggregator = wordcount.ArticleWordCountAggregator([_make_pre_block_article()], include_block_code=True)
    result = aggregator.compute()

    assert result["total_char_count"] == 103
    assert result["average_chars_per_article"] == 103


def test_include_block_code_false_explicit_matches_default():
    """Explicitly passing `False` must produce the same result as not
    passing the parameter at all (the unspecified case above) -- proving
    `False` isn't silently treated differently from "unset"."""
    aggregator = wordcount.ArticleWordCountAggregator([_make_pre_block_article()], include_block_code=False)
    result = aggregator.compute()

    assert result["total_char_count"] == 3
    assert result["average_chars_per_article"] == 3


def test_writing_years_measured_from_earliest_article_to_now(monkeypatch):
    """`writing_years` = earliest article to *now*, not earliest to latest
    article -- it must keep growing even without new posts. `datetime.now()`
    is non-deterministic, so freeze it via monkeypatching `wordcount._now`
    instead of asserting against a moving target."""
    data_collector = PelicanArticleDataCollector("tests/sample_pelican_project/pelicanconf.py")
    aggregator = wordcount.ArticleWordCountAggregator(data_collector.articles)

    earliest_date = data_collector.articles[0].date
    frozen_now = earliest_date + timedelta(days=730)  # exactly 2 years later
    monkeypatch.setattr(wordcount, "_now", lambda tz: frozen_now)

    result = aggregator.compute()

    assert result["writing_years"] == round(730 / 365.25, 1)
