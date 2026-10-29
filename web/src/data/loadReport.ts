import { Report } from "./schema";

export class ReportError extends Error {
  constructor(message: string, readonly detail?: string) {
    super(message);
    this.name = "ReportError";
  }
}

/** Fetch and validate the report. Errors name the file and the field, never a stack. */
export async function loadReport(url: string, signal?: AbortSignal): Promise<Report> {
  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch (cause) {
    if ((cause as Error).name === "AbortError") throw cause;
    throw new ReportError(`Could not reach ${url}`, String(cause));
  }
  if (!response.ok) throw new ReportError(`${url} answered ${response.status}`);
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new ReportError(`${url} is not valid JSON`);
  }
  const parsed = Report.safeParse(json);
  if (!parsed.success) {
    const detail = parsed.error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`).join("\n");
    throw new ReportError(`${url} does not match the report schema`, detail);
  }
  return parsed.data;
}
