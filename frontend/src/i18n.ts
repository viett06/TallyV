import messages from './locales/vi.json'

export type MessageKey = keyof typeof messages
export type MessageValues = Record<string, string | number>

/** Resolve local presentation text without embedding translated strings in code. */
export function t(key: MessageKey, values: MessageValues = {}): string {
  return messages[key].replace(/\{(\w+)\}/g, (_, name: string) => {
    if (!(name in values)) throw new Error('Missing translation parameter: ' + name)
    return String(values[name])
  })
}
