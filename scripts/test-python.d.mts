export interface TestPythonOptions {
  env?: NodeJS.ProcessEnv;
  repoRoot?: string;
  platform?: NodeJS.Platform;
}

export function resolveTestPython(options?: TestPythonOptions): string;
