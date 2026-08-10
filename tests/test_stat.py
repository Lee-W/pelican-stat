from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import markdown

import pelican
from pelican import signals  # type: ignore[attr-defined]
from pelican.generators import Generator
from pelican.plugins.stat import stat, wordcount
from pelican.plugins.stat.plotter import PelicanDataPlotter


def _run_minimal_build(output_path, *, extra_settings=None, content_path=None):
    """`extra_settings` (merged on top of the sample project's own settings)
    and `content_path` (overrides `PATH`) let a test point this at custom
    content and/or flip `PELICAN_STAT_*` settings -- used by the
    `PELICAN_STAT_INCLUDE_CODE_BLOCKS` tests below, which need an article
    containing a `<pre>` block that the shared sample project's single
    plain-text article doesn't have."""
    settings = pelican.read_settings("tests/sample_pelican_project/pelicanconf.py")
    settings["PLUGINS"] = ["pelican.plugins.stat"]
    settings["OUTPUT_PATH"] = str(output_path)
    if content_path is not None:
        settings["PATH"] = content_path
    if extra_settings:
        settings.update(extra_settings)

    captured_generators = []

    def _capture(generators):
        captured_generators.append(generators)

    signals.all_generators_finalized.connect(_capture, weak=False)
    try:
        pelican_instance = pelican.Pelican(settings)
        pelican_instance.run()
    finally:
        signals.all_generators_finalized.disconnect(_capture)

    return captured_generators[-1]


def _generate_context_generators(output_path: Path, *, round_name: str = "") -> list[Generator]:
    """Build real `Generator`s (incl. a real `ArticlesGenerator`) up through
    `generate_context()`, WITHOUT running `generate_output()`/`finalized`.

    Mirrors what `pelican.Pelican.run()` itself does before it sends
    `all_generators_finalized` (see `stat.py`'s module docstring for the
    full, source-verified timeline). Used to simulate two independent
    `all_generators_finalized` "rounds" -- one primary, one nested -- by
    calling `stat._attach_word_count_stats()` directly on each round's
    generators, without needing a real nested `i18n_subsites` build (that
    package isn't a test dependency of `pelican-stat`, on purpose).

    Every call reads the *same* `tests/sample_pelican_project` fixture (1
    article), so two calls simulate two rounds of 1 article each. In a real
    two-round build (primary zh + nested en), each round's articles come
    from genuinely different source files, so their `source_path`s differ
    -- but re-reading the same fixture file gives both calls' article the
    *same* `source_path`, which is indistinguishable from the crash/
    livereload double-accumulation scenario `_ACCUMULATED_SOURCE_PATHS`
    (see `stat.py`) is specifically designed to dedup away. Pass a distinct
    `round_name` per call to give each round's article a distinct
    `source_path`, so accumulation tests keep exercising genuine two-round
    accumulation instead of tripping the dedup guard.
    """
    settings = pelican.read_settings("tests/sample_pelican_project/pelicanconf.py")  # type: ignore[attr-defined]
    settings["PLUGINS"] = []  # no plugins registered -- signal handlers are invoked manually below
    settings["OUTPUT_PATH"] = str(output_path)

    pelican_instance = pelican.Pelican(settings)  # type: ignore[attr-defined]
    context = pelican_instance.settings.copy()
    context["generated_content"] = {}
    context["static_links"] = set()
    context["static_content"] = {}
    context["localsiteurl"] = pelican_instance.settings["SITEURL"]

    generators = [
        cls(
            context=context,
            settings=pelican_instance.settings,
            path=pelican_instance.path,
            theme=pelican_instance.theme,
            output_path=pelican_instance.output_path,
        )
        for cls in pelican_instance._get_generator_classes()
    ]
    for generator in generators:
        if hasattr(generator, "generate_context"):
            generator.generate_context()
    if round_name:
        for generator in generators:
            for article in getattr(generator, "articles", []):
                article.source_path = f"{article.source_path}#{round_name}"
    return generators


def setup_function():
    stat._reset_cache_for_testing()


