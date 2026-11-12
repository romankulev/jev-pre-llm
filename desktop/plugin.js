/**
 * jev-pre-llm LED — status-bar activity light for the fast-path plugin.
 *
 * Install: copy this file to
 *   $HERMES_HOME/desktop-plugins/jev-pre-llm/plugin.js
 * (folder name must match the plugin id), then Cmd/Ctrl+K →
 * "Reload desktop plugins". Plain ESM, loaded uncompiled.
 *
 * The dot follows turn atoms (dim when idle, pulsing while the focused
 * chat is working) plus a 5s poll of the Python backend (`GET status`):
 * a recent short_circuit / would_short_circuit decision lights the dot
 * solid and names the intent in the tooltip. No backend (or OAuth remote
 * where sockets are a no-op) — atoms only, still useful.
 */

import { atom, haptic, host, Tip, useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'jev-pre-llm'
const POLL_MS = 5000
const FRESH_MS = 15000

const PULSE_CSS = '@keyframes jpl-pulse{50%{opacity:.2}}'

const statusAtom = atom({ last: null, trace_count: 0, backend: false })

function pollStatus(ctx) {
  ctx.rest('/status', { timeoutMs: 4000 }).then(
    (data) => {
      if (data && typeof data === 'object') {
        statusAtom.set({ last: data.last || null, trace_count: data.trace_count || 0, backend: true })
      }
    },
    () => { statusAtom.set((prev) => ({ ...prev, backend: false })) }
  )
}

function freshDecision(last) {
  if (!last || !last.ts) return null
  const age = Date.now() - Date.parse(last.ts)
  if (Number.isNaN(age) || age > FRESH_MS) return null
  if (last.outcome === 'short_circuit' || last.outcome === 'would_short_circuit') return last
  return null
}

function LedChip() {
  const busy = useValue(host.state.busy)
  const waiting = useValue(host.state.awaitingResponse)
  const status = useValue(statusAtom)
  const active = busy || waiting
  const hit = freshDecision(status.last)

  const dot = hit ? 'var(--ui-accent)' : active ? 'var(--ui-accent)' : 'var(--ui-text-quaternary)'
  const anim = hit ? 'none' : active ? 'jpl-pulse 1s ease-in-out infinite' : 'none'
  const label = hit
    ? `jev-pre-llm: ${hit.outcome} → ${hit.selected_handler || '?'} (${hit.mode || '?'})`
    : active
      ? 'jev-pre-llm: turn running (fast-path classifying or LLM working)'
      : status.backend
        ? `jev-pre-llm: idle (traces: ${status.trace_count})`
        : 'jev-pre-llm: idle (backend unreachable)'

  return jsx(Tip, {
    label,
    children: jsx('button', {
      type: 'button',
      className: 'inline-flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)',
      onClick: () => {
        haptic('tap')
        host.notify({ kind: 'info', message: label })
      },
      children: [
        jsx('style', { children: PULSE_CSS }),
        jsx('span', {
          style: {
            width: '8px',
            height: '8px',
            borderRadius: '9999px',
            background: dot,
            animation: anim
          }
        }),
        jsx('span', { children: hit ? hit.selected_handler || 'fast-path' : 'fast-path' })
      ]
    })
  })
}

export default {
  id: ID, // must match the folder name
  name: 'jev-pre-llm LED',
  register(ctx) {
    ctx.i18n.register({
      en: { chipTip: 'jev-pre-llm fast-path activity' }
    })
    pollStatus(ctx)
    setInterval(() => pollStatus(ctx), POLL_MS)
    ctx.register({
      id: 'led',
      area: 'statusBar.right',
      order: 130,
      render: () => jsx(LedChip, {})
    })
  }
}
