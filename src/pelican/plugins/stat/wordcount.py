from __future__ import annotations

import re
import statistics
from datetime import datetime, tzinfo

from bs4 import BeautifulSoup

from pelican.contents import Article

# --- Known limitations (documented here once, not repeated per-field) -----
#
# - CJK char count only covers the CJK Unified Ideographs BMP block
#   (U+4E00-U+9FFF). Rare traditional variants living in the Extension B+
#   supplementary planes are not counted.
# - English word count treats hyphens as word boundaries (no special
#   handling), so a hyphenated word such as "well-known" is counted as two
#   words ("well", "known").
# - Total char count includes punctuation and whitespace, not just "content"
#   characters -- it's a raw `len()` over the extracted text.
# - Block code (`<pre>`, which wraps every fenced/indented code block a
#   typical Markdown pipeline emits) is stripped out by `_strip_html()`
#   before any counting happens by default -- it's pasted-in material, not
#   prose, and (measured on a real 322-article site) was ~21% of the raw
#   character count, enough to meaningfully skew "average/median chars per
#   article" toward a handful of code-heavy posts. This is configurable --
#   see `ArticleWordCountAggregator.__init__`'s `include_block_code`
#   parameter and `PELICAN_STAT_INCLUDE_CODE_BLOCKS` (the Pelican-facing
#   setting a site can flip; read by `stat.py`/`__main__.py`, NOT by this
#   module -- see that parameter's docstring for why the boundary is drawn
#   there). Inline `<code>` spans (e.g. "use `git rebase` to rewrite
#   history") are NOT configurable and always stay counted -- they sit
#   mid-sentence, so removing them would leave a grammatical gap in the
#   extracted text, and they're a small, fairly constant share of content
#   (~3% on that same site) so a second on/off knob for them isn't worth
#   the added surface.
# - `_strip_html()` is called twice per article with different `separator`
#   values (see its docstring) to avoid two competing failure modes:
#   under-counting English words across adjacent inline tags vs.
#   over-counting total characters from injected separator whitespace.
# - `writing_years` measures "first article to now" (not "first to last
#   article"), so it keeps growing even during a dry spell with no new
#   posts -- see `ArticleWordCountAggregator.compute()` for why, and note
#   this makes the aggregate result non-deterministic across calls (it
#   depends on wall-clock time).
# - This site also computes a "years writing" figure independently in
#   `pelican-heatmap`'s `calculateYearsWriting()`
#   (`pelican_heatmap.js:175-178`, sibling plugin, same repo family) --
#   NOT the same code path, and the two are not guaranteed to agree. This
#   module: exact `datetime` timestamps, `.days` (integer-truncated) //
#   365.25, the source article's own tzinfo (as Pelican attaches it from
#   the site's `TIMEZONE` setting -- Asia/Taipei for this deployment),
#   Python `round()` (banker's rounding). Heatmap's JS: calendar-day
#   granularity via `Math.floor((today - earliestDate) / 86400000)`, the
#   *reader's browser* local timezone (not the site's configured
#   `TIMEZONE`), and `toFixed()` (different rounding, returns a string not
#   a number). Confirmed via a real Node repro against this site's actual
#   earliest-article date: the two happened to both round to `12.7` at
#   review time -- a coincidence for that specific date, not a guarantee
#   for any other. Currently harmless because neither the
#   `pelican-stat` widget nor any current consumer displays this field
#   side-by-side with heatmap's own (this widget's `_WIDGET_FIELDS` no
#   longer includes `writing_years` at all -- see `stat.py`), but a latent
#   risk if a future template/widget ever renders both numbers on the same
#   page expecting them to match.
# ---------------------------------------------------------------------------

_CJK_CHAR_PATTERN = re.compile(r"[一-鿿]")
_ENGLISH_WORD_PATTERN = re.compile(r"[A-Za-z]+")


def _strip_html(html: str, *, separator: str = "", strip_block_code: bool = True) -> str:
    """Extract plain text from HTML content.

    `strip_block_code` (default `True`, matching this module's own default
    behavior) removes every `<pre>` element (block code -- fenced/indented
    code blocks) via `.decompose()` before text is extracted, so its
    content counts toward none of CJK chars, English words, or total
    chars. This is the single choke point both of `compute()`'s two calls
    (word/CJK counting with a separator, and total-char counting without
    one) go through, so both paths respect the same flag -- no need to
    filter twice. Passing `strip_block_code=False` keeps `<pre>` content in
    the extracted text (used when a site opts into counting block code via
    `PELICAN_STAT_INCLUDE_CODE_BLOCKS`, see
    `ArticleWordCountAggregator.__init__`). Inline `<code>` spans are
    always left alone regardless of this flag (see the module-level "Known
    limitations" note for why) -- there is no equivalent toggle for them.

    `separator` is inserted between text extracted from adjacent tags.
    Without it, `BeautifulSoup.get_text()` concatenates text across tag
    boundaries with nothing in between, so e.g. `<b>hello</b><i>world</i>`
    collapses into "helloworld" and English word counting would
    under-count. Passing a whitespace separator fixes that -- but it also
    means the separator characters themselves get counted, which would
    inflate a total character count. So callers must pick per use case:
    whitespace separator for word/CJK-char counting, no separator (default)
    for total character counting.
    """
    soup = BeautifulSoup(html, "html.parser")
    if strip_block_code:
        for pre in soup.find_all("pre"):
            pre.decompose()
    return soup.get_text(separator=separator)


