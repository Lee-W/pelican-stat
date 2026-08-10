from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import markdown as _markdown

from pelican import Pelican, signals  # type: ignore[attr-defined]
from pelican.contents import Article
from pelican.generators import ArticlesGenerator, Generator

from .plotter import PelicanDataPlotter
from .wordcount import ArticleWordCountAggregator

# --- Why two-round accumulation (not "trust the first call" or "rebuild
# from disk") -------------------------------------------------------------
#
# Two prior designs were tried for this site (a primary zh-tw build with a
# nested `i18n_subsites` en subsite) and both were wrong:
#
#   1. Trust `articles_generator.articles` on the first
#      `all_generators_finalized` call. Wrong: by the time that signal
#      fires, `i18n_subsites` has already filtered `.articles` down to the
#      *current* build's `DEFAULT_LANG` (298 zh on the primary call, 24 en
#      on the nested call) -- neither call ever sees the full site.
#   2. Rebuild a fresh, plugin-free `ArticlesGenerator` straight from disk
#      (`PLUGINS=[]`). Also wrong: `i18n_subsites` connects its filter via
#      `signals.article_generator_pretaxonomy.connect(handler)` with
#      blinker's default `sender=ANY`, so that handler intercepts *any*
#      `ArticlesGenerator` built anywhere in the same process -- including
#      a freshly-built one with `PLUGINS=[]`. Clearing `PLUGINS` only stops
#      *new* `register()` calls; it does not disconnect handlers a live
#      process has already registered.
#
# What actually works: accumulate across the exact `all_generators_finalized`
# calls Pelican makes for this site (confirmed by reading
# `pelican.Pelican.run()`/`_get_writer()`, not assumed):
#
#   primary (zh) generate_context()      -> filtered to 298 articles
#   primary all_generators_finalized     -> round 1: +298
#     primary._get_writer()
#       -> i18n_subsites' `get_writer` handler synchronously runs a nested
#          `Pelican.run()` for the en subsite:
#          nested (en) generate_context()    -> filtered to 24 articles
#          nested all_generators_finalized   -> round 2: +24 (total: 322)
#          nested generate_output()          -> EN PAGES RENDER HERE
#          nested finalized                  -> depth 2 -> 1, do NOT reset
#     primary generate_output()          -> ZH PAGES RENDER HERE
#   primary finalized                    -> depth 1 -> 0, reset here
#
# Both `all_generators_finalized` calls (both rounds) happen before EITHER
# site's `generate_output()` renders a single page, so accumulating into a
# shared mutable object and reading it at render time is safe -- both the
# en and the zh pages read the same, fully-accumulated (322) data.
#
# --- Known limitations -----------------------------------------------------
#
# - `_ACCUMULATED_ARTICLES.extend(...)` used to assume each round's articles
#   were disjoint from every other round's, with no dedup key to guard
#   against a violation of that assumption. As of Milestone C (plan.md C-8),
#   this is fixed: every article is keyed by `article.source_path` in
#   `_ACCUMULATED_SOURCE_PATHS` before being appended, so re-accumulating an
#   already-seen `source_path` is a silent no-op instead of a double-count.
#   This also fixes the previously-documented crash/livereload risk below --
#   even if `_ACCUMULATION_DEPTH` gets stuck above 0 after a crashed round
#   (Pelican core never sends that round's matching `finalized` when
#   `generate_output()` raises mid-way, see `_reset_word_count_cache()`
#   below) and a long-running `livereload`/`--autoreload` process
#   re-accumulates the same articles on the next rebuild, the dedup key
#   prevents the numbers from inflating.
# - Residual edge case the dedup key does NOT cover: if the SAME
#   `source_path` is accumulated twice with two *different* `Article`
#   objects representing stale vs. fresh content (e.g. a file edited between
#   a crashed round and the next rebuild, with the crashed round's object
#   still sitting in `_ACCUMULATED_ARTICLES`), the first-seen object wins
#   and the second is dropped -- stats would reflect the stale content until
#   the process restarts. Not mitigated (same "no `finally`ish hook exposed
#   at this signal boundary" constraint as above); flagged as a known,
#   accepted risk rather than fixed, per plan.md Milestone A2's existing
#   convention of documenting rather than silently working around this
#   class of edge case (see `wordcount.py`'s own "Known limitations").
_CACHED_STATS: dict[str, int | float] | None = None
_CACHED_TREND_HTML: _LazyTrendPlotHtml | None = None
_ACCUMULATED_ARTICLES: list[Article] = []
_ACCUMULATED_SOURCE_PATHS: set[str] = (
    set()
)  # dedup key for `_ACCUMULATED_ARTICLES`, see "Known limitations" above
_ACCUMULATION_DEPTH = 0


def _article_to_info_dict(article: Article) -> dict[str, str | int]:
    """Convert an Article into the dict shape `PelicanDataPlotter` expects.

    Mirrors `PelicanArticleDataCollector.extract_articles_info()`'s field
    format so `PelicanDataPlotter` can be fed the same shape regardless of
    whether the caller is the CLI or this plugin. This module intentionally
    does not import `PelicanArticleDataCollector` (CLI-only, rebuilds a
    Pelican instance) to avoid rerunning that logic inside an already
    running build.
    """
    return {
        "timestamp": article.date.timestamp(),
        "category": article.category.name,
        "authors": [author.name for author in article.authors],  # type: ignore
        "reader": article.reader,
        "status": article.status,
        "tags": [tag.name for tag in article.tags],  # type: ignore
        "timezone": str(article.timezone),
        "title": article.title,
    }


