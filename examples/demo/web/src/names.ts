// Stored file names, shown before the upload starts.

// COUPLED:safe-name: web
export function safeName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9.-]+/g, "-").replace(/^-+|-+$/g, "");
}
// COUPLED:safe-name:END
