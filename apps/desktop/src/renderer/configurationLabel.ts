import type { RunProfile } from "./types";

/** Give a configuration its model context wherever models share one chooser. */
export function configurationLabel(configuration?: RunProfile, bundleName?: string): string | undefined {
  if (!configuration) return undefined;
  const model = configuration.bundle_name || bundleName;
  return model && model !== configuration.display_name ? `${model} · ${configuration.display_name}` : configuration.display_name;
}

export function findConfiguration(configurations: RunProfile[], id: string | null | undefined): RunProfile | undefined {
  return id ? configurations.find(item => item.id === id) : undefined;
}
