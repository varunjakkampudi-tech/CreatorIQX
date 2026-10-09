/**
 * Forbids a letter-bearing string literal directly in JSX markup: text
 * between tags (JSXText), and the `alt`/`title`/`placeholder`/`aria-label`
 * attributes, which are the other common places UI copy gets typed in by
 * hand. Spec section 5 lists next-intl, "prepared, English first" - a
 * literal here is copy that was never routed through it, so it can't be
 * translated later without finding every call site again. Pure whitespace,
 * punctuation-only text (JSX indentation, a bare "-" or "/"), and the
 * `aria-hidden` attribute itself are not copy and are allowed.
 *
 * This is the lint rule P0-082's acceptance criterion names ("string lint
 * passes"), matching the shape of the existing no-raw-hex-in-components rule
 * in eslint.config.mjs.
 */
const HAS_LETTERS = /[A-Za-z]/;
const COPY_ATTRIBUTES = new Set(["alt", "title", "placeholder", "aria-label"]);

const noRawJsxText = {
  rules: {
    "no-raw-jsx-text": {
      meta: {
        type: "problem",
        docs: {
          description:
            "Disallow hard-coded UI copy in JSX text or copy-bearing attributes; use next-intl instead.",
        },
        schema: [],
      },
      create(context) {
        return {
          JSXText(node) {
            if (HAS_LETTERS.test(node.value)) {
              context.report({
                node,
                message:
                  "No hard-coded UI text in JSX. Add the string to apps/web/messages/en.json and read it with next-intl (useTranslations/getTranslations).",
              });
            }
          },
          JSXAttribute(node) {
            const name = node.name && node.name.name;
            if (
              typeof name === "string" &&
              COPY_ATTRIBUTES.has(name) &&
              node.value &&
              node.value.type === "Literal" &&
              typeof node.value.value === "string" &&
              HAS_LETTERS.test(node.value.value)
            ) {
              context.report({
                node: node.value,
                message: `No hard-coded UI text in the "${name}" attribute. Add the string to apps/web/messages/en.json and read it with next-intl.`,
              });
            }
          },
        };
      },
    },
  },
};

export default noRawJsxText;