# --- `PELICAN_STAT_INCLUDE_CODE_BLOCKS` end-to-end (settings -> `_settings`
# -> `ArticleWordCountAggregator`) ------------------------------------------


def _write_pre_block_content(tmp_path: Path) -> str:
    """A one-article content dir: 3 chars of prose ("abc") plus an indented
    (4-space) code block, which Python-Markdown's built-in (always-on, no
    extension needed) code block handling renders as `<pre><code>...`.
    Returns the content dir path as a `str` (what `PATH` expects)."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "pre_article.md").write_text(
        "Title: pre title\n"
        "Date: 2021-01-19 16:12\n"
        "Category: Testing\n"
        "Slug: pre-title\n"
        "\n"
        "abc\n"
        "\n"
        "    def foo():\n"
        "        pass\n",
        encoding="utf-8",
    )
    return str(content_dir)


def test_include_code_blocks_setting_unspecified_and_false_match_true_differs(tmp_path):
    """Three real `Pelican.run()` builds over the SAME `<pre>`-containing
    article, differing only in `PELICAN_STAT_INCLUDE_CODE_BLOCKS`: not
    mentioning it at all, explicitly `False`, and explicitly `True`.
    Compares the resulting `total_char_count`s against EACH OTHER (not a
    hardcoded literal) -- Python-Markdown's own rendering inserts
    whitespace text nodes between `<p>` and `<pre>` that make the "exact
    prose-only char count" an implementation detail of the Markdown
    library, not of this setting; what this setting must guarantee is
    "unspecified behaves exactly like explicit `False`, and explicit `True`
    is strictly larger" -- so that's what's asserted, not a magic number.
    """
    content_path = _write_pre_block_content(tmp_path)

    stats_unspecified = _run_minimal_build(tmp_path / "out-unspecified", content_path=content_path)[
        0
    ].context["pelican_stat_word_count"]
    stats_false = _run_minimal_build(
        tmp_path / "out-false",
        content_path=content_path,
        extra_settings={"PELICAN_STAT_INCLUDE_CODE_BLOCKS": False},
    )[0].context["pelican_stat_word_count"]
    stats_true = _run_minimal_build(
        tmp_path / "out-true",
        content_path=content_path,
        extra_settings={"PELICAN_STAT_INCLUDE_CODE_BLOCKS": True},
    )[0].context["pelican_stat_word_count"]

    assert stats_unspecified["total_char_count"] == stats_false["total_char_count"]
    assert stats_true["total_char_count"] > stats_unspecified["total_char_count"]
    # Not just "some" bigger -- the code block itself ("def foo():\n    pass")
    # is 20 chars, so the increase must be at least that much, proving the
    # `<pre>` content specifically (not just noise) got counted in.
    assert stats_true["total_char_count"] - stats_unspecified["total_char_count"] >= 20


def test_context_populated_for_every_generator(tmp_path):
    generators = _run_minimal_build(tmp_path)

    assert generators
    for generator in generators:
        assert "pelican_stat_word_count" in generator.context
        assert "pelican_stat_trend_plot_html" in generator.context

    word_count = generators[0].context["pelican_stat_word_count"]
    assert word_count["post_count"] == 1

    # `pelican_stat_trend_plot_html` is a lazy object (see
    # `stat._LazyTrendPlotHtml`) that only produces real HTML once
    # stringified *during* `generate_output()` (i.e. while
    # `_ACCUMULATED_ARTICLES` is still populated). This assertion only
    # checks that the right kind of object was attached; the actual
    # rendered-HTML content (no `<html>` wrapper, no `cdn.plot.ly`) is
    # covered by `test_trend_plot_html_reflects_both_rounds_once_evaluated`,
    # which evaluates it at the correct point in the timeline instead of
    # after `.run()` (and this cache reset) has already completed.
    assert isinstance(generators[0].context["pelican_stat_trend_plot_html"], stat._LazyTrendPlotHtml)


def test_finalized_resets_cache_so_next_build_recomputes(tmp_path, monkeypatch):
    """`signals.finalized` fires at the end of every `Pelican.run()` and
    must clear the cache -- otherwise a long-running process (livereload)
    would keep serving the first build's stats forever."""
    # Freeze "now" so both builds compute identical `writing_years`; the
    # article content itself never changes between the two builds, so the
    # only source of non-determinism would be wall-clock time.
    monkeypatch.setattr(wordcount, "_now", lambda tz: datetime(2030, 1, 1, tzinfo=tz))

    first_generators = _run_minimal_build(tmp_path / "first")
    first_stats = first_generators[0].context["pelican_stat_word_count"]

    # `finalized` already fired at the end of `.run()` above. This is a
    # single, non-nested `Pelican.run()`, so accumulation depth unwinds
    # straight back to 0 and the cache resets.
    assert stat._CACHED_STATS is None
    assert stat._CACHED_TREND_HTML is None
    assert stat._ACCUMULATED_ARTICLES == []

    # The next full build must recompute (not reuse) -- same content still
    # produces an equal but distinct dict, proving it was recomputed rather
    # than served from a stale reference.
    second_generators = _run_minimal_build(tmp_path / "second")
    second_stats = second_generators[0].context["pelican_stat_word_count"]

    assert second_stats is not first_stats
    assert second_stats == first_stats


