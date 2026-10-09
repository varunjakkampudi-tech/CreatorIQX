import type { Meta, StoryObj } from "@storybook/nextjs-vite";

/**
 * The design-token reference Storybook asks for (P0-083's "tokens page"),
 * next to the primitives that consume these same tokens. Mirrors
 * app/page.tsx's token showcase without duplicating it as a route.
 */
const meta: Meta = {
  title: "Design tokens/Colors",
};
export default meta;

type Story = StoryObj;

const swatches = [
  { label: "surface", className: "bg-surface border border-border" },
  {
    label: "surface-raised",
    className: "bg-surface-raised border border-border",
  },
  { label: "brand", className: "bg-brand text-brand-ink" },
  { label: "danger", className: "bg-danger text-white" },
  { label: "success", className: "bg-success text-white" },
  { label: "warning", className: "bg-warning text-white" },
];

export const Colors: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {swatches.map((swatch) => (
        <div
          key={swatch.label}
          className={`rounded-md p-4 text-sm font-medium ${swatch.className}`}
        >
          {swatch.label}
        </div>
      ))}
    </div>
  ),
};
