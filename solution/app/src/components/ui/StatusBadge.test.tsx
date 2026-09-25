import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each([["draft", "DRAFT"], ["active", "ACTIVE"], ["revoked", "REVOKED"]] as const)(
    "shows %s as the word %s", (status, text) => {
      render(<StatusBadge status={status} />);
      expect(screen.getByText(text)).toHaveClass("badge", `badge-${status}`);
    });
});