def test_reset_cache_for_testing_clears_cache():
    stat._CACHED_STATS = {"post_count": 1}
    stat._CACHED_TREND_HTML = "<div>fake</div>"
    stat._ACCUMULATED_ARTICLES.append("not a real article")
    stat._ACCUMULATION_DEPTH = 3

    stat._reset_cache_for_testing()

    assert stat._CACHED_STATS is None
    assert stat._CACHED_TREND_HTML is None
    assert stat._ACCUMULATED_ARTICLES == []
    assert stat._ACCUMULATION_DEPTH == 0


def test_two_rounds_accumulate_into_shared_post_count(tmp_path):
    """Regression test for plan.md Milestone A2 problem two: on a site with
    a nested `i18n_subsites` en subsite, `all_generators_finalized` fires
    twice per top-level `Pelican.run()` -- once for the primary build, once
    (synchronously, from inside the primary build's own `_get_writer()`)
    for the nested subsite build. Neither round's own `ArticlesGenerator.articles`
    is ever the full site (each has already been filtered to its own
    `DEFAULT_LANG`); `post_count` must be the SUM across both rounds, read
    from the SAME dict object both rounds attach to `context`."""
    round_1_generators = _generate_context_generators(tmp_path / "round_1", round_name="round_1")
    round_2_generators = _generate_context_generators(tmp_path / "round_2", round_name="round_2")

    stat._attach_word_count_stats(round_1_generators)  # simulates the primary round
    stat._attach_word_count_stats(round_2_generators)  # simulates the nested round

    stats_seen_by_round_1 = round_1_generators[0].context["pelican_stat_word_count"]
    stats_seen_by_round_2 = round_2_generators[0].context["pelican_stat_word_count"]

    # Same dict OBJECT for both rounds -- required so a page rendered from
    # round 1's context (the primary/zh page) and one rendered from round
    # 2's context (the nested/en page) both read the identical, fully
    # accumulated values.
    assert stats_seen_by_round_1 is stats_seen_by_round_2
    # Each round's own fixture has exactly 1 article; the accumulated total
    # must be the sum (2), not either round's own count (1) -- 2 is
    # unambiguously proof accumulation happened, not just "cache reuse".
    assert stats_seen_by_round_1["post_count"] == 2