class _LazyTrendPlotHtml:
    """Renders the trend-plot HTML lazily, the first time it's stringified.

    A plain `str` can't be mutated in place. If the primary (zh) round
    rendered its trend-plot HTML into a finished string and stored that in
    `context` right away, the nested en round's 24 articles would never be
    able to get added to it -- the zh page would render a plot missing a
    quarter of the site. Deferring the actual `PelicanDataPlotter` call
    until Jinja stringifies this object works around that: template
    rendering (`generate_output()`) only ever happens *after* both
    `all_generators_finalized` rounds have already run (see the module
    docstring above), so by the time `__str__`/`__html__` is actually
    called, `_ACCUMULATED_ARTICLES` already holds the full, accumulated
    site -- for both the en and the zh page.
    """

    def __html__(self) -> str:
        # Implementing `__html__` is MarkupSafe/Jinja2's own "this object is
        # already-safe markup" hook (`markupsafe.escape()` calls it when
        # present), so `{{ pelican_stat_trend_plot_html }}` would render
        # correctly even without an explicit `| safe` filter. The
        # `templates/stats.html` in `main-blog` already applies `| safe`
        # explicitly, so this is a belt-and-suspenders addition, not load
        # bearing on its own.
        return PelicanDataPlotter(
            [_article_to_info_dict(a) for a in _ACCUMULATED_ARTICLES]
        ).render_trend_plot_html()

    def __str__(self) -> str:
        return self.__html__()

    def __bool__(self) -> bool:
        return bool(_ACCUMULATED_ARTICLES)


def _attach_word_count_stats(generators: list[Generator]) -> None:
    global _CACHED_STATS, _CACHED_TREND_HTML, _ACCUMULATION_DEPTH

    _ACCUMULATION_DEPTH += 1

    articles_generator = next((g for g in generators if isinstance(g, ArticlesGenerator)), None)
    if articles_generator is not None:
        # Dedup by `source_path`: guards against double-counting when the
        # same article shows up in more than one round (see the
        # `_ACCUMULATED_SOURCE_PATHS` "Known limitations" note above).
        new_articles = [
            article
            for article in articles_generator.articles
            if article.source_path not in _ACCUMULATED_SOURCE_PATHS
        ]
        for article in new_articles:
            _ACCUMULATED_SOURCE_PATHS.add(article.source_path)
        _ACCUMULATED_ARTICLES.extend(new_articles)

        if _CACHED_STATS is None:
            # First round of this `Pelican.run()`: create the dict object
            # once. Every later round (and every generator's `context`)
            # keeps holding a reference to this exact same object -- see
            # the `.clear()`/`.update()` below, never a re-assignment.
            _CACHED_STATS = {}
            _CACHED_TREND_HTML = _LazyTrendPlotHtml()

        # Recompute from the full accumulation-so-far and mutate the
        # existing dict's *contents* in place (not `_CACHED_STATS = {...}`)
        # -- every generator across every round already has a reference to
        # this object in its `context`; reassigning the name here would
        # leave those earlier references stale. Recomputing via the
        # existing, already-tested `ArticleWordCountAggregator` (rather
        # than hand-summing individual fields) is deliberate: fields like
        # `writing_years` (earliest article to *now*) and
        # `average_chars_per_article` (total / post_count) are NOT
        # additive across rounds -- summing them field-by-field would give
        # a wrong answer. Recomputing from the full article list every
        # round keeps every field correct using logic that already has its
        # own test coverage, at the cost of a little redundant re-counting
        # of earlier rounds' articles (cheap: in-memory string counting
        # over at most ~322 articles, not disk I/O).
        # `PELICAN_STAT_INCLUDE_CODE_BLOCKS` (default `False`, matching
        # `ArticleWordCountAggregator`'s own default): read here, from the
        # module-level `_settings` populated by `_initialize_shortcode` at
        # `signals.initialized` (which always fires before
        # `all_generators_finalized`, same ordering `PELICAN_STAT_LABELS`
        # already relies on below), and passed in as a plain bool --
        # `wordcount.py` itself never touches Pelican settings, see
        # `ArticleWordCountAggregator`'s own docstring for why that
        # boundary is kept.
        include_block_code = bool(_settings.get("PELICAN_STAT_INCLUDE_CODE_BLOCKS", False))
        _CACHED_STATS.clear()
        _CACHED_STATS.update(
            ArticleWordCountAggregator(_ACCUMULATED_ARTICLES, include_block_code=include_block_code).compute()
        )

    for generator in generators:
        generator.context["pelican_stat_word_count"] = _CACHED_STATS
        generator.context["pelican_stat_trend_plot_html"] = _CACHED_TREND_HTML


