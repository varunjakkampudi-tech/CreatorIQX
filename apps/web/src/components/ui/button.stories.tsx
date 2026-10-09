import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "./button";

const meta: Meta<typeof Button> = {
  component: Button,
  title: "UI/Button",
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "danger", "ghost"],
    },
    size: { control: "select", options: ["sm", "md", "lg"] },
  },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = {
  args: { children: "Save changes", variant: "primary" },
};

export const Secondary: Story = {
  args: { children: "Cancel", variant: "secondary" },
};

export const Danger: Story = {
  args: { children: "Delete video", variant: "danger" },
};

export const Ghost: Story = {
  args: { children: "Dismiss", variant: "ghost" },
};

export const Disabled: Story = {
  args: { children: "Save changes", variant: "primary", disabled: true },
};
