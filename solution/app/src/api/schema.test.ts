import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import openapiTS, { astToString } from "openapi-typescript";

describe("API types", () => {
  it("are generated from the current contract (run `npm run gen:api` after changing policy-api.yaml)", async () => {
    const contract = new URL(`file://${resolve(__dirname, "../../../contracts/policy-api.yaml")}`);
    const fresh = astToString(await openapiTS(contract));
    const committed = readFileSync(resolve(__dirname, "schema.d.ts"), "utf8");
    const body = (text: string) => text.slice(text.indexOf("export"));  // ignore the generated header
    expect(body(committed)).toBe(body(fresh));
  }, 20000);
});