def _reset_word_count_cache(pelican_instance: Pelican | None) -> None:
    """Reset the module-level accumulator once the *outermost* `Pelican.run()` finishes.

    `signals.finalized` fires once per `Pelican.run()` call, including once
    for the nested en subsite build -- and that nested `finalized` fires
    *before* the outer/primary site's own `generate_output()` has rendered
    a single zh page yet (see the module docstring's timeline). Resetting
    on that nested `finalized` would wipe the accumulator out from under
    the primary build's still-pending render.

    `_ACCUMULATION_DEPTH` tracks how many `all_generators_finalized` calls
    (rounds) are still "open" (haven't had their matching `finalized` yet).
    Only reset once it unwinds back to 0 -- i.e. the outermost, last
    `finalized` of this whole `Pelican.run()` tree. This also still solves
    the original problem this cache-reset existed for: a long-running
    process (`livereload`/`--autoreload`) would otherwise keep serving the
    first build's stats forever; the *next* full `Pelican.run()` still
    starts from a clean accumulator.
    """
    global _CACHED_STATS, _CACHED_TREND_HTML, _ACCUMULATION_DEPTH

    _ACCUMULATION_DEPTH -= 1
    if _ACCUMULATION_DEPTH > 0:
        return

    _ACCUMULATION_DEPTH = 0  # defensive: never let depth go negative
    _ACCUMULATED_ARTICLES.clear()
    _ACCUMULATED_SOURCE_PATHS.clear()
    _CACHED_STATS = None
    _CACHED_TREND_HTML = None


def _reset_cache_for_testing() -> None:
    """Unconditionally reset the module-level cache. Test-only helper, not part of the public API.

    Deliberately does NOT go through `_reset_word_count_cache()` -- that
    function only resets once `_ACCUMULATION_DEPTH` has unwound to 0, which
    is the wrong semantics for "wipe the slate clean before this test".
    """
    global _CACHED_STATS, _CACHED_TREND_HTML, _ACCUMULATION_DEPTH
    _ACCUMULATION_DEPTH = 0
    _ACCUMULATED_ARTICLES.clear()
    _ACCUMULATED_SOURCE_PATHS.clear()
    _CACHED_STATS = None
    _CACHED_TREND_HTML = None


# --- Shortcode: `{% writing_stats %}` / `{% writing_stats compact %}` -----
#
# Two-phase design (plan.md Milestone C, design judgment 4):
#
#   1. Protect: a Markdown Preprocessor (priority 25, same technique as
#      pelican-osm's `_ShortcodePreserver`) stashes the shortcode's literal
#      text into `md.htmlStash` before any other extension (notably
#      `attr_list`) can mangle it. Markdown restores it verbatim into
#      `article._content`/`page._content` once conversion finishes.
#   2. Replace: unlike osm/tabular (which substitute at
#      `signals.content_object_init`, long before word-count stats exist),
#      the actual substitution happens at `signals.content_written` -- after
#      the HTML file has already been rendered and written to disk (see
#      `pelican.writers.Writer.write_file()`: `template.render()`, then the
#      write, THEN `content_written` is sent). By that point both
#      `all_generators_finalized` rounds have always already run (same
#      timeline as the module docstring above), so `_ACCUMULATED_ARTICLES`/
#      `_CACHED_STATS` are guaranteed complete. This mirrors this repo's
#      sibling convention in `main-blog/plugins/image_markup.py`: read the
#      just-written file back, find-and-replace, write it back.
#
#   Known limitation: `_substitute_shortcode_html`'s `pattern.sub(...)` (see
#   below) is a blind string replacement over the *entire* rendered HTML
#   file -- it cannot tell a real `{% writing_stats %}` call apart from the
#   same literal text sitting inside a fenced code block or inline code
#   span (e.g. a tutorial post showing `` `{% writing_stats %}` `` as an
#   example of the syntax). Such an occurrence gets replaced too, producing
#   invalid nested markup: `<code>...<div class="pelican-stat-widget">
#   ...</div>...</code>`. Confirmed with a standalone repro during the
#   Milestone C review. Not fixed here -- a fix would need Markdown-stage
#   code-block/code-span detection to exempt shortcode text that landed
#   inside a code token, which is out of scope for this shortcode and would
#   make its behavior diverge from every other shortcode in this family
#   that shares this same whole-file substitution technique and therefore
#   the same limitation, e.g. pelican-osm's `{% place %}`
#   (`osm.py`'s `_ShortcodePreserver`, `osm.py:1587-1608`, plus its own
#   `_process_content` substitution step) and pelican-tabular's shortcode.
DEFAULT_SHORTCODE = "writing_stats"

_settings: dict[str, Any] = {}


def _build_shortcode_pattern(shortcode: str) -> re.Pattern[str]:
    """Match `{% <shortcode> %}` or `{% <shortcode> <arg> %}` (e.g. `compact`).

    Unlike osm/tabular's shortcodes (which always require at least one
    argument), `writing_stats` has exactly one site-wide dataset -- there's
    no "which one" to select -- so the argument is optional.
    """
    return re.compile(r"\{%\s*" + re.escape(shortcode) + r"(?:\s+(\S+))?\s*%\}")