def test_nested_finalized_does_not_reset_but_outermost_finalized_does(tmp_path):
    """`_ACCUMULATION_DEPTH` must track how many `all_generators_finalized`
    calls are still "open" (no matching `finalized` yet), and only reset
    the accumulator once it unwinds back to 0. A nested subsite's own
    `finalized` fires strictly before the primary build's own
    `generate_output()` has rendered anything -- resetting there would wipe
    the accumulator out from under the primary build's still-pending
    render. See `stat.py`'s module docstring for the source-verified
    signal-firing order this mirrors."""
    round_1_generators = _generate_context_generators(tmp_path / "round_1", round_name="round_1")
    round_2_generators = _generate_context_generators(tmp_path / "round_2", round_name="round_2")

    stat._attach_word_count_stats(round_1_generators)  # depth 0 -> 1 (primary round)
    stat._attach_word_count_stats(round_2_generators)  # depth 1 -> 2 (nested round)
    assert stat._ACCUMULATION_DEPTH == 2

    # Nested (en) subsite's own `finalized` -- fires BEFORE the primary
    # build's `generate_output()` in a real build. Must NOT reset.
    stat._reset_word_count_cache(None)
    assert stat._ACCUMULATION_DEPTH == 1
    assert stat._CACHED_STATS is not None
    assert stat._CACHED_STATS["post_count"] == 2
    assert stat._ACCUMULATED_ARTICLES != []

    # Primary build's own, outermost `finalized` -- the whole `Pelican.run()`
    # tree is done now. Must reset.
    stat._reset_word_count_cache(None)
    assert stat._ACCUMULATION_DEPTH == 0
    assert stat._CACHED_STATS is None
    assert stat._CACHED_TREND_HTML is None
    assert stat._ACCUMULATED_ARTICLES == []


def test_trend_plot_html_reflects_both_rounds_once_evaluated(tmp_path):
    """The lazy trend-plot object must reflect BOTH rounds' articles once
    stringified -- not whichever round happened to create it. Verified
    against the actual `plotly.graph_objects.Figure` data (exact), not by
    string-matching the rendered HTML (which embeds data as opaque JS)."""
    round_1_generators = _generate_context_generators(tmp_path / "round_1", round_name="round_1")
    round_2_generators = _generate_context_generators(tmp_path / "round_2", round_name="round_2")

    stat._attach_word_count_stats(round_1_generators)
    trend_html_obj = round_1_generators[0].context["pelican_stat_trend_plot_html"]
    assert len(stat._ACCUMULATED_ARTICLES) == 1  # only round 1 has accumulated so far

    stat._attach_word_count_stats(round_2_generators)
    assert len(stat._ACCUMULATED_ARTICLES) == 2  # both rounds accumulated now

    # Evaluate NOW, the same way a real template render would -- i.e. only
    # after both rounds have already accumulated (see `stat.py`'s module
    # docstring: `generate_output()` never runs before both rounds do).
    rendered = str(trend_html_obj)
    assert "cdn.plot.ly" not in rendered

    # Same object handed to round 2's context too, and evaluating it again
    # produces the same (already fully-accumulated) content.
    assert round_2_generators[0].context["pelican_stat_trend_plot_html"] is trend_html_obj

    articles_info = [stat._article_to_info_dict(a) for a in stat._ACCUMULATED_ARTICLES]
    figure = PelicanDataPlotter(articles_info)._build_figure()
    assert len(figure.data[0].x) == 2  # both accumulated articles, not just round 1's 1


def test_duplicate_source_path_articles_not_double_counted(tmp_path):
    """Regression test for plan.md Milestone C C-8: if the accumulator isn't
    reset between rounds (e.g. a crashed `livereload` rebuild left
    `_ACCUMULATION_DEPTH` stuck above 0, see `stat.py`'s "Known
    limitations"), re-accumulating the exact same batch of articles a second
    time must be a no-op, not a double-count."""
    generators = _generate_context_generators(tmp_path / "round_1", round_name="round_1")

    stat._attach_word_count_stats(generators)
    first_post_count = stat._CACHED_STATS["post_count"]
    assert first_post_count == 1

    # Simulate the accumulator never having been reset: feed the SAME
    # `Article` objects (same `source_path`) a second time.
    stat._attach_word_count_stats(generators)

    assert stat._CACHED_STATS["post_count"] == first_post_count
    assert len(stat._ACCUMULATED_ARTICLES) == 1


# --- Shortcode: `{% writing_stats %}` / `{% writing_stats compact %}` -----


