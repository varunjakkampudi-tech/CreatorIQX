import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Card } from "./card";

const meta: Meta<typeof Card> = {
  component: Card,
  title: "UI/Card",
};
export default meta;

type Story = StoryObj<typeof Card>;

export const Default: Story = {
  args: {
    children: (
      <>
        <h2>Channel health score</h2>
        <p>78 out of 100, up 4 points since last audit.</p>
      </>
    ),
  },
};
