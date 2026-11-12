/**
 * jev-pre-llm intent roulette — one LED per intent, under the chat.
 *
 * Install: copy this file to
 *   $HERMES_HOME/desktop-plugins/jev-pre-llm/plugin.js
 * (folder name must match the plugin id), then Cmd/Ctrl+K →
 * "Reload desktop plugins". Plain ESM, loaded uncompiled.
 *
 * A pane docked below the conversation. While the solver is choosing,
 * the LEDs light one by one, slowly, in yellow (pure CSS, one LED per
 * enabled intent from the backend). The winner turns green and is named
 * in large text for a few seconds, then the pane clears itself.
 * The LLM thinking afterwards never touches the LEDs.
 */

import { atom, haptic, host, Tip, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'jev-pre-llm'
const POLL_MS = 3000
const ROULETTE_MS = 6000
const WINNER_MS = 5000
const FRESH_MS = 20000
const STEP_MS = 450

const CYCLE_CSS = '@keyframes jpl-cycle{0%,100%{opacity:.2}15%{opacity:1}}'
const DOT_ON = 'var(--ui-accent, #eab308)'
const DOT_IDLE = 'var(--ui-text-quaternary)'
const DOT_WIN = 'var(--ui-success, #22c55e)'

const FALLBACK_ENABLED = ['check_tg', 'tg_person', 'fp_status']
const statusAtom = atom({ last: null, enabled: [], trace_count: 0, backend: false, gw: '' })
const turn = { active: false, start: 0 }
const winner = { id: null, outcome: null, latency: 0, ts: 0 }

// Gateway name is read OUTSIDE the render path: a missing atom must never
// crash the pane. Plain string, safe to render.
function readGw() {
  try {
    const g = host.state.gateway.get()
    if (g && typeof g === 'object') return g.name || g.id || g.label || ''
    if (typeof g === 'string') return g
  } catch { /* host without gateway atom */ }
  try {
    const p = host.state.focusedSessionProfile.get()
    if (typeof p === 'string') return p
  } catch { /* host without profile atom */ }
  return ''
}

function pollStatus(ctx) {
  ctx.rest('/status', { timeoutMs: 4000 }).then(
    (data) => {
      if (!data || typeof data !== 'object') return
      statusAtom.set({
        last: data.last || null,
        enabled: Array.isArray(data.enabled) ? data.enabled : [],
        trace_count: data.trace_count || 0,
        backend: true,
        gw: readGw()
      })
      const last = data.last
      if (last && last.ts && last.selected_handler && turn.start > 0) {
        const age = Date.now() - Date.parse(last.ts)
        if (!Number.isNaN(age) && age < FRESH_MS && Date.parse(last.ts) >= turn.start - 2000) {
          if (last.outcome === 'short_circuit' || last.outcome === 'would_short_circuit') {
            winner.id = last.selected_handler
            winner.outcome = last.outcome
            winner.latency = last.latency_ms || 0
            winner.ts = Date.now()
          }
        }
      }
    },
    () => { statusAtom.set((prev) => ({ ...prev, backend: false })) }
  )
}

function RoulettePane() {
  try {
    return RouletteInner()
  } catch (err) {
    return jsx('div', {
      className: 'flex h-full flex-col justify-center gap-2 px-4 py-2',
      children: jsx('div', {
        className: 'text-xs text-(--ui-text-secondary)',
        children: `roulette render error: ${(err && err.message) || err}`
      })
    })
  }
}

function RouletteInner() {
  const busy = useValue(host.state.busy)
  const status = useValue(statusAtom) || {}
  const enabled = Array.isArray(status.enabled) ? status.enabled : []
  const gwName = typeof status.gw === 'string' ? status.gw : ''

  if (busy && !turn.active) {
    turn.active = true
    turn.start = Date.now()
    winner.id = null
  }
  if (!busy) turn.active = false

  const now = Date.now()
  const showWinner = winner.id && (now - winner.ts) < WINNER_MS
  const spinning = turn.active && !showWinner && (now - turn.start) < ROULETTE_MS
  const dots = enabled.length > 0 ? enabled : FALLBACK_ENABLED
  const period = (dots.length * STEP_MS) / 1000

  // The pane clears itself: idle with nothing fresh to show renders nothing.
  const lastAge = status.last && status.last.ts ? now - Date.parse(status.last.ts) : Infinity
  if (!spinning && !showWinner && (Number.isNaN(lastAge) || lastAge > FRESH_MS)) {
    return jsx('div', { className: 'h-full w-full' })
  }

  let headline
  if (showWinner) headline = `${winner.id}  ·  ${winner.outcome} (${winner.latency} ms)`
  else if (spinning) headline = 'solver is choosing…'
  else if (status.backend) headline = `idle — ${status.trace_count} traced turns`
  else headline = 'idle — backend unreachable'
  if (gwName) headline = `${gwName} · ${headline}`

  return jsxs('div', {
    className: 'flex h-full flex-col justify-center gap-2 px-4 py-2',
    children: [
      jsx('style', { children: CYCLE_CSS }),
      jsxs('div', {
        className: 'flex items-end gap-5',
        children: dots.map((id, i) => jsxs('div', {
          key: id,
          className: 'flex flex-col items-center gap-1',
          children: [
            jsx('span', {
              title: id,
              style: {
                width: '14px',
                height: '14px',
                borderRadius: '9999px',
                background: showWinner
                  ? (id === winner.id ? DOT_WIN : DOT_IDLE)
                  : (spinning ? DOT_ON : DOT_IDLE),
                opacity: showWinner ? 1 : undefined,
                animation: spinning ? `jpl-cycle ${period}s linear infinite` : 'none',
                animationDelay: spinning ? `${-(i * STEP_MS) / 1000}s` : '0s'
              }
            }),
            jsx('span', {
              className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
              children: id
            })
          ]
        }))
      }),
      jsx('div', {
        className: 'text-xs text-(--ui-text-secondary)',
        children: headline
      })
    ]
  })
}

export default {
  id: ID, // must match the folder name
  name: 'jev-pre-llm roulette',
  register(ctx) {
    ctx.i18n.register({
      en: { paneTitle: 'intent roulette' }
    })
    pollStatus(ctx)
    setInterval(() => pollStatus(ctx), POLL_MS)
    ctx.register({
      id: 'roulette',
      area: 'panes',
      title: 'intent roulette',
      data: { placement: 'bottom', dock: { pane: 'workspace', pos: 'bottom', enforce: true }, height: '132px' },
      render: () => jsx(RoulettePane, {})
    })
  }
}