def test_shortcode_preprocessor_restores_verbatim_text_on_adjacent_lines():
    """Regression test for the specific attr_list-eats-shortcode failure
    mode described in `_ShortcodePreserver`'s docstring: two shortcodes on
    adjacent lines (no blank line between) would otherwise merge into one
    paragraph, with the second `{% ... %}` misparsed as `attr_list`
    attributes instead of surviving verbatim. Runs standalone against
    `markdown.Markdown(...)` directly -- no Pelican build needed."""
    pattern = stat._build_shortcode_pattern("writing_stats")
    md = markdown.Markdown(extensions=["attr_list", stat._ShortcodePreserveExtension(pattern)])

    html = md.convert("{% writing_stats %}\n{% writing_stats compact %}")

    assert "{% writing_stats %}" in html
    assert "{% writing_stats compact %}" in html


def test_substitute_shortcode_html_replaces_literal_text(tmp_path):
    stat._CACHED_STATS = {
        "post_count": 42,
        "cjk_char_count": 100,
        "english_word_count": 20,
        "total_char_count": 500,
        "writing_years": 3.5,
        "average_chars_per_article": 11.9,
        "median_chars_per_article": 9.0,
    }
    try:
        output = tmp_path / "index.html"
        output.write_text('<div class="post-content">{% writing_stats %}</div>', encoding="utf-8")

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert "{% writing_stats %}" not in result
        # Full widget renders exactly the 5 "word" fields in `_WIDGET_FIELDS`.
        assert len(stat._WIDGET_FIELDS) == 5
        assert result.count('<dl class="pstat-card">') == 5
        for key in stat._WIDGET_FIELDS:
            assert f'<dd class="pstat-num">{stat._CACHED_STATS[key]}</dd>' in result, key
        # `post_count`/`writing_years` moved to pelican-heatmap's widget and
        # must NOT be rendered here.
        assert '<dd class="pstat-num">42</dd>' not in result
        assert '<dd class="pstat-num">3.5</dd>' not in result
    finally:
        stat._reset_cache_for_testing()


def test_substitute_shortcode_html_compact_variant_only_shows_compact_fields(tmp_path):
    stat._CACHED_STATS = {
        "post_count": 111,
        "cjk_char_count": 222,
        "english_word_count": 333,
        "total_char_count": 7,
        "writing_years": 444,
        "average_chars_per_article": 2.75,
    }
    try:
        output = tmp_path / "index.html"
        output.write_text("{% writing_stats compact %}", encoding="utf-8")

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert "{% writing_stats compact %}" not in result
        assert "pelican-stat-widget--compact" in result
        # Compact renders exactly `_COMPACT_WIDGET_FIELDS` (2 fields).
        assert len(stat._COMPACT_WIDGET_FIELDS) == 2
        assert result.count('<dl class="pstat-card">') == 2
        assert '<dd class="pstat-num">7</dd>' in result
        assert '<dd class="pstat-num">2.75</dd>' in result
        # compact variant must NOT surface fields outside
        # `_COMPACT_WIDGET_FIELDS` -- including `post_count`/`writing_years`,
        # which moved to pelican-heatmap's widget entirely.
        for leaked in (111, 222, 333, 444):
            assert f'<dd class="pstat-num">{leaked}</dd>' not in result
    finally:
        stat._reset_cache_for_testing()


def test_substitute_shortcode_html_dedupes_style_block_for_multiple_widgets_on_one_page(tmp_path):
    """A single rendered page can carry the shortcode more than once (e.g.
    a full widget mid-article and a compact one in a closing note). The
    `<style>` block must be emitted exactly once -- the CSS rules are
    page-scoped (`.pelican-stat-widget ...` selectors), so repeating them
    would only add dead bytes, not additional styling."""
    stat._CACHED_STATS = {
        "post_count": 1,
        "cjk_char_count": 2,
        "english_word_count": 3,
        "total_char_count": 4,
        "writing_years": 5,
        "average_chars_per_article": 6,
    }
    try:
        output = tmp_path / "index.html"
        output.write_text("{% writing_stats %}<p>middle</p>{% writing_stats compact %}", encoding="utf-8")

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert "{% writing_stats" not in result
        assert result.count("<style>") == 1
        # Both widget instances still rendered (first full, second compact).
        assert result.count('<dl class="pstat-card">') == len(stat._WIDGET_FIELDS) + len(
            stat._COMPACT_WIDGET_FIELDS
        )
        assert "pelican-stat-widget--compact" in result
    finally:
        stat._reset_cache_for_testing()