def _build_p_wrapped_shortcode_pattern(shortcode: str) -> re.Pattern[str]:
    """Match a shortcode that is the *sole* content of a `<p>...</p>`.

    A `{% writing_stats %}` written on its own line is, to Markdown, just
    paragraph text (the stashed placeholder is opaque to Markdown -- see
    `_ShortcodePreserver`) -- so it gets wrapped in `<p>...</p>` like any
    other standalone line. `_substitute_shortcode_html` replaces that
    placeholder text with a `<div class="pelican-stat-widget">...</div>`,
    a block-level element -- if the surrounding `<p>` is left in place,
    the result is `<p><div>...</div></p>`, which is illegal HTML (`<div>`
    cannot be a descendant of `<p>`; browsers implicitly close the `<p>`
    right before the `<div>`, leaving a stray `</p>` in the parsed DOM,
    which was observed in a real `main-blog` build, see plan.md's bug
    report). Reusing `_build_shortcode_pattern`'s inner text as a group
    (`(?:\\s+(\\S+))?` still lands in `match.group(1)`, so callers built
    around `match.group(1)` being the compact/full variant continue to
    work unchanged for matches from this pattern too) wrapped in
    `<p>\\s*...\\s*</p>` matches only when the shortcode is the paragraph's
    *entire* content (mere whitespace/newlines on either side are still
    allowed, e.g. Markdown emitting a trailing newline before `</p>`).

    Deliberately does NOT match `<P>`/`<p ...>` variants: Python-Markdown's
    own HTML block renderer only ever emits lowercase, attribute-less
    `<p>` for a plain paragraph (verified by reading this repo's own
    rendered test fixtures/output -- nothing in this codebase's Markdown
    pipeline adds attributes to bare paragraph tags), so a case-insensitive
    or attribute-tolerant match would only add complexity for inputs this
    pipeline never actually produces.

    Inline usage (the shortcode written mid-sentence, with other text
    still inside the same `<p>`) never matches this pattern -- the `<p>`
    is not swallowed in that case, and the caller falls back to
    `_build_shortcode_pattern`'s plain substitution, which still produces
    `<p>text<div>...</div>text</p>` (still illegal HTML, but an authoring
    choice outside this fix's scope -- see `_substitute_shortcode_html`'s
    docstring for the accepted-limitation note).
    """
    inner = r"\{%\s*" + re.escape(shortcode) + r"(?:\s+(\S+))?\s*%\}"
    return re.compile(r"<p>\s*" + inner + r"\s*</p>")


class _ShortcodePreserver(_markdown.preprocessors.Preprocessor):  # type: ignore[misc]
    """Stash the shortcode's literal text via `htmlStash` before any other
    Markdown extension (notably `attr_list`) can touch it. See the module
    comment above this class for the full two-phase design rationale.
    """

    def __init__(self, md: Any, pattern: re.Pattern[str]) -> None:
        super().__init__(md)
        self._pattern = pattern

    def run(self, lines: list[str]) -> list[str]:
        text = "\n".join(lines)
        text = self._pattern.sub(lambda m: self.md.htmlStash.store(m.group(0)), text)
        return text.split("\n")


class _ShortcodePreserveExtension(_markdown.Extension):  # type: ignore[misc]
    def __init__(self, pattern: re.Pattern[str]) -> None:
        super().__init__()
        self._pattern = pattern

    def extendMarkdown(self, md: Any) -> None:
        # Priority 25: after `normalize_whitespace` (30, which would
        # otherwise strip the STX/ETX control chars `htmlStash` relies on)
        # and before `html_block`/`attr_list` (20 and lower) -- mirrors
        # pelican-osm's `_ShortcodePreserveExtension`.
        md.preprocessors.register(
            _ShortcodePreserver(md, self._pattern),
            "pelican_stat_shortcode_preserve",
            25,
        )


def _register_markdown_extension(settings: dict[str, Any]) -> None:
    """Append the shortcode-preserving Markdown extension to `MARKDOWN`.

    Idempotent so repeated `initialized` signals (e.g. the nested en subsite
    rebuild) don't stack duplicate copies of the extension.
    """
    md_settings = settings.setdefault("MARKDOWN", {})
    md_settings.setdefault("extensions", [])
    extensions = md_settings["extensions"]

    if any(isinstance(e, _ShortcodePreserveExtension) for e in extensions):
        return

    shortcode = settings.get("PELICAN_STAT_SHORTCODE", DEFAULT_SHORTCODE)
    extensions.append(_ShortcodePreserveExtension(_build_shortcode_pattern(shortcode)))


def _initialize_shortcode(pelican_obj: Pelican) -> None:
    global _settings
    _settings = pelican_obj.settings
    _register_markdown_extension(_settings)


