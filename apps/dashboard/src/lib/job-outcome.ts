export interface FileChange {
  path: string;
  additions: number;
  deletions: number;
  diff: string;
}

export function fileChanges(diff: string, paths: string[]): FileChange[] {
  const chunks = diff.split(/(?=^diff --git )/m).filter(Boolean);
  return paths.map((path) => {
    const chunk =
      chunks.find((c) =>
        c
          .split("\n")
          .some((line) => line === `+++ b/${path}` || line === `--- a/${path}`),
      ) || "";
    const lines = chunk.split("\n");
    return {
      path,
      additions: lines.filter((l) => l.startsWith("+") && !l.startsWith("+++ "))
        .length,
      deletions: lines.filter((l) => l.startsWith("-") && !l.startsWith("--- "))
        .length,
      diff: chunk,
    };
  });
}
