import { render, screen } from "@testing-library/react";
import { formatChf, LimitTile } from "./LimitTile";

describe("LimitTile", () => {
  it("hard stop tile names its limit in text", () => {
    render(<LimitTile tone="stopped" amount="200" />);
    const tile = screen.getByRole("group", { name: "Hard stop at CHF 200.00" });
    expect(tile).toHaveTextContent("Hard stop at");
    expect(tile).toHaveTextContent("CHF 200.00");
  });

  it("labels a green budget tile as guidance, never as enforced", () => {
    render(<LimitTile tone="allowed" amount="150.5" />);
    expect(screen.getByRole("group", { name: "Budget · guidance CHF 150.50" })).toBeInTheDocument();
  });

  it("names the violet tile in words too", () => {
    render(<LimitTile tone="attention" amount="215.00" />);
    expect(screen.getByRole("group", { name: "Stretch up to CHF 215.00" })).toBeInTheDocument();
  });

  it("formats money from the string, never through a float", () => {
    expect(formatChf("0.1")).toBe("0.10");
    expect(formatChf("12345678901234567.89")).toBe("12'345'678'901'234'567.89");  // beyond float precision, kept exact
    expect(formatChf("1000")).toBe("1'000.00");
  });

  it("refuses anything that is not a plain decimal amount", () => {
    for (const bad of ["1e3", "-5", "12.345", "", "NaN", "CHF 5"]) expect(() => formatChf(bad), bad).toThrow();
  });
});