def test_render_widget_html_include_style_false_omits_style_block():
    html = stat._render_widget_html({"total_char_count": 1}, compact=True, include_style=False)
    assert "<style>" not in html
    assert "pstat-num" in html


def test_substitute_shortcode_html_unwraps_p_when_placeholder_is_sole_content(tmp_path):
    """Regression test for the real `main-blog` bug: a `{% writing_stats %}`
    written on its own line gets wrapped in `<p>...</p>` by Markdown (it
    doesn't know the placeholder is meant to become a block-level `<div>`).
    Substituting only the placeholder text would leave illegal
    `<p><div>...</div></p>` nesting -- the `<p>`/`</p>` must be dropped
    along with the placeholder when it's the paragraph's sole content."""
    stat._CACHED_STATS = {"total_char_count": 176, "average_chars_per_article": 88.0}
    try:
        output = tmp_path / "index.html"
        output.write_text("<p>{% writing_stats compact %}</p>", encoding="utf-8")

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert result.startswith('<div class="pelican-stat-widget pelican-stat-widget--compact">')
        assert result.endswith("</div>")
        assert "<p>" not in result
        assert "</p>" not in result
    finally:
        stat._reset_cache_for_testing()


def test_substitute_shortcode_html_unwraps_p_tolerating_surrounding_whitespace(tmp_path):
    """Markdown may emit a trailing newline before `</p>` -- the `<p>`
    un-nesting must still trigger, not just for the exact zero-whitespace
    case."""
    stat._CACHED_STATS = {"total_char_count": 1, "average_chars_per_article": 1}
    try:
        output = tmp_path / "index.html"
        output.write_text("<p>\n  {% writing_stats compact %}\n</p>", encoding="utf-8")

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert "<p>" not in result
        assert "</p>" not in result
    finally:
        stat._reset_cache_for_testing()


def test_substitute_shortcode_html_leaves_p_intact_for_inline_usage(tmp_path):
    """Accepted limitation, not a fix target: when the shortcode is written
    mid-sentence (other text still shares the `<p>`), the surrounding `<p>`
    is NOT unwrapped -- unwrapping it would break the sentence's other text.
    The substitution itself must still happen; only the (still-illegal,
    pre-existing) `<p>`-nesting is left as-is for this authoring pattern."""
    stat._CACHED_STATS = {"total_char_count": 1, "average_chars_per_article": 1}
    try:
        output = tmp_path / "index.html"
        output.write_text("<p>Some stats: {% writing_stats compact %} -- see above.</p>", encoding="utf-8")

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert result.startswith("<p>Some stats: ")
        assert result.endswith(" -- see above.</p>")
        assert '<div class="pelican-stat-widget pelican-stat-widget--compact">' in result
    finally:
        stat._reset_cache_for_testing()


def test_substitute_shortcode_html_unwraps_multiple_p_wrapped_widgets_on_one_page(tmp_path):
    """Two independent `<p>`-wrapped shortcode occurrences on the same page
    (the realistic `main-blog` pattern: full widget, then compact widget,
    each on its own line) must both be unwrapped, and still only carry one
    `<style>` block between them (dedup from the earlier fix)."""
    stat._CACHED_STATS = {"total_char_count": 5, "average_chars_per_article": 2}
    try:
        output = tmp_path / "index.html"
        output.write_text(
            "<p>{% writing_stats %}</p><p>middle text</p><p>{% writing_stats compact %}</p>",
            encoding="utf-8",
        )

        stat._substitute_shortcode_html(str(output), {})

        result = output.read_text(encoding="utf-8")
        assert "<p>middle text</p>" in result
        assert "<p><div" not in result
        assert "</div></p>" not in result
        assert result.count("<style>") == 1
        assert "pelican-stat-widget--compact" in result
    finally:
        stat._reset_cache_for_testing()