# --- Widget CSS: visually matched to `pelican-heatmap`'s `.hm-stat-card`
# family (`pelican_heatmap.css:96-131`), because on this site's `about` page
# the two widgets sit right next to each other and get read as one group --
# see plan.md Milestone C-9. `pelican-stat` still cannot *depend* on
# `pelican-heatmap` (separately-installable package; a site may have this
# plugin without that one), so nothing here references `--hm-*` custom
# properties -- this widget defines its own `--pstat-*` set, tuned to the
# same values as heatmap's `--hm-*` defaults so the two line up when both
# are installed, but fully self-sufficient when only this one is.
#
# Dark mode uses the same feature-query technique as heatmap
# (`pelican_heatmap.css:77-94`): redefine the `--pstat-*` custom properties
# inside `@supports (color: light-dark(white, black))`, using the
# `light-dark()` CSS function for the actual color pick.
#
# `color-scheme` -- decided against forcing `light dark` on the widget
# (2nd design pass; strict review caught this). `color-scheme` is an
# *inherited* property: a value declared directly on `.pelican-stat-widget`
# always wins over whatever an ancestor computed, regardless of that
# ancestor's own specificity/origin (inheritance isn't a cascade
# competition -- any direct declaration on the element always wins). attila
# does BOTH of these, at different times (confirmed by reading the actually
# *installed* theme, not just its source repo -- see the attila-audit note
# below for why that distinction mattered):
#   - No saved preference: only the `<meta name="color-scheme"
#     content="light dark">` tag applies (equivalent to `color-scheme:
#     light dark` on the document element) -- OS preference wins.
#   - Saved preference (reader clicked attila's own light/dark toggle):
#     `script.js` sets `html.style.colorScheme = "dark"` (or `"light"`) as
#     an *inline* style on `<html>` -- a single forced value, not `light
#     dark` (confirmed: `attila/static/js/script.js:163-177`, installed
#     copy at `.venv/lib/.../pelican/themes/attila/static/js/script.js`).
#   Forcing `color-scheme: light dark` on this widget would make it ignore
#   that second case entirely -- a reader who manually flips to dark (while
#   their OS is light, or vice versa) would see every OTHER element on the
#   page respect their click except this widget, which would keep following
#   the OS instead. That's a worse, more visibly-broken failure mode than
#   the alternative below.
#   Chose `color-scheme: inherit` instead (this is actually a no-op vs. not
#   declaring the property at all, since inheritance is what a browser does
#   by default for this property anyway -- written explicitly so the
#   decision is visible in a diff, not just an absence). Trade-off, stated
#   plainly because there is no known pure-CSS way to have both at once (no
#   "inherit if an ancestor set something, else use my own value" construct
#   exists for a standard CSS property -- `var()` fallback only works for
#   custom properties, and inheritance itself doesn't expose "was this
#   explicitly set by someone" for a conditional check):
#     - On a host that already manages `color-scheme` somewhere in the
#       ancestor chain (attila does, via the meta tag and/or the toggle) --
#       this widget now correctly follows both the OS default AND a manual
#       toggle, matching every other element on the page.
#     - On a *bare* host with no theme-level `color-scheme` handling at all
#       (this widget installed standalone, no attila, no equivalent) --
#       `color-scheme` stays at its initial value `normal`, so
#       `light-dark()` always resolves to the light branch: the widget
#       renders correctly, just without a dark variant, until the host
#       adds its own `color-scheme` handling. Judged an acceptable
#       degradation (still fully legible, just not dark-mode-aware) versus
#       actively fighting a reader's explicit in-page action on every real
#       theme that does the sensible thing.
#     - This also makes `pelican-stat` consistent with `pelican-heatmap`'s
#       own widget on this exact axis: heatmap never sets `color-scheme`
#       itself either (re-confirmed: no such declaration anywhere in
#       `pelican_heatmap.css`) -- `inherit` was the odd widget out, not the
#       norm, among this repo family's own siblings.
#
# --- attila audit (strict-review should-fix #1): every `dl`/`dt`/`dd`-
# touching rule in the *actually installed* attila stylesheet -----------
#
# Read from `.venv/lib/python3.14/site-packages/pelican/themes/attila/
# static/css/style.css` (the copy pelican actually renders with for this
# build, fetched from attila's git source per `main-blog/pyproject.toml`'s
# `[tool.uv.sources]`) -- there is exactly one CSS file in that theme's
# `static/css/`, so this is the complete surface, not a sample:
#
#   style.css:824-828 `.post-content dl { font-family: var(--font-primary);
#     margin: 0 0 4rem; padding-inline-start: 30px; }`
#     -> margin/padding: already beaten by `.pstat-card`'s own `margin:0`
#        + its own `padding` declaration below -- `.pelican-stat-widget
#        .pstat-card` has 2 classes (specificity 0,2,0) vs. attila's 1
#        class + 1 type selector (0,1,1); logical (`padding-inline-start`) and
#        physical (`padding-left`) properties resolve to the same
#        underlying box side, so the physical shorthand here still wins
#        the cascade for that side despite attila's logical spelling.
#     -> font-family: NOT overridden, deliberately -- this just makes the
#        widget's text use the same body font as the rest of the article
#        (exactly what heatmap's widget also does, by never setting
#        font-family itself either), not a visual defect.
#   style.css:830-837 `.post-content dl dt { font-weight:500; font-
#     size:.75em; line-height:1.25em; font-weight:700 (2nd decl wins);
#     margin-bottom:.33334em; font-family }`
#     -> font-size/line-height/margin: already beaten by `.pstat-label`'s
#        own declarations (same 0,2,0-vs-0,1,2 specificity math as above).
#     -> font-weight:700 -- THIS is the bug strict-review caught: `.pstat-
#        label` never declared `font-weight` at all, so with no competing
#        declaration on the widget's own rule, attila's is the only one
#        that applies (specificity only decides between rules that BOTH
#        declare the same property) -- labels render bold instead of the
#        intended plain weight. Fixed: `.pstat-label` now explicitly
#        declares `font-weight:400`.
#   style.css:839-846 `.post-content dl dt:before { content:"";
#     position:absolute; width:1em; height:2px; margin-inline-start:-30px;
#     margin-top:.5em; background:var(--color-primary) }`
#     -> the decorative dash strict-review flagged. Same "never declared,
#        so attila's is the only rule" issue as font-weight. Fixed: added
#        `.pstat-label::before{content:none}` -- `content:none` removes
#        the pseudo-element's generated box entirely (not just makes it
#        invisible), so `position`/`background`/etc. on it become moot.
#   style.css:849-851 `.post-content dl dd { margin-inline-start:0;
#     margin-bottom:1em }`
#     -> already beaten by `.pstat-num`'s own `margin:0` (same specificity
#        math as the `dl` rule above).
#   style.css:4047-4048 `.post-content > dl > dt { margin-top:20px }`
#     -> does NOT apply: `>` requires `dl` to be a *direct* child of
#        `.post-content`. Confirmed via a real `main-blog` rebuild's actual
#        DOM: `.post-content` (a `<section>`) -> `.pelican-stat-widget`
#        (`<div>`, direct child) -> `.pstat-card` (`<dl>`, grandchild, NOT
#        a direct child of `.post-content`) -- the widget's own wrapper
#        `<div>` breaks the direct-child chain this selector requires.
#   style.css:4372-4374 `.post-content dl { font-family: var(--font-
#     primary) }` -- exact duplicate of the font-family half of the
#     824-828 rule (different line, same selector/property/value); same
#     "deliberately not overridden" judgment as above.
#
# No bare (unscoped) `dl`/`dt`/`dd` element-selector rules exist anywhere
# in this stylesheet (checked separately -- attila's only CSS file has no
# reset/normalize section touching these tags), and this is the theme's
# *only* stylesheet (no separate print/dark/editor CSS file), so the above
# is the complete set, not a sample of it.
#
# --- Sizing: deliberately smaller than heatmap's `.hm-stat-num`/`.hm-stat-
# label` (user feedback, 3rd design pass) -----------------------------------
#
# The first pass matched heatmap's numbers 1:1 (`34px`/`17px`, same as
# `.hm-stat-num`/`.hm-stat-label`) on the theory that visual parity would
# read as "one family". User feedback: on the actual `about` page, heatmap
# (a calendar grid -- much more visual real estate, the actual navigable
# widget) is the protagonist and this widget's numbers are supporting detail
# -- equal type size made them compete for the same visual weight instead of
# reading as primary/secondary. Sized down a clear step, not a nudge:
#   --pstat-num:   34px -> 24px (~71% of heatmap's number -- still a clear
#                  headline figure, but unmistakably subordinate)
#   --pstat-label: 17px -> 13px (~76% of heatmap's label)
#   card padding:  1.2rem 1.5rem -> .8rem 1rem (scaled down with the type,
#                  so the card doesn't end up with the old amount of empty
#                  space around now-smaller text)
#   card min/max-width: 100/220px -> 80/170px (same reasoning -- a card
#                  sized for 34px numbers looks empty around 24px ones)
# Net visual relationship when both widgets sit on the same page: heatmap's
# grid + its own `34px` stat numbers still read as the primary, larger-type
# element; this widget's `24px`/`13px` cards read as a smaller, secondary
# summary row underneath it -- distinct type scale, same card language
# (rounded corners, card background, numbers-over-labels), so they still
# read as one family, just no longer competing for the same rank in it.
#
# --- 5th card (median_chars_per_article) fit check, no CSS change made ----
#
# `.pstat-card`'s `flex:1 1 80px` means the row only wraps once the sum of
# every card's 80px min-width plus the `.9rem` (14.4px) gaps between them
# exceeds the container's width. Five cards: 5*80 + 4*14.4 = 457.6px. This
# site's article body (`attila`'s installed `style.css:4242`,
# `.post-content`-ancestor container) caps at `868px` (~820px content +
# padding) -- comfortably above 457.6px, so on a normal reading-width
# viewport all five cards stay on one row; with the container's actual
# ~820px available, each card grows toward (but doesn't hit) its
# `max-width:170px` ceiling, so they read as evenly-sized, not cramped.
# On a narrow phone viewport the row was already going to wrap via
# `flex-wrap:wrap` with 4 cards too (existing, pre-this-change behavior);
# a 5th card just means the wrap now reliably kicks in below ~458px
# instead of ~368px -- same graceful multi-row fallback, not a new failure
# mode. Conclusion: no `min-width`/`max-width`/`gap` change needed.
_WIDGET_STYLE = """<style>
/* Customizable classes:
     .pelican-stat-widget           -- outer wrapper (flex row of cards)
     .pelican-stat-widget--compact  -- modifier for the compact widget variant
     .pstat-card                    -- one card per stat (was a bare <dl>)
     .pstat-num                     -- large number (was a bare <dd>)
     .pstat-label                   -- label under the number (was a bare <dt>)
   CSS custom properties (override with a more specific `.pelican-stat-widget{...}` rule):
     --pstat-card-bg, --pstat-text-num, --pstat-text-muted */
.pelican-stat-widget{--pstat-card-bg:#f0ede8;--pstat-text-num:#1a1a1a;--pstat-text-muted:#888;
color-scheme:inherit;display:flex;flex-wrap:wrap;gap:.9rem;margin:1rem 0}
@supports (color: light-dark(white, black)){
.pelican-stat-widget{--pstat-card-bg:light-dark(#f0ede8,#242420);
--pstat-text-num:light-dark(#1a1a1a,#f0ede8);--pstat-text-muted:light-dark(#888,#bbb)}}
.pelican-stat-widget .pstat-card{background:var(--pstat-card-bg);border-radius:10px;
padding:.8rem 1rem;margin:0;display:flex;flex-direction:column-reverse;align-items:center;
gap:.3rem;flex:1 1 80px;min-width:80px;max-width:170px}
.pelican-stat-widget .pstat-num{font-size:24px;font-weight:700;color:var(--pstat-text-num);
line-height:1;margin:0}
.pelican-stat-widget .pstat-label{font-size:13px;font-weight:400;color:var(--pstat-text-muted);
letter-spacing:.03em;text-align:center;line-height:1.4;margin:0}
.pelican-stat-widget .pstat-label:before{content:none}
</style>"""

