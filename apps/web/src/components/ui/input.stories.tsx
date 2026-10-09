import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Input } from "./input";

const meta: Meta<typeof Input> = {
  component: Input,
  title: "UI/Input",
};
export default meta;

type Story = StoryObj<typeof Input>;

export const Default: Story = {
  args: { "aria-label": "Channel name", placeholder: "My channel" },
};

export const Invalid: Story = {
  args: {
    "aria-label": "Channel name",
    "aria-invalid": true,
    defaultValue: "",
  },
};

export const Disabled: Story = {
  args: { "aria-label": "Channel name", disabled: true, defaultValue: "" },
};
