export function passcodeErrorMessage(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : ''
  // Electron adds IPC details around backend errors; show only known UI copy.
  if (/(?:That|The current) passcode was not (?:recognized|accepted)/.test(message)) {
    return 'Le mot de passe n’est pas correct.'
  }
  if (/Passcodes did not match|The new passcodes do not match/.test(message)) {
    return 'Les mots de passe ne correspondent pas.'
  }
  return fallback
}
