/**
 * jev-pre-llm intent roulette — one LED per intent.
 *
 * Install: copy this file to
 *   $HERMES_HOME/desktop-plugins/jev-pre-llm/plugin.js
 * (folder name must match the plugin id), then Cmd/Ctrl+K →
 * "Reload desktop plugins". Plain ESM, loaded uncompiled.
 *
 * While the solver is choosing, the dots spin like a roulette (pure CSS,
 * one dot per enabled intent from the backend). The winner lights solid
 * and is named in the chip for a few seconds, then everything fades back
 * to idle. The LLM thinking afterwards never touches the LEDs.
 */

import { atom, haptic, host, Tip, useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'jev-pre-llm'
const POLL_MS = 3000
const ROULETTE_MS = 6000
const WINNER_MS = 4000
const FRESH_MS = 20000
const STEP_MS = 180

const CYCLE_CSS = '@keyframes jpl-cycle{0%,100%{opacity:.2}12%{opacity:1}}'

const statusAtom = atom({ last: null, enabled: [], trace_count: 0, backend: false })
const turn = { active: false, start: 0 }
const winner = { id: null, outcome: null, ts: 0 }

function pollStatus(ctx) {
  ctx.rest('/status', { timeoutMs: 4000 }).then(
    (data) => {
      if (!data || typeof data !== 'object') return
      statusAtom.set({
        last: data.last || null,
        enabled: Array.isArray(data.enabled) ? data.enabled : [],
        trace_count: data.trace_count || 0,
        backend: true
      })
      const last = data.last
      if (last && last.ts && last.selected_handler && turn.start > 0) {
        const age = Date.now() - Date.parse(last.ts)
        if (!Number.isNaN(age) && age < FRESH_MS && Date.parse(last.ts) >= turn.start - 2000) {
          if (last.outcome === 'short_circuit' || last.outcome === 'would_short_circuit') {
            winner.id = last.selected_handler
            winner.outcome = last.outcome
            winner.ts = Date.now()
          }
        }
      }
    },
    () => { statusAtom.set((prev) => ({ ...prev, backend: false })) }
  )
}

function RouletteChip() {
  const busy = useValue(host.state.busy)
  const status = useValue(statusAtom)

  if (busy && !turn.active) {
    turn.active = true
    turn.start = Date.now()
    winner.id = null
  }
  if (!busy) turn.active = false

  const now = Date.now()
  const showWinner = winner.id && (now - winner.ts) < WINNER_MS
  const spinning = turn.active && !showWinner && (now - turn.start) < ROULETTE_MS
  const dots = status.enabled.length > 0 ? status.enabled : ['fast-path']
  const period = (dots.length * STEP_MS) / 1000

  let tip
  if (showWinner) tip = `jev-pre-llm: ${winner.outcome} → ${winner.id}`
  else if (spinning) tip = 'jev-pre-llm: solver is choosing…'
  else if (status.backend) tip = `jev-pre-llm: idle (traces: ${status.trace_count})`
  else tip = 'jev-pre-llm: idle (backend unreachable)'

  return jsx(Tip, {
    label: tip,
    children: jsx('button', {
      type: 'button',
      className: 'inline-flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)',
      onClick: () => {
        haptic('tap')
        host.notify({ kind: 'info', message: tip })
      },
      children: [
        jsx('style', { children: CYCLE_CSS }),
        ...dots.map((id, i) => jsx('span', {
          key: id,
          title: id,
          style: {
            width: '8px',
            height: '8px',
            borderRadius: '9999px',
            background: showWinner
              ? (id === winner.id ? 'var(--ui-accent)' : 'var(--ui-text-quaternary)')
              : 'var(--ui-accent)',
            opacity: showWinner ? 1 : undefined,
            animation: spinning ? `jpl-cycle ${period}s linear infinite` : 'none',
            animationDelay: spinning ? `${-(i * STEP_MS) / 1000}s` : '0s'
          }
        })),
        jsx('span', { children: showWinner ? winner.id : 'fast-path' })
      ]
    })
  })
}

export default {
  id: ID, // must match the folder name
  name: 'jev-pre-llm roulette',
  register(ctx) {
    ctx.i18n.register({
      en: { chipTip: 'jev-pre-llm intent roulette' }
    })
    pollStatus(ctx)
    setInterval(() => pollStatus(ctx), POLL_MS)
    ctx.register({
      id: 'led',
      area: 'statusBar.right',
      order: 130,
      render: () => jsx(RouletteChip, {})
    })
  }
}