def test_substitute_shortcode_html_noop_when_shortcode_absent(tmp_path):
    output = tmp_path / "index.html"
    original = "<p>No shortcode here.</p>"
    output.write_text(original, encoding="utf-8")

    stat._substitute_shortcode_html(str(output), {})

    assert output.read_text(encoding="utf-8") == original


def test_substitute_shortcode_html_skips_non_html_files(tmp_path):
    output = tmp_path / "data.json"
    original = "{% writing_stats %}"
    output.write_text(original, encoding="utf-8")

    stat._substitute_shortcode_html(str(output), {})

    assert output.read_text(encoding="utf-8") == original


# --- i18n: locale label tables ----------------------------------------------


def test_resolve_locale_exact_match_case_insensitive():
    # Site metadata (`Lang: zh-tw`) is lowercase; the table key is `zh-TW`.
    assert stat._resolve_locale("zh-tw") == stat._LOCALES["zh-TW"]
    assert stat._resolve_locale("ZH-TW") == stat._LOCALES["zh-TW"]


def test_resolve_locale_unknown_lang_falls_back_to_en():
    assert stat._resolve_locale("fr") == stat._LOCALES["en"]
    # Bare "zh" (no region subtag) doesn't literally match the "zh-TW" key
    # or its own primary subtag ("zh-tw".split("-")[0] == "zh-tw"[:2]... no
    # -- "zh-TW".lower().split("-")[0] == "zh"), so this also documents the
    # same "no bare zh-only match" limitation `pelican-heatmap`'s JS lookup
    # has (see `pelican_heatmap.js:61-63`) -- both fall back to `en`.
    assert stat._resolve_locale("zh") == stat._LOCALES["en"]


def test_resolve_locale_merges_pelican_stat_labels_override():
    original_settings = stat._settings
    try:
        stat._settings = {"PELICAN_STAT_LABELS": {"zh-TW": {"post_count": "篇數"}}}
        resolved = stat._resolve_locale("zh-tw")
        assert resolved["post_count"] == "篇數"
        # Non-overridden fields keep the base locale's label.
        assert resolved["writing_years"] == stat._LOCALES["zh-TW"]["writing_years"]
    finally:
        stat._settings = original_settings


def test_resolve_lang_prefers_article_lang_over_default_lang():
    context = {"article": SimpleNamespace(lang="en"), "DEFAULT_LANG": "zh-tw"}
    assert stat._resolve_lang(context) == "en"


def test_resolve_lang_prefers_page_lang_when_no_article():
    context = {"page": SimpleNamespace(lang="zh-tw"), "DEFAULT_LANG": "en"}
    assert stat._resolve_lang(context) == "zh-tw"


def test_resolve_lang_falls_back_to_default_lang_when_no_content():
    assert stat._resolve_lang({"DEFAULT_LANG": "zh-tw"}) == "zh-tw"


def test_resolve_lang_falls_back_to_en_when_nothing_present():
    assert stat._resolve_lang({}) == "en"


def test_render_widget_html_renders_zh_tw_labels():
    html = stat._render_widget_html({"total_char_count": 1}, compact=True, lang="zh-TW")
    assert "總字元數" in html
    assert "Total Characters" not in html


def test_render_widget_html_renders_en_labels_by_default():
    html = stat._render_widget_html({"total_char_count": 1}, compact=True)
    assert "Total Characters" in html
    assert "總字元數" not in html


def test_render_widget_html_unknown_lang_falls_back_to_en_labels():
    html = stat._render_widget_html({"total_char_count": 1}, compact=True, lang="fr")
    assert "Total Characters" in html