# Field order for each variant. Full: the five "word" fields this widget is
# responsible for -- `median_chars_per_article` was added alongside the mean
# so a reader sees both in one glance (the mean alone is easily dragged by a
# handful of code-heavy or unusually long posts; the median is the more
# "typical article" figure). `post_count` and `writing_years` are
# deliberately NOT rendered here -- they're time/count-dimension fields that
# belong to `pelican-heatmap`'s widget instead (which already shows post
# count and, as of the same migration, writing years).
# `ArticleWordCountAggregator.compute()` still returns all seven fields
# unchanged (CLI/other template consumers may still want them); only this
# widget's rendered field list shrank.
# Compact: for sidebars/footers -- just the headline numbers, picked from the
# fields above (aggregate volume + per-post average, skipping the
# CJK/English-word breakdown *and* the median -- deliberately kept at 2
# fields, not 3. The median is genuinely useful next to the mean when both
# are visible at once (that's the whole point of adding it), but compact's
# whole reason to exist is "just the headline, nothing else"; if a site
# wants distribution detail it can use the full widget instead. Since no
# `main-blog` content currently uses `{% writing_stats compact %}` yet (only
# the full variant is), there's no existing-widget-shape to preserve here
# either way -- this is a fresh call, not a compatibility constraint).
_WIDGET_FIELDS: tuple[str, ...] = (
    "cjk_char_count",
    "english_word_count",
    "total_char_count",
    "average_chars_per_article",
    "median_chars_per_article",
)
_COMPACT_WIDGET_FIELDS: tuple[str, ...] = ("total_char_count", "average_chars_per_article")

