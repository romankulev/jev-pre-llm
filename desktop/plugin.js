/**
 * jev-pre-llm LED — status-bar activity light for the fast-path plugin.
 *
 * Install: copy this file to
 *   $HERMES_HOME/desktop-plugins/jev-pre-llm/plugin.js
 * (folder name must match the plugin id), then Cmd/Ctrl+K →
 * "Reload desktop plugins". Plain ESM, loaded uncompiled.
 *
 * v1: follows turn atoms only — dim when idle, pulsing while the focused
 * chat is working. Shows that *a* turn is running, not which path it took.
 * v2 (planned, see SPEC.md): subscribes to `jev-pre-llm/decision` backend
 * events for classifying / short-circuit:<id> / fallback states.
 */

import { haptic, host, Tip, useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'jev-pre-llm'

const PULSE_CSS = '@keyframes jpl-pulse{50%{opacity:.2}}'

function LedChip() {
  const busy = useValue(host.state.busy)
  const waiting = useValue(host.state.awaitingResponse)
  const active = busy || waiting

  return jsx(Tip, {
    label: active
      ? 'jev-pre-llm: turn running (fast-path classifying or LLM working)'
      : 'jev-pre-llm: idle',
    children: jsx('button', {
      type: 'button',
      className: 'inline-flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)',
      onClick: () => {
        haptic('tap')
        host.notify({
          kind: 'info',
          message: active ? 'jev-pre-llm: turn in progress' : 'jev-pre-llm: idle — no turn running'
        })
      },
      children: [
        jsx('style', { children: PULSE_CSS }),
        jsx('span', {
          style: {
            width: '8px',
            height: '8px',
            borderRadius: '9999px',
            background: active ? 'var(--ui-accent)' : 'var(--ui-text-quaternary)',
            animation: active ? 'jpl-pulse 1s ease-in-out infinite' : 'none'
          }
        }),
        jsx('span', { children: 'fast-path' })
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
    ctx.register({
      id: 'led',
      area: 'statusBar.right',
      order: 130,
      render: () => jsx(LedChip, {})
    })
  }
}