def test_render_widget_html_formats_thousands_separator():
    html = stat._render_widget_html(
        {"total_char_count": 220918, "average_chars_per_article": 12.7}, compact=True
    )
    assert '<dd class="pstat-num">220,918</dd>' in html
    assert '<dd class="pstat-num">12.7</dd>' in html


def test_render_widget_html_full_variant_renders_median_label_zh_tw():
    html = stat._render_widget_html({"median_chars_per_article": 1268}, compact=False, lang="zh-TW")
    assert "中位數每篇字數" in html
    assert "Median Chars / Post" not in html


def test_render_widget_html_full_variant_renders_median_label_en():
    html = stat._render_widget_html({"median_chars_per_article": 1268}, compact=False, lang="en")
    assert "Median Chars / Post" in html
    assert "中位數每篇字數" not in html


def test_resolve_locale_has_median_label_for_every_locale():
    for locale_key in stat._LOCALES:
        assert "median_chars_per_article" in stat._LOCALES[locale_key]


def test_substitute_shortcode_html_uses_article_lang_for_labels(tmp_path):
    stat._CACHED_STATS = {
        "post_count": 42,
        "cjk_char_count": 100,
        "english_word_count": 20,
        "total_char_count": 500,
        "writing_years": 3.5,
        "average_chars_per_article": 11.9,
    }
    try:
        output = tmp_path / "zh-article.html"
        output.write_text("{% writing_stats %}", encoding="utf-8")

        stat._substitute_shortcode_html(
            str(output), {"article": SimpleNamespace(lang="zh-tw"), "DEFAULT_LANG": "en"}
        )

        result = output.read_text(encoding="utf-8")
        assert "總字元數" in result
        assert "Total Characters" not in result
    finally:
        stat._reset_cache_for_testing()


def test_real_build_renders_locale_correct_labels_per_article_lang(tmp_path):
    """End-to-end: a real `Pelican.run()` over two articles with different
    `Lang:` metadata, one differing from the site's own `DEFAULT_LANG`, must
    render each article's `{% writing_stats %}` widget with that article's
    own language's labels -- not the site default's.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "zh_article.md").write_text(
        "Title: zh title\n"
        "Date: 2021-01-19 16:12\n"
        "Category: Testing\n"
        "Lang: zh-tw\n"
        "Slug: zh-article\n"
        "\n"
        "content with the shortcode below.\n"
        "\n"
        "{% writing_stats %}\n",
        encoding="utf-8",
    )
    (content_dir / "en_article.md").write_text(
        "Title: en title\n"
        "Date: 2021-01-20 16:12\n"
        "Category: Testing\n"
        "Lang: en\n"
        "Slug: en-article\n"
        "\n"
        "content with the shortcode below.\n"
        "\n"
        "{% writing_stats %}\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "output"
    settings = pelican.read_settings("tests/sample_pelican_project/pelicanconf.py")
    settings["PLUGINS"] = ["pelican.plugins.stat"]
    settings["PATH"] = str(content_dir)
    settings["OUTPUT_PATH"] = str(output_path)
    # Site default deliberately differs from the zh article's own `Lang:`,
    # so a pass here proves per-article `.lang` wins over `DEFAULT_LANG`.
    settings["DEFAULT_LANG"] = "en"

    pelican_instance = pelican.Pelican(settings)
    pelican_instance.run()

    # `ARTICLE_LANG_SAVE_AS` (default `{slug}-{lang}.html`) applies whenever
    # an article's own `Lang:` differs from `DEFAULT_LANG` -- verified by
    # inspecting the actual `output_path` contents produced by this exact
    # build; the zh article (Lang: zh-tw, site default: en) lands at
    # `zh-article-zh-tw.html`, while the en article (Lang: en, matching the
    # site default) uses the plain `{slug}.html` form.
    zh_html = (output_path / "zh-article-zh-tw.html").read_text(encoding="utf-8")
    en_html = (output_path / "en-article.html").read_text(encoding="utf-8")

    assert "總字元數" in zh_html
    assert "Total Characters" not in zh_html
    assert "Total Characters" in en_html
    assert "總字元數" not in en_html
