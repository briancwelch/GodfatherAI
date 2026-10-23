export const builtInVariables = [
  "workspace.id",
  "workspace.name",
  "job.name",
  "job.goal",
  "task.key",
  "task.name",
  "agent.id",
  "agent.name",
  "agent.version",
  "model.identifier",
];
export function taskReferences(
  instruction: string,
  earlier: string[],
  custom: string[],
): string[] {
  const expression = /\{\{\s*([A-Za-z][A-Za-z0-9_.-]*)\s*\}\}/g;
  if (/\{\{|\}\}/.test(instruction.replace(expression, "")))
    throw new Error("Use a complete variable such as {{tasks.task1.output}}.");
  const dependencies: string[] = [];
  for (const match of instruction.matchAll(expression)) {
    const key = match[1];
    if (
      builtInVariables.includes(key) ||
      custom.map((name) => `vars.${name}`).includes(key)
    )
      continue;
    const output = /^tasks\.([A-Za-z][A-Za-z0-9_-]{0,63})\.output$/.exec(key);
    if (!output)
      throw new Error("Unknown variable. Choose a reference from Variables.");
    if (!earlier.includes(output[1]))
      throw new Error("Output variables must refer to an earlier task.");
    dependencies.push(output[1]);
  }
  return [...new Set(dependencies)];
}