# --- i18n: locale label tables ---------------------------------------------
#
# Mirrors `pelican-heatmap`'s `pelican_heatmap.js` `LOCALES` table (sibling
# plugin, same repo family, same convention): a plain dict keyed by lang
# tag, no gettext/babel dependency (see plan constraint). Unlike heatmap
# (client-side JS, resolves `document.documentElement.lang` in the
# browser), this widget substitutes server-side at `signals.content_written`
# time -- there's no DOM to read from, so `_resolve_lang()` below reads the
# rendered content's own `.lang` instead. See that function's docstring for
# the source-verified evidence of what `content_written`'s `context` param
# actually contains.
DEFAULT_LOCALE = "en"
_LOCALES: dict[str, dict[str, str]] = {
    "en": {
        "post_count": "Posts",
        "cjk_char_count": "CJK Characters",
        "english_word_count": "English Words",
        "total_char_count": "Total Characters",
        "writing_years": "Years Writing",
        "average_chars_per_article": "Avg. Chars / Post",
        "median_chars_per_article": "Median Chars / Post",
    },
    "zh-TW": {
        "post_count": "貼文總數",
        "cjk_char_count": "中文字數",
        "english_word_count": "英文單詞數",
        "total_char_count": "總字元數",
        "writing_years": "寫作年資",
        "average_chars_per_article": "平均每篇字數",
        "median_chars_per_article": "中位數每篇字數",
    },
}


def _resolve_locale(lang: str) -> dict[str, str]:
    """Resolve a lang tag to a field->label dict.

    Lookup mirrors heatmap's JS `LOCALES` lookup (`pelican_heatmap.js:61-63`):
    exact match first (case-insensitive, so site `Lang: zh-tw` matches the
    `zh-TW` table key), then the primary subtag (e.g. "zh" out of
    "zh-hant"), then `DEFAULT_LOCALE`. `PELICAN_STAT_LABELS` (settings dict,
    same per-lang shape as `_LOCALES`) lets a site override individual
    labels; the override is merged on top of whichever base locale was
    chosen, so a partial override (e.g. just `post_count`) doesn't lose the
    rest of that language's labels.
    """
    normalized = lang.lower()
    exact = next((key for key in _LOCALES if key.lower() == normalized), None)
    primary = normalized.split("-")[0]
    base_key = exact or next((key for key in _LOCALES if key.lower() == primary), None) or DEFAULT_LOCALE
    base = _LOCALES[base_key]

    overrides_by_lang: dict[str, dict[str, str]] = _settings.get("PELICAN_STAT_LABELS", {})
    override = next(
        (v for k, v in overrides_by_lang.items() if k.lower() == base_key.lower()),
        {},
    )
    return {**base, **override}


def _resolve_lang(context: dict[str, Any]) -> str:
    """Determine which language to render the widget's labels in.

    This widget substitutes at `signals.content_written` time (see the
    module comment above `_substitute_shortcode_html`), which fires once
    per rendered *file* -- there is no DOM/browser to read
    `document.documentElement.lang` from (unlike `pelican-heatmap`, a
    client-side widget). Verified by reading the installed
    `pelican.writers.Writer.write_file()` (`pelican/writers.py:217-233`):
    `content_written` is sent with `context=localcontext`, and
    `localcontext` is `context.copy()` plus whatever `**kwargs` the calling
    generator passed to `write()`. For article/page output specifically,
    `pelican/generators.py` passes `article=article` (`generators.py:515`,
    inside `generate_articles()`) or `page=page` (`generators.py:997`,
    inside `generate_pages()`) respectively. Both `Article` and `Page` are
    `pelican.contents.Content` subclasses, which always set `self.lang`
    (from that content's own `Lang:` metadata, falling back to
    `DEFAULT_LANG` -- `pelican/contents.py:106-108`) during
    `content_object_init`, which always runs before `content_written`.

    Priority: the content object's own `.lang` (so the same
    `{% writing_stats %}` shortcode renders correctly on both the zh-tw
    primary site and the nested `i18n_subsites` en subsite, matching this
    site's actual topology) -> `context["DEFAULT_LANG"]` (present because
    `context` starts life as `self.settings.copy()`, confirmed at
    `pelican/__init__.py:96`) -> `DEFAULT_LOCALE` ("en") as the last
    resort, for output that has neither (e.g. archive/tag/category listing
    pages, which never carry the shortcode anyway -- it only ever appears
    inside article/page Markdown body text).
    """
    content = context.get("article") or context.get("page")
    lang = getattr(content, "lang", None) if content is not None else None
    if not lang:
        lang = context.get("DEFAULT_LANG")
    return lang or DEFAULT_LOCALE


