import type { Engine, Register } from 'claude-code'

// /handoff calls this tool as its last step: when the turn ends, the conversation is compacted once
// with the handoff file's full text as the summary, then "continue" is sent automatically, so the
// same session picks up where it left off. Auto-compaction and a manual /compact are left alone.

const TOOL = 'compact_now'
// The standalone mod this plugin replaced (handoff-compact) may still be installed: its tool has another
// name and each copy only takes over the compaction after its own tool was called, so the two never act
// on the same handoff. Standing aside while it is enabled was tried in 0.2.0 and left no tool at all once
// the old one could no longer load (gone from the marketplace, yet still enabled).

// The handoff is written in the user's language; the visible lines follow it.
const isChinese = (text: string) => (text.match(/[一-鿿]/g)?.length ?? 0) >= 50
const words = (text: string) =>
  isChinese(text)
    ? {
        cont: '继续（上面就是交接文件全文，按它的开场指令往下做）',
        header: (path: string) => `【上一段对话已压缩。下面是交接文件 ${path} 的全文，代替压缩摘要】`,
        ack: '交接文件读到了，等你说继续。',
        failed: (path: string) => `交接压缩没做成（打 /clear，再说「读 ${path} 接着干」即可接上）：`,
      }
    : {
        cont: 'Continue (the handoff file is above; follow its opening instructions)',
        header: (path: string) => `[The conversation so far was compacted. Below is the full text of the handoff file ${path}, in place of a summary]`,
        ack: 'Handoff file received. Waiting for you to say continue.',
        failed: (path: string) => `Handoff compaction failed (type /clear, then say "read ${path} and continue"): `,
      }

type Pending = { path: string; text: string }
let pending: Pending | undefined
// Set once the /compact is queued: only that compaction is taken over, never a later unrelated one.
let armed = false
// A queued /compact that never reaches session.compact (cancelled) must not leave the mod armed.
const ARMED_FOR_MS = 120_000

function clear(): void {
  pending = undefined
  armed = false
}

// In the desktop app (a headless session) $.session.compact is not available ("not available in a
// headless (-p / SDK) session yet: compaction here runs inside a turn (a /compact prompt)"), so a
// /compact command is queued instead; a command waits until the session is idle, no retry needed.
function queueCompact($: Engine): void {
  const p = pending
  $.clock.after(ARMED_FOR_MS, () => {
    if (pending === p) clear()
  })
  $.command.run({ command: 'compact' }).catch(err => {
    const failed = pending ? words(pending.text).failed(pending.path) : ''
    clear()
    $.ui.toast(`${failed}${String(err)}`)
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: TOOL,
      description:
        'Call only as the very last step of /handoff, after the handoff file is written. When this turn ends, ' +
        'the context is compacted once with that file as the summary, and work resumes automatically. ' +
        'path is the absolute path of the handoff file.',
      inputSchema: {
        type: 'object',
        properties: { path: { type: 'string', description: 'Absolute path of the handoff file' } },
        required: ['path'],
      },
      isDeferred: false,
    })
    return next(e)
  })

  // mcp__<plugin name>__<tool name>, written out so the engine can read it from the source
  on('tool.call', { tool: 'mcp__handoff__compact_now' }, async ($, e) => {
    const path = String((e as { path?: unknown }).path ?? '')
    if (!path.startsWith('/')) return { deny: 'path must be an absolute path' }
    if (!(await $.fs.exists(path))) return { deny: `Handoff file not found: ${path}` }
    const text = await $.fs.read(path)
    if (typeof text !== 'string' || text.trim() === '') return { deny: `Handoff file is empty: ${path}` }
    pending = { path, text }
    armed = false
    return {
      result:
        `Queued: when this reply ends, the context is compacted with the full text of ${path} as the summary, ` +
        'then "continue" is sent automatically. End this reply now; do not call any other tool.',
    }
  })

  on('turn.complete', async ($, e, next) => {
    const out = await next(e)
    if (pending && !armed && e.agentId === undefined) {
      // Interrupted or failed turn: drop the handoff, the user's later /compact stays theirs
      if (e.isAborted || e.reason !== 'answer') clear()
      else {
        armed = true
        $.clock.after(300, () => queueCompact($))
      }
    }
    return out
  })

  on('session.end', async ($, e, next) => {
    clear()
    return next(e)
  })

  // Takes over only the compaction right after a handoff was queued; anything else (nothing queued,
  // a subagent, a precompute) goes to the engine untouched.
  on('session.compact', async ($, e, next) => {
    if (!pending || !armed || e.agentId !== undefined || e.trigger === 'precompute') return next(e)
    const { path, text } = pending
    clear()
    const w = words(text)
    // "continue" is queued after the compaction turn and sent once the session is idle
    $.clock.after(300, () => void $.prompt.submit({ text: w.cont, asUser: true }))
    return {
      messages: [
        { role: 'user', text: `${w.header(path)}\n\n${text}`, toolUses: [] },
        { role: 'assistant', text: w.ack, toolUses: [] },
      ],
    }
  })
}
