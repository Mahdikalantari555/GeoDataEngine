"""Tests for the in-app help content (``app.help_text``)."""

from __future__ import annotations

from app import help_text
from app.core.indices import INDEX_FORMULAS
from app.core.presets import preset_help_entries


class TestHelpDocument:
    def test_build_help_text_is_non_empty(self):
        body = help_text.build_help_text()
        assert len(body) > 1000
        assert body.endswith("\n")

    def test_every_tab_is_documented(self):
        body = help_text.build_help_text()
        for section in ("Search tab", "Download tab", "Indices tab", "Settings tab"):
            assert section in body

    def test_usage_documents_workflow_steps(self):
        for step in ("Settings", "Search", "Download", "Indices"):
            assert step in help_text.OVERVIEW

    def test_presets_are_listed_with_products(self):
        body = help_text.build_help_text()
        for preset, products in preset_help_entries():
            assert preset in body
            for product in products:
                assert product in body

    def test_index_formulas_are_documented(self):
        body = help_text.build_help_text()
        for name, formula in INDEX_FORMULAS.items():
            assert name in body
            assert formula in body

    def test_optram_is_documented(self):
        body = help_text.build_help_text()
        assert "OPTRAM" in body
        assert "sqrt(NIR / RED)" in body

    def test_output_layout_section(self):
        body = help_text.build_help_text()
        assert "<output>/scenes/" in body
        assert "<output>/products/" in body
        assert "metadata/" in body

    def test_troubleshooting_mentions_mirror_and_prj(self):
        body = help_text.build_help_text()
        assert "pypi.org/simple" in body
        assert ".prj" in body

    def test_bands_documented_for_both_satellites(self):
        body = help_text.build_help_text()
        assert "qa_pixel" in body
        assert "B08" in body


class TestIndexEntries:
    def test_all_indices_have_formula_and_description(self):
        entries = help_text.index_entries()
        assert len(entries) == len(INDEX_FORMULAS)
        for name, formula, description in entries:
            assert name and formula and description
            assert description[0].isupper()


class TestHelpDialog:
    def test_help_button_opens_dialog_with_full_text(self, app, prompter):
        app.open_help()
        assert len(prompter.help_calls) == 1
        assert prompter.help_calls[0] == help_text.build_help_text()
        assert app.last_status == "Help opened"

    def test_help_button_is_on_the_indices_tab(self, app, fake_toolkit, prompter):
        button = fake_toolkit.find_button("Help")
        assert button is not None
        button.invoke()
        assert prompter.help_calls

    def test_help_can_be_opened_repeatedly(self, app, prompter):
        app.open_help()
        app.open_help()
        assert len(prompter.help_calls) == 2