def _render_widget_html(
    stats: dict[str, int | float],
    *,
    compact: bool,
    lang: str = DEFAULT_LOCALE,
    include_style: bool = True,
) -> str:
    """Render the `{% writing_stats %}` widget as a standalone HTML fragment.

    Self-contained (inline `<style>`, scoped to `.pelican-stat-widget`) --
    see plan.md Milestone C design judgment 2 for why: there's no theme hook
    (like heatmap's attila-side `<link>` auto-injection) available without
    editing the attila theme repo, which is out of scope.

    `include_style=False` omits the `<style>` block entirely -- used by
    `_substitute_shortcode_html` when a single rendered page has more than
    one `{% writing_stats %}` call, so the (page-scoped, not
    instance-scoped) CSS rules only get emitted once. See that function's
    docstring for the full rationale.

    Numbers are formatted with `:,` (thousands separators, e.g. `220,918`)
    -- this works unchanged for both `int` and already-rounded `float`
    values (`ArticleWordCountAggregator.compute()` rounds its float fields
    to 1 decimal place), so it doesn't need a locale-specific decimal/digit
    convention on top.
    """
    fields = _COMPACT_WIDGET_FIELDS if compact else _WIDGET_FIELDS
    labels = _resolve_locale(lang)
    items = "".join(
        f'<dl class="pstat-card"><dt class="pstat-label">{labels.get(key, key)}</dt>'
        f'<dd class="pstat-num">{stats.get(key, 0):,}</dd></dl>'
        for key in fields
    )
    style = _WIDGET_STYLE if include_style else ""
    variant_class = " pelican-stat-widget--compact" if compact else ""
    return f'<div class="pelican-stat-widget{variant_class}">{style}{items}</div>'


def _substitute_shortcode_html(path: str, context: dict[str, Any]) -> None:
    """Substitute every `{% writing_stats %}`/`{% writing_stats compact %}`
    occurrence in one rendered HTML file.

    A single article/page can legitimately contain the shortcode more than
    once (e.g. `{% writing_stats %}` once mid-article and `{% writing_stats
    compact %}` again in a closing note). `pattern.sub(replace, html)` below
    calls `replace` once per match *within this one file*, so `style_emitted`
    -- a plain closure-local flag, fresh for every call to this function
    (i.e. fresh per output file) -- lets only the first match's rendered
    output carry the `<style>` block. This is safe to dedupe because the CSS
    rules are page-scoped (`.pelican-stat-widget ...` selectors, not
    instance-scoped ids), so every widget instance on the page is already
    styled by that one copy; a second identical `<style>` block would be
    inert bytes, not a second independent set of rules.

    Two substitution passes handle the `<p>` un-nesting bug (see
    `_build_p_wrapped_shortcode_pattern`'s docstring for the full "why"):

    1. `p_wrapped_pattern` first replaces every `<p>...</p>` whose *entire*
       content is one shortcode occurrence, dropping the `<p>`/`</p>` along
       with it -- this is the common case (`{% writing_stats %}` written on
       its own line), and the one that produced illegal
       `<p><div>...</div></p>` nesting before this fix.
    2. `pattern` then runs over what's left, catching any shortcode written
       inline (mid-paragraph, with other text still in the same `<p>`) --
       accepted limitation: that case still produces
       `<p>text<div>...</div>text</p>`, illegal HTML, but from an authoring
       choice (splitting a block-level widget into the middle of a
       sentence) this fix does not attempt to un-nest; see plan.md's bug
       report for the scope decision.

    Running pass 1 before pass 2 over the *same* string (pass 2 operates on
    pass 1's output, not the original `html`) means a shortcode that pass 1
    already swallowed can never also be matched by pass 2 -- its literal
    `{% ... %}` text no longer exists in the string pass 2 sees.
    """
    output = Path(path)
    if output.suffix.lower() != ".html":
        return

    shortcode = _settings.get("PELICAN_STAT_SHORTCODE", DEFAULT_SHORTCODE)
    html = output.read_text(encoding="utf-8")
    if shortcode not in html:
        return

    p_wrapped_pattern = _build_p_wrapped_shortcode_pattern(shortcode)
    pattern = _build_shortcode_pattern(shortcode)
    lang = _resolve_lang(context)
    style_emitted = False

    def replace(match: re.Match[str]) -> str:
        nonlocal style_emitted
        variant = match.group(1)
        include_style = not style_emitted
        style_emitted = True
        return _render_widget_html(
            _CACHED_STATS or {},
            compact=variant == "compact",
            lang=lang,
            include_style=include_style,
        )

    html_after_p_unwrap = p_wrapped_pattern.sub(replace, html)
    new_html = pattern.sub(replace, html_after_p_unwrap)
    if new_html != html:
        output.write_text(new_html, encoding="utf-8")


def register() -> None:
    signals.initialized.connect(_initialize_shortcode)
    signals.all_generators_finalized.connect(_attach_word_count_stats)
    signals.content_written.connect(_substitute_shortcode_html)
    signals.finalized.connect(_reset_word_count_cache)
