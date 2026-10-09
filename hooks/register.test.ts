import { test, expect, mock } from 'claude-code/testing'

const P = '/tmp/HANDOFF-test.md'
const BODY = '# HANDOFF\n§0 first item'
const ZH = '# 交接\n' + '本轮是第一次走完整的交接流程，先问两件事。'.repeat(5)
const TOOL = 'mcp__handoff__compact_now'
const turn = (over = {}) => ({ answer: 'ok', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' as const, ...over })

// Mocks the world beneath the mod; records the /compact commands and prompts it sends.
function world(on: Parameters<Parameters<typeof test>[1]>[1], body: string) {
  const sent = { compacts: 0, prompts: [] as string[] }
  on('fs.exists', ($, e) => ({ value: e.path === P }))
  on('fs.read', () => ({ value: body }))
  on('session.compact', () => ({ skip: 'engine-bottom' }))
  on('turn.complete', () => ({ text: '' }))
  on('command.run', ($, e) => {
    if (e.command === 'compact') sent.compacts++
    return { text: '' }
  })
  on('prompt.submit', ($, e) => {
    sent.prompts.push(e.text)
    return { drop: 'test' }
  })
  return sent
}

test('end to end: queue, compact once with the handoff, then continue', async ($, on) => {
  const clock = mock.clock(on)
  const sent = world(on, BODY)

  const queued = await $.tool.call({ tool: TOOL, path: P })
  expect(String(queued.result)).toContain('Queued')
  await $.turn.complete(turn())
  await clock.advance(300)
  expect(sent.compacts).toBe(1)

  const first = await $.session.compact({})
  expect('messages' in first).toBe(true)
  if ('messages' in first) {
    expect(first.messages[0].text).toContain(BODY)
    expect(first.messages[0].text).toContain(P)
    expect(first.messages[0].text).toContain('in place of a summary')
  }
  await clock.advance(300)
  expect(sent.prompts).toEqual(['Continue (the handoff file is above; follow its opening instructions)'])

  // used up: the next compaction is the engine's, and no second "continue"
  expect(await $.session.compact({})).toEqual({ skip: 'engine-bottom' })
  await $.turn.complete(turn({ turnId: 't2' }))
  await clock.advance(1000)
  expect(sent.compacts).toBe(1)
  expect(sent.prompts.length).toBe(1)
})

test('interrupted turn: nothing queued, a later /compact is left to the engine', async ($, on) => {
  const clock = mock.clock(on)
  const sent = world(on, BODY)

  await $.tool.call({ tool: TOOL, path: P })
  await $.turn.complete(turn({ isAborted: true, reason: 'aborted' }))
  await clock.advance(1000)
  expect(sent.compacts).toBe(0)
  expect(await $.session.compact({})).toEqual({ skip: 'engine-bottom' })
  await $.turn.complete(turn({ turnId: 't2' }))
  await clock.advance(1000)
  expect(sent.compacts).toBe(0)
})

test('a compaction before the queued one is left to the engine; the queue expires', async ($, on) => {
  const clock = mock.clock(on)
  const sent = world(on, BODY)

  await $.tool.call({ tool: TOOL, path: P })
  expect(await $.session.compact({})).toEqual({ skip: 'engine-bottom' })

  await $.turn.complete(turn())
  await clock.advance(300)
  expect(sent.compacts).toBe(1)
  await clock.advance(120_000)
  expect(await $.session.compact({})).toEqual({ skip: 'engine-bottom' })
  expect(sent.prompts.length).toBe(0)
})

test('a Chinese handoff gets Chinese lines', async ($, on) => {
  const clock = mock.clock(on)
  const sent = world(on, ZH)

  await $.tool.call({ tool: TOOL, path: P })
  await $.turn.complete(turn())
  await clock.advance(300)
  const out = await $.session.compact({})
  expect('messages' in out).toBe(true)
  if ('messages' in out) {
    expect(out.messages[0].text).toContain('代替压缩摘要')
    expect(out.messages[1].text).toContain('等你说继续')
  }
  await clock.advance(300)
  expect(sent.prompts[0]).toContain('继续')
})

test('bad paths are refused', async ($, on) => {
  on('fs.exists', () => ({ value: false }))
  const rel = await $.tool.call({ tool: TOOL, path: 'HANDOFF.md' })
  expect(rel.deny).toContain('absolute path')
  const missing = await $.tool.call({ tool: TOOL, path: P })
  expect(missing.deny).toContain('not found')
})