def count_cjk_chars(text: str) -> int:
    """Count CJK (Chinese) characters in the given text."""
    return len(_CJK_CHAR_PATTERN.findall(text))


def count_english_words(text: str) -> int:
    """Count English words in the given text."""
    return len(_ENGLISH_WORD_PATTERN.findall(text))


def count_total_chars(text: str) -> int:
    """Count all characters in the given text, including punctuation and whitespace."""
    return len(text)


def _now(tz: tzinfo | None) -> datetime:
    """Thin wrapper around `datetime.now()` so tests can monkeypatch it.

    `tz=None` falls back to naive local time, matching the behavior of an
    `article.date` that (unusually) has no tzinfo attached, so the
    subtraction in `compute()` never mixes naive and aware datetimes.
    """
    return datetime.now(tz=tz)


class ArticleWordCountAggregator:
    """Compute site-wide word count statistics for a list of articles.

    This is a pure calculation layer: it only depends on
    ``list[pelican.contents.Article]`` and a plain ``bool``, and does not
    know how the articles were collected (CLI rebuild vs. Pelican plugin
    signal) or that a Pelican ``settings`` dict / ``PELICAN_STAT_*`` key
    exists at all. Callers (`stat.py`'s plugin handler, `__main__.py`'s
    CLI) are responsible for reading `PELICAN_STAT_INCLUDE_CODE_BLOCKS`
    out of Pelican settings themselves and passing the plain bool in here
    -- this module deliberately never imports Pelican settings, so it stays
    testable and reusable without a running Pelican instance.
    """

    def __init__(self, articles: list[Article], *, include_block_code: bool = False) -> None:
        """
        `include_block_code` (default `False`, i.e. block code is excluded
        by default): whether text inside `<pre>` elements (block code)
        should count toward CJK chars / English words / total chars /
        average / median. Mirrors `PELICAN_STAT_INCLUDE_CODE_BLOCKS` --
        see that setting's usage in `stat.py`/`__main__.py` for how a site
        or CLI invocation controls this. Does NOT affect inline `<code>`
        spans, which are always counted (no equivalent toggle exists for
        them -- see this module's "Known limitations" note).
        """
        self.articles = articles
        self.include_block_code = include_block_code

    def compute(self) -> dict[str, int | float]:
        if not self.articles:
            return {
                "post_count": 0,
                "cjk_char_count": 0,
                "english_word_count": 0,
                "total_char_count": 0,
                "writing_years": 0.0,
                "average_chars_per_article": 0.0,
                "median_chars_per_article": 0.0,
            }

        cjk_char_count = 0
        english_word_count = 0
        total_char_count = 0
        dates = []
        # Per-article char counts, needed for the median (a site-wide sum
        # alone can't reconstruct the distribution across articles the way
        # it can for a mean).
        chars_per_article = []

        # `_strip_html()`'s default (`strip_block_code=True`) excludes
        # `<pre>` content; `include_block_code=True` flips that off so
        # `<pre>` text is kept in, for both calls below.
        strip_block_code = not self.include_block_code

        for article in self.articles:
            # Word/CJK-char counting needs a separator so adjacent inline
            # tags don't concatenate into one word; total char counting
            # must NOT have one, or the inserted separators would inflate
            # the count. See `_strip_html()`'s docstring.
            word_count_text = _strip_html(article.content, separator=" ", strip_block_code=strip_block_code)
            char_count_text = _strip_html(article.content, strip_block_code=strip_block_code)

            cjk_char_count += count_cjk_chars(word_count_text)
            english_word_count += count_english_words(word_count_text)
            article_char_count = count_total_chars(char_count_text)
            total_char_count += article_char_count
            chars_per_article.append(article_char_count)
            dates.append(article.date)

        post_count = len(self.articles)
        earliest_date = min(dates)

        # "writing_years" is meant to answer "how many years has this blog
        # been written for", which should keep growing over time even if
        # there's been no new post recently -- so it's measured from the
        # earliest article to *now*, not to the latest article. The
        # trade-off: this makes the field non-deterministic (depends on
        # wall-clock time at call time), unlike every other field here.
        writing_years = (_now(tz=earliest_date.tzinfo) - earliest_date).days / 365.25

        return {
            "post_count": post_count,
            "cjk_char_count": cjk_char_count,
            "english_word_count": english_word_count,
            "total_char_count": total_char_count,
            "writing_years": round(writing_years, 1),
            "average_chars_per_article": round(total_char_count / post_count, 1),
            # `statistics.median` rather than a hand-rolled sort+index: it
            # already correctly handles both the odd-count (middle element)
            # and even-count (average of the two middle elements) cases.
            "median_chars_per_article": round(statistics.median(chars_per_article), 1),
        }
