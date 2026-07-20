import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "project-context"
    / "scripts"
    / "project_context_markdown.py"
)
SPEC = importlib.util.spec_from_file_location("project_context_markdown", SCRIPT_PATH)
project_context_markdown = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project_context_markdown)


class InlineLinkTargetsTest(unittest.TestCase):
    def targets(self, markdown):
        return list(project_context_markdown.iter_inline_link_targets(markdown))

    def test_parenthesized_destination_and_valid_titles(self):
        markdown = (
            "[Route](../app/(auth)/page.tsx)\n"
            '[Double](double.py "Double title")\n'
            "[Single](single.py 'Single title')\n"
            "[Parenthesized](parenthesized.py (Parenthesized title))\n"
        )

        self.assertEqual(
            self.targets(markdown),
            [
                "../app/(auth)/page.tsx",
                "double.py",
                "single.py",
                "parenthesized.py",
            ],
        )

    def test_invalid_title_or_trailing_junk_is_not_a_link(self):
        markdown = (
            "[Bare junk](source.py junk)\n"
            '[After title](source.py "title" junk)\n'
            '[Unclosed title](source.py "title)\n'
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_unmatched_backticks_do_not_hide_later_links(self):
        markdown = (
            "` unmatched [First](first.py)\n"
            "`` unmatched [Second](second.py)\n"
            "[Third](third.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["first.py", "second.py", "third.py"])

    def test_inline_code_comments_and_indented_code_are_ignored(self):
        markdown = (
            "`[Inline](inline.py)`\n"
            "<!-- [Comment](comment.py) -->\n"
            "\n"
            "    [Indented](indented.py)\n"
            "\t[Tab-indented](tab.py)\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_indented_links_inside_lists_are_not_code(self):
        markdown = (
            "- Sources:\n"
            "    - [Nested unordered](nested-unordered.py)\n"
            "1. Ordered sources\n"
            "    [Ordered continuation](ordered-continuation.py)\n"
            "- Paragraph source\n"
            "\n"
            "    [After blank](after-blank.py)\n"
        )

        self.assertEqual(
            self.targets(markdown),
            [
                "nested-unordered.py",
                "ordered-continuation.py",
                "after-blank.py",
            ],
        )

    def test_list_continuation_survives_intermediate_paragraphs(self):
        markdown = (
            "- Item\n"
            "  Paragraph\n"
            "\n"
            "    [Unordered continuation](unordered.py)\n"
            "\n"
            "1. Item\n"
            "   Paragraph\n"
            "\n"
            "      [Ordered continuation](ordered.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["unordered.py", "ordered.py"])

    def test_indented_code_after_or_inside_a_list_is_ignored(self):
        markdown = (
            "- Item\n"
            "\n"
            "      [List code](list-code.py)\n"
            "      - [List-shaped code](list-shaped-code.py)\n"
            "Outside the list.\n"
            "\n"
            "    [Top-level code](top-level-code.py)\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_top_level_list_shaped_code_is_not_a_list_ancestor(self):
        markdown = (
            "    - Item\n"
            "        [Hidden](hidden.py)\n"
            "   - Valid list\n"
            "       [Visible](visible.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["visible.py"])

    def test_indentation_cannot_interrupt_a_paragraph(self):
        markdown = "Paragraph\n    [Continuation](continuation.py)\n"

        self.assertEqual(self.targets(markdown), ["continuation.py"])

    def test_fence_with_trailing_text_does_not_close_the_fence(self):
        markdown = (
            "```md\n"
            "[Inside](inside.py)\n"
            "``` trailing text\n"
            "[Still inside](still-inside.py)\n"
            "```\n"
            "[Outside](outside.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["outside.py"])

    def test_list_and_blockquote_container_fences_are_ignored(self):
        markdown = (
            "- Item\n"
            "    ~~~\n"
            "    [List fake](list-fake.py)\n"
            "    ~~~~\n"
            "    [List real](list-real.py)\n"
            "> ```\n"
            "> [Quote fake](quote-fake.py)\n"
            "> ````\n"
            "> [Quote real](quote-real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["list-real.py", "quote-real.py"])

    def test_block_boundaries_allow_following_indented_code(self):
        markdown = (
            "# Heading\n"
            "    [Heading code](heading-code.py)\n"
            "```\n"
            "content\n"
            "```\n"
            "    [Fence-adjacent code](fence-adjacent-code.py)\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_setext_heading_allows_following_indented_code(self):
        markdown = (
            "Heading\n"
            "===\n"
            "    [Heading code](heading-code.py)\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_fence_closer_must_stay_in_the_same_container(self):
        markdown = (
            "```\n"
            "> ```\n"
            "[Fake](fake.py)\n"
            "```\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_unclosed_fence_ends_when_its_container_ends(self):
        markdown = (
            "> ```\n"
            "> quote code\n"
            "[After quote](after-quote.py)\n"
            "- Item\n"
            "  ```\n"
            "  list code\n"
            "[After list](after-list.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["after-quote.py", "after-list.py"])

    def test_sibling_list_item_starts_a_new_fence_container(self):
        markdown = (
            "- One\n"
            "  ```\n"
            "- Two\n"
            "  ```\n"
            "  [Fake](fake.py)\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_list_fence_content_cannot_create_a_nested_container(self):
        markdown = (
            "- Item\n"
            "  ```\n"
            "  - fake nested item\n"
            "    [Fake](fake.py)\n"
            "  ```\n"
            "  [Inside real](inside-real.py)\n"
            "[Outside real](outside-real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["inside-real.py", "outside-real.py"])

    def test_indented_fence_cannot_interrupt_a_paragraph(self):
        markdown = (
            "Paragraph\n"
            "    ~~~\n"
            "    [Real](real.py)\n"
            "    ~~~\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_image_and_nested_image_alt_links_are_ignored(self):
        markdown = (
            "![Image](image.png)\n"
            "![[Nested link](nested.py)](image.png)\n"
            "![Outer ![Nested image](nested.png)](outer.png)\n"
            "[Real](real.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["real.py"])

    def test_code_spans_and_nested_links_inside_labels_follow_commonmark(self):
        markdown = (
            "[Label `]` tail](outer.py)\n"
            "[Outer [Inner](inner.py)](ignored-outer.py)\n"
        )

        self.assertEqual(self.targets(markdown), ["outer.py", "inner.py"])

    def test_nbsp_is_not_an_ascii_title_separator(self):
        markdown = '[NBSP](foo.py\u00a0"title")\n'

        self.assertEqual(self.targets(markdown), ['foo.py\u00a0"title"'])

    def test_long_indented_code_block_does_not_recurse(self):
        markdown = ("    code\n" * 1100) + "[Real](real.py)\n"

        self.assertEqual(self.targets(markdown), ["real.py"])


if __name__ == "__main__":
    unittest.main()
