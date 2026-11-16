import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'
import type { Engine, Plugin } from 'claude-code/testing'

const URL = 'http://127.0.0.1:8765'
const UNCUT = { isStdoutTruncated: false, isStderrTruncated: false }
// /studio as the person types it at the terminal.
const STUDIO = {
  command: 'studio',
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: false, columns: 120 },
} as Parameters<Engine['command']['run']>[0]

type Sent = { path: string; body: Record<string, unknown> }
type ToolArgs = Parameters<Engine['tool']['call']>[0]
type TurnEnd = Parameters<Engine['turn']['complete']>[0]

// What the mocked world beneath the mod recorded, the server's stdout the test writes to, and
// the switches that change how the world answers.
type World = {
  sent: Sent[]
  prompts: string[]
  opened: string[][]
  spawned: string[][]
  toasts: string[]
  registered: string[]
  aborted: string[]
  chunk: (text: string) => void
  write: (line: string) => void
  exit: () => void
  clock: ReturnType<typeof mock.clock>
  fetch: 'ok' | 'not-ok' | 'fail' | 'hang'
  drop: boolean
  // Calls of this tool wait at the bottom until the test releases them, in order.
  holdTool?: string
  held: (() => void)[]
}

type WorldOptions = { env?: Record<string, string>; uname?: string }

// Mocks everything the mod reaches beneath it: a server whose stdout the test writes, the
// HTTP endpoints, prompt submission, the browser opener and the session's own nouns.
function world(on: On, options: WorldOptions = {}): World {
  const pieces: (string | null)[] = []
  let wake: (() => void) | undefined
  const push = (text: string | null): void => {
    pieces.push(text)
    wake?.()
  }
  const w: World = {
    sent: [],
    prompts: [],
    opened: [],
    spawned: [],
    toasts: [],
    registered: [],
    aborted: [],
    chunk: text => push(text),
    write: line => push(`${line}\n`),
    exit: () => push(null),
    clock: mock.clock(on),
    fetch: 'ok',
    drop: false,
    held: [],
  }
  mock.env(on, options.env ?? {})
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('tool.register', (_, e) => {
    w.registered.push(e.name)
    return { value: { tool: `mcp__studio__${e.name}` } }
  })
  on('ui.status', () => ({ value: undefined }))
  on('ui.log', () => ({ value: undefined }))
  on('ui.toast', (_, e) => {
    w.toasts.push(e.text)
    return { value: undefined }
  })
  on('process.run', (_, e) => {
    if (e.argv[0] === 'uname') return { value: { exitCode: 0, stdout: `${options.uname ?? 'Darwin'}\n`, stderr: '', ...UNCUT } }
    w.opened.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '', ...UNCUT } }
  })
  on('process.spawn', async function* (_, e) {
    w.spawned.push([...e.argv])
    for (;;) {
      if (pieces.length === 0) {
        await new Promise<void>(resolve => (wake = resolve))
        continue
      }
      const piece = pieces.shift()
      if (piece === null || piece === undefined) return { value: { code: 0, signal: null } }
      yield { stream: 'stdout' as const, text: piece }
    }
  })
  on('http.fetch', (_, e) => {
    if (w.fetch === 'fail') return { deny: 'connection refused' }
    if (w.fetch === 'hang') return new Promise<never>(() => undefined)
    w.sent.push({ path: e.url.slice(URL.length), body: JSON.parse(e.init?.body ?? '{}') })
    const ok = w.fetch === 'ok'
    return { value: { status: ok ? 200 : 500, ok, headers: {}, text: '' } }
  })
  on('prompt.submit', (_, e) => {
    w.prompts.push(e.text)
    return w.drop ? { drop: 'blocked' } : { text: e.text }
  })
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.abort', (_, e) => {
    w.aborted.push(e.turnId)
    return { value: undefined }
  })
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', async (_, e) => {
    if (e.tool === w.holdTool) await new Promise<void>(resolve => w.held.push(resolve))
    return { result: 'ran' }
  })

  return w
}

const events = (w: World, kind: string) =>
  w.sent.filter(s => s.path === '/event' && s.body.kind === kind).map(s => s.body)

const states = (w: World) => events(w, 'state').map(({ busy, current, queued }) => ({ busy, current, queued }))

// Stands for the person: above the mod, it allows every approval no hook beneath settled, as a
// person pressing "Yes" in the dialog would (the kit itself refuses such an ask at once).
const PERSON: Plugin = {
  name: 'person',
  tier: 'prepend',
  register: on => {
    on('classic.PermissionRequest', async (_, e, next) => {
      const result = await next(e)
      return result.decision === undefined ? { ...result, decision: { behavior: 'allow' } } : result
    })
  },
}

const heartbeats = (w: World) => w.sent.filter(s => s.path === '/heartbeat').length

async function startStudio($: Engine, w: World): Promise<string | undefined> {
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const run = $.command.run(STUDIO)
  w.write(JSON.stringify({ type: 'ready', url: URL }))
  const result = await run
  await w.clock.settle()

  return result.text
}

const request = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  action: 'generate',
  kind: 'image',
  skill: 'images',
  project: '/studio/images/cats',
  brief: 'a cat',
  ...extra,
})

async function sendRequest(w: World, id: string): Promise<void> {
  w.write(JSON.stringify({ type: 'request', request: request(id) }))
  await w.clock.settle()
}

const end = (turnId: string, agentId?: string): TurnEnd =>
  ({ reason: 'answer', answer: '', durationMs: 1, isAborted: false, turnId, agentId }) as TurnEnd

// Starts the main loop's turn with `text` as its prompt.
async function begin($: Engine, w: World, turnId: string, text: string): Promise<void> {
  await $.turn.start({ text, turnId })
  await w.clock.settle()
}

async function finish($: Engine, w: World, turnId: string): Promise<void> {
  await $.turn.complete(end(turnId))
  await w.clock.settle()
}

test('/studio starts the server, opens the page, publishes state and heartbeats every 5 s', async ($, on) => {
  const w = world(on)
  expect(await startStudio($, w)).toBe(`Studio is running at ${URL}`)
  expect(w.spawned).toHaveLength(1)
  expect(w.spawned[0]?.[0]).toMatch(/\/server\/studio-server\.sh$/)
  expect(w.opened).toEqual([['open', URL]])
  expect(states(w)).toEqual([{ busy: false, current: null, queued: [] }])

  await w.clock.advance(10_000)
  expect(heartbeats(w)).toBe(2)

  // A second /studio reuses the server and opens the page again.
  expect((await $.command.run(STUDIO)).text).toBe(`Studio is running at ${URL}`)
  await w.clock.settle()
  expect(w.spawned).toHaveLength(1)
  expect(w.opened).toHaveLength(2)
})

test('the page opens with cmd start on Windows', async ($, on) => {
  const w = world(on, { env: { OS: 'Windows_NT' } })
  await startStudio($, w)
  expect(w.opened).toEqual([['cmd', '/c', 'start', '', URL]])
})

test('the page opens with xdg-open on Linux', async ($, on) => {
  const w = world(on, { uname: 'Linux' })
  await startStudio($, w)
  expect(w.opened).toEqual([['xdg-open', URL]])
})

test('after the server exits: no heartbeats, the tools are refused, /studio spawns a new one', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.exit()
  await w.clock.settle()
  expect(w.toasts).toHaveLength(1)
  const beats = heartbeats(w)
  await w.clock.advance(20_000)
  expect(heartbeats(w)).toBe(beats)
  const result = await $.tool.call({ tool: 'mcp__studio__post', text: 'late' } as ToolArgs)
  expect(JSON.stringify(result)).toContain('not running')

  const run = $.command.run(STUDIO)
  w.write(JSON.stringify({ type: 'ready', url: URL }))
  expect((await run).text).toBe(`Studio is running at ${URL}`)
  expect(w.spawned).toHaveLength(2)
})

test('a server that exits before ready: /studio says it could not start', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const run = $.command.run(STUDIO)
  w.exit()
  expect((await run).text).toMatch(/^Studio could not start/)
  expect(w.toasts).toEqual([])
})

test('a server not ready in 5 s: /studio says it is starting, then opens the page or toasts a failure', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const run = $.command.run(STUDIO)
  await w.clock.settle()
  const waited = w.clock.advance(5000)
  expect((await run).text).toMatch(/^Studio is starting/)
  await waited
  expect(w.opened).toEqual([])
  w.write(JSON.stringify({ type: 'ready', url: URL }))
  await w.clock.settle()
  expect(w.opened).toEqual([['open', URL]])

  // A second start that fails after the "starting" answer is told with a toast.
  w.exit()
  await w.clock.settle()
  w.toasts.length = 0
  const again = $.command.run(STUDIO)
  await w.clock.settle()
  const waitedAgain = w.clock.advance(5000)
  expect((await again).text).toMatch(/^Studio is starting/)
  await waitedAgain
  w.exit()
  await w.clock.settle()
  expect(w.toasts).toHaveLength(1)
  expect(w.toasts[0]).toMatch(/^Studio could not start/)
})

test('a request becomes a prompt naming the workspace skill with the JSON verbatim', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const req = request('r1', { refs: ['/a b/ref.png'], note: 'quote " and ```' })
  w.write(JSON.stringify({ type: 'request', request: req }))
  await w.clock.settle()

  expect(w.prompts).toHaveLength(1)
  const prompt = w.prompts[0] ?? ''
  expect(prompt).toContain('`studio:images`')
  expect(prompt).toContain('Skill tool')
  expect(prompt).toContain('mcp__studio__post')
  expect(prompt).toContain('mcp__studio__note')
  const block = /```json\n([\s\S]*)\n```\n/.exec(prompt)?.[1] ?? ''
  expect(JSON.parse(block)).toEqual(req)
})

test('a request of another kind names the workspace skill it carries', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const req = request('r1', { kind: 'infographic', project: '/studio/infographics/heat-pump' })
  w.write(JSON.stringify({ type: 'request', request: req }))
  await w.clock.settle()

  expect(w.prompts).toHaveLength(1)
  expect(w.prompts[0]).toContain('`studio:images`')
  const block = /```json\n([\s\S]*)\n```\n/.exec(w.prompts[0] ?? '')?.[1] ?? ''
  expect(JSON.parse(block)).toEqual(req)
})

test('a slide request names studio:images and carries its slide and fields verbatim', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const change = request('r1', { kind: 'slide', project: '/studio/slides/garden', action: 'change', slide: 2,
    version: 3, marks: [], note: 'shorter title', marked: null, mask: null })
  const assemble = request('r2', { kind: 'slide', project: '/studio/slides/garden', action: 'assemble',
    assembly: 'native', versions: { 1: 2, 2: 3 } })
  w.write(JSON.stringify({ type: 'request', request: change }))
  w.write(JSON.stringify({ type: 'request', request: assemble }))
  await w.clock.settle()
  // The second is submitted once the first one's turn has run.
  await begin($, w, 't1', w.prompts[0] ?? '')
  await finish($, w, 't1')

  expect(w.prompts).toHaveLength(2)
  for (const [i, req] of [change, assemble].entries()) {
    expect(w.prompts[i]).toContain('`studio:images`')
    const block = /```json\n([\s\S]*)\n```\n/.exec(w.prompts[i] ?? '')?.[1] ?? ''
    expect(JSON.parse(block)).toEqual(req)
  }
})

test('stdout lines split across pieces and several in one piece are all read', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const one = JSON.stringify({ type: 'request', request: request('r1') })
  const two = JSON.stringify({ type: 'request', request: request('r2') })
  const three = JSON.stringify({ type: 'request', request: request('r3') })
  w.chunk(one.slice(0, 10))
  w.chunk(`${one.slice(10)}\n${two}\n${three.slice(0, 5)}`)
  w.chunk(`${three.slice(5)}\n`)
  await w.clock.settle()
  expect(w.prompts.map(p => /"id": "(r\d)"/.exec(p)?.[1])).toEqual(['r1'])
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r1', queued: ['r2', 'r3'] })
})

test('a bad stdout line is skipped and the next one still works', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.write('this is not json')
  w.write(JSON.stringify({ type: 'request', request: { id: 'x', skill: '../evil' } }))
  await sendRequest(w, 'r2')
  expect(w.prompts).toHaveLength(1)
  expect(w.prompts[0]).toContain('"id": "r2"')
})

test('state: current while idle, queued while busy, turns credited by their prompt', async ($, on) => {
  const w = world(on)
  await startStudio($, w)

  await sendRequest(w, 'r1')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r1', queued: [] })
  const [p1] = w.prompts

  await begin($, w, 't1', p1 ?? '')
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r1', queued: [] })

  await sendRequest(w, 'r2')
  await sendRequest(w, 'r3')
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r1', queued: ['r2', 'r3'] })

  await finish($, w, 't1')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: ['r3'] })
  expect(events(w, 'turn-end').at(-1)).toEqual(expect.objectContaining({ agent: null, reason: 'answer' }))

  // A turn the person started at the terminal runs no request.
  await begin($, w, 't2', 'what is in this folder?')
  expect(states(w).at(-1)).toEqual({ busy: true, current: null, queued: ['r2', 'r3'] })
  await finish($, w, 't2')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: ['r3'] })

  // A turn that runs r2's prompt, framed; r3 is submitted once it ended.
  await begin($, w, 't3', `The studio plugin sent a message:\n${w.prompts[1] ?? ''}`)
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r2', queued: ['r3'] })
  await finish($, w, 't3')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r3', queued: [] })
  await begin($, w, 't4', w.prompts[2] ?? '')
  await finish($, w, 't4')
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })

  // A subagent's turn changes nothing.
  const count = states(w).length
  await $.turn.start({ text: '', turnId: 'a1', agentId: 'agent-1' })
  await $.turn.complete(end('a1', 'agent-1'))
  await w.clock.settle()
  expect(states(w)).toHaveLength(count)
})

test('a dropped submission leaves the queue', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.drop = true
  await sendRequest(w, 'r1')
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })

  w.drop = false
  await sendRequest(w, 'r2')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: [] })
})

test('the tools are refused while the server is not running', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  for (const call of [
    { tool: 'mcp__studio__post', text: 'hi' },
    { tool: 'mcp__studio__note', text: 'working' },
  ]) {
    const result = await $.tool.call(call as ToolArgs)
    expect(JSON.stringify(result)).toContain('not running')
  }
  expect(w.sent).toEqual([])
})

test('the tools post their events while the server runs', async ($, on) => {
  const w = world(on)
  await startStudio($, w)

  await $.tool.call({ tool: 'mcp__studio__post', text: 'done', images: ['/p/v1.png'] } as ToolArgs)
  await $.tool.call({ tool: 'mcp__studio__note', text: 'step 1' } as ToolArgs)
  const head = { request: null, agent: null, time: expect.any(Number) }
  expect(events(w, 'agent')).toEqual([{ kind: 'agent', ...head, text: 'done', images: ['/p/v1.png'] }])
  expect(events(w, 'note')).toEqual([{ kind: 'note', ...head, text: 'step 1' }])
  // The mod's own tools are no tool events.
  expect(events(w, 'tool')).toEqual([])

  // The mod registers post and note alone.
  expect(w.registered).toEqual(['post', 'note'])
})

test('a fetch that fails or is not ok denies post and throws nothing', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  for (const mode of ['fail', 'not-ok'] as const) {
    w.fetch = mode
    const result = await $.tool.call({ tool: 'mcp__studio__post', text: 'x' } as ToolArgs)
    expect(JSON.stringify(result)).toContain('did not take')
    await sendRequest(w, `r-${mode}`)
    await w.clock.advance(5000)
  }
  // The second request waits until the first one's turn has run.
  expect(w.prompts).toHaveLength(1)
})

test('ask is sent when a person is asked, and ask-done once the call settled', async ($, on) => {
  const w = world(on)
  on('tool.check', () => ({ decision: 'ask' }))
  // Nothing beneath decides: the dialog would show.
  on('classic.PermissionRequest', () => ({}))
  await startStudio($, w)

  await $.tool.call({ tool: 'Bash', command: 'rm -rf build' })
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([
    { kind: 'ask', request: null, agent: null, time: expect.any(Number), use: expect.any(String), tool: 'Bash', text: 'rm -rf build' },
  ])
  expect(events(w, 'ask-done')).toHaveLength(1)
  const kinds = w.sent.filter(s => s.path === '/event').map(s => s.body.kind)
  expect(kinds.indexOf('ask')).toBeLessThan(kinds.indexOf('ask-done'))
})

test('no ask when a hook beneath settles the approval, or when the call is allowed', async ($, on) => {
  const w = world(on)
  let verdict: 'ask' | 'allow' = 'ask'
  on('tool.check', () => ({ decision: verdict }))
  on('classic.PermissionRequest', () => ({ decision: { behavior: 'allow' } }))
  await startStudio($, w)
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  verdict = 'allow'
  await $.tool.call({ tool: 'Bash', command: 'pwd' })
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([])
  expect(events(w, 'ask-done')).toEqual([])
})

test('an ask still open when the turn ends gets ask-done then, and only once', { plugins: [PERSON] }, async ($, on) => {
  const w = world(on)
  w.holdTool = 'Write'
  on('tool.check', () => ({ decision: 'ask' }))
  on('classic.PermissionRequest', () => ({}))
  await startStudio($, w)

  const call = $.tool.call({ tool: 'Write', file_path: '/tmp/x', content: 'x' })
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([expect.objectContaining({ kind: 'ask', tool: 'Write', text: '/tmp/x' })])
  expect(w.held).toHaveLength(1)
  expect(events(w, 'ask-done')).toEqual([])
  await begin($, w, 't1', 'go')
  await finish($, w, 't1')
  expect(events(w, 'ask-done')).toHaveLength(1)
  w.held[0]?.()
  await call
  await w.clock.settle()
  expect(events(w, 'ask-done')).toHaveLength(1)
})

test('the session end sends ended to the page', async ($, on) => {
  const w = world(on)
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  await startStudio($, w)
  await $.session.end({
    reason: 'prompt_input_exit',
    sessionId: 's1',
    resume: {},
  } as unknown as Parameters<Engine['session']['end']>[0])
  expect(events(w, 'ended')).toEqual([{ kind: 'ended' }])
})

test('requests are submitted one at a time, each once the session is idle', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await sendRequest(w, 'r2')
  await sendRequest(w, 'r3')
  expect(w.prompts).toHaveLength(1)
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r1', queued: ['r2', 'r3'] })
  await begin($, w, 't1', w.prompts[0] ?? '')
  await finish($, w, 't1')
  expect(w.prompts).toHaveLength(2)
  expect(w.prompts[1]).toContain('"id": "r2"')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: ['r3'] })

  // A dropped submission gives way to the next request.
  w.drop = true
  await begin($, w, 't2', w.prompts[1] ?? '')
  await finish($, w, 't2')
  expect(w.prompts).toHaveLength(3)
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })
})

test('a POST that gets no answer marks the server down until a heartbeat is answered', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.fetch = 'hang'
  const first = $.tool.call({ tool: 'mcp__studio__post', text: 'a' } as ToolArgs)
  await w.clock.settle()
  const advanced = w.clock.advance(2000)
  expect(JSON.stringify(await first)).toContain('did not take')
  await advanced

  // Down: refused at once, without a fetch, however many earlier POSTs hang.
  const before = w.sent.length
  const second = await $.tool.call({ tool: 'mcp__studio__note', text: 'b' } as ToolArgs)
  expect(JSON.stringify(second)).toContain('did not take')
  expect(w.sent.length).toBe(before)

  // An answered heartbeat brings it back.
  w.fetch = 'ok'
  await w.clock.advance(5000)
  expect(w.sent.at(-1)).toEqual({ path: '/event', body: { kind: 'state', busy: false, current: null, queued: [], started: null } })
  const third = await $.tool.call({ tool: 'mcp__studio__post', text: 'c' } as ToolArgs)
  expect(JSON.stringify(third)).toContain('Shown in the Studio page')
  expect(events(w, 'agent').map(e => e.text)).toEqual(['c'])
})

test('the server exiting after session.end is not told with a toast', async ($, on) => {
  const w = world(on)
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  await startStudio($, w)
  await $.session.end({ reason: 'clear', sessionId: 's1', resume: {} } as unknown as Parameters<
    Engine['session']['end']
  >[0])
  w.exit()
  await w.clock.settle()
  expect(w.toasts).toEqual([])
})

test('two parallel calls with the same input: the one settled silently sends no ask-done', { plugins: [PERSON] }, async ($, on) => {
  const w = world(on)
  w.holdTool = 'Write'
  let requests = 0
  on('tool.check', () => ({ decision: 'ask' }))
  // The first PermissionRequest is settled by a hook beneath; the second shows the dialog.
  on('classic.PermissionRequest', () => (requests++ === 0 ? { decision: { behavior: 'allow' } } : {}))
  await startStudio($, w)

  const input = { tool: 'Write', file_path: '/tmp/same', content: 'x' } as const
  const a = $.tool.call(input)
  await w.clock.settle()
  const b = $.tool.call(input)
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([expect.objectContaining({ kind: 'ask', tool: 'Write', text: '/tmp/same' })])
  expect(w.held).toHaveLength(2)

  w.held[0]?.()
  await a
  await w.clock.settle()
  expect(events(w, 'ask-done')).toEqual([])
  w.held[1]?.()
  await b
  await w.clock.settle()
  expect(events(w, 'ask-done')).toHaveLength(1)
})

test('stop of the running request ends its turn; the next prompt names it', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  expect(events(w, 'state').at(-1)?.started).toEqual(expect.any(Number))

  w.write(JSON.stringify({ type: 'stop', id: 'r1' }))
  await w.clock.settle()
  expect(w.aborted).toEqual(['t1'])
  expect(events(w, 'stopped')).toEqual([{ kind: 'stopped', id: 'r1' }])

  await $.turn.complete({ ...end('t1'), reason: 'aborted' } as TurnEnd)
  await w.clock.settle()
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })
  expect(events(w, 'state').at(-1)?.started).toBeNull()

  // A background task's notification after the stop starts a turn that is ended too; a turn
  // the person types ends that.
  await begin($, w, 'n1', '<task-notification>\n<task-id>a1</task-id>')
  expect(w.aborted).toEqual(['t1', 'n1'])
  await finish($, w, 'n1')
  await begin($, w, 'x1', 'what is in this folder?')
  await finish($, w, 'x1')
  await begin($, w, 'n2', '<task-notification>\n<task-id>a2</task-id>')
  expect(w.aborted).toEqual(['t1', 'n1'])
  await finish($, w, 'n2')

  await sendRequest(w, 'r2')
  expect(w.prompts[1]).toMatch(/^The user stopped the Studio request r1 in the page/)
  await begin($, w, 't2', w.prompts[1] ?? '')
  await finish($, w, 't2')
  await sendRequest(w, 'r3')
  expect(w.prompts[2]).toMatch(/^A request from the Studio page/)
})

test('done follows a turn that ended with the answer; another end sends a note, a stopped one neither', async ($, on) => {
  const w = world(on)
  await startStudio($, w)

  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  await finish($, w, 't1')
  expect(events(w, 'done')).toEqual([{ kind: 'done', id: 'r1' }])
  // `done` reaches the server before the state that drops the request.
  const kinds = w.sent.filter(s => s.path === '/event').map(s => s.body.kind)
  expect(kinds.lastIndexOf('done')).toBeLessThan(kinds.lastIndexOf('state'))

  await sendRequest(w, 'r2')
  await begin($, w, 't2', w.prompts[1] ?? '')
  await $.turn.complete({ ...end('t2'), reason: 'max_turns' } as TurnEnd)
  await w.clock.settle()
  expect(events(w, 'done')).toHaveLength(1)
  expect(events(w, 'note')).toEqual([{ kind: 'note', request: 'r2', agent: null, time: expect.any(Number),
    text: 'The turn ended without finishing this request (max_turns).' }])

  await sendRequest(w, 'r3')
  await begin($, w, 't3', w.prompts[2] ?? '')
  w.write(JSON.stringify({ type: 'stop', id: 'r3' }))
  await w.clock.settle()
  await $.turn.complete({ ...end('t3'), reason: 'aborted' } as TurnEnd)
  await w.clock.settle()
  expect(events(w, 'done')).toHaveLength(1)
  expect(events(w, 'note')).toHaveLength(1)

  // A terminal turn runs no request: neither.
  await begin($, w, 't4', 'what is in this folder?')
  await finish($, w, 't4')
  expect(events(w, 'done')).toHaveLength(1)
})

test('a mark-scene request reaches the prompt unchanged', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const req = request('m1', { action: 'mark-scene', kind: 'short-video', skill: 'videos', project: '/studio/short-video/f',
    scene: 'intro', version: 2, t: 1.5, world: null, world_t: null, mark: { rect: { x: 10, y: 20, w: 300, h: 100 } },
    ids: ['title'], marked: '/studio/short-video/f/comments/intro/v2-t1.50-1.png', text: 'larger' })
  delete (req as Record<string, unknown>).brief
  w.write(JSON.stringify({ type: 'request', request: req }))
  await w.clock.settle()
  expect(w.prompts[0]).toContain('`studio:videos`')
  expect(w.prompts[0]).toContain(JSON.stringify(req, null, 2))
})

test('stop of a waiting request takes it out of the queue; a submitted one ends when it starts', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  await sendRequest(w, 'r2')
  await sendRequest(w, 'r3')

  // r2 was never submitted: it leaves the queue and no prompt names it.
  w.write(JSON.stringify({ type: 'stop', id: 'r2' }))
  await w.clock.settle()
  expect(w.aborted).toEqual([])
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r1', queued: ['r3'] })
  expect(events(w, 'stopped')).toEqual([{ kind: 'stopped', id: 'r2' }])

  // A stop of an id the mod does not hold changes nothing.
  w.write(JSON.stringify({ type: 'stop', id: 'nope' }))
  await w.clock.settle()
  expect(events(w, 'stopped')).toHaveLength(1)

  await finish($, w, 't1')
  expect(w.prompts).toHaveLength(2)
  expect(w.prompts[1]).toMatch(/^A request from the Studio page/)
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r3', queued: [] })

  // r3 is submitted: its turn ends as soon as it starts, quieting nothing, and the next prompt names it.
  w.write(JSON.stringify({ type: 'stop', id: 'r3' }))
  await w.clock.settle()
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })
  await begin($, w, 't2', w.prompts[1] ?? '')
  expect(w.aborted).toEqual(['t2'])
  expect(states(w).at(-1)).toEqual({ busy: true, current: null, queued: [] })
  await finish($, w, 't2')
  await begin($, w, 'n1', '<task-notification>\n<task-id>a1</task-id>')
  expect(w.aborted).toEqual(['t2'])
  await finish($, w, 'n1')
  await sendRequest(w, 'r4')
  expect(w.prompts[2]).toMatch(/^The user stopped the Studio request r3 in the page/)
  expect(events(w, 'stopped')).toHaveLength(2)
})

test('every tool call of a request reaches the page as tool and tool-end events, none dropped', async ($, on) => {
  const w = world(on)
  w.holdTool = 'Read'
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  const head = { request: 'r1', agent: null, time: expect.any(Number) }
  expect(events(w, 'turn-start')).toEqual([{ kind: 'turn-start', ...head }])

  const long = 'x'.repeat(5000)
  await $.tool.call({ tool: 'Bash', command: 'ls -la', description: 'List files', tool_use_id: 'u1' } as unknown as ToolArgs)
  const read = $.tool.call({ tool: 'Read', file_path: '/a', tool_use_id: 'u2' } as unknown as ToolArgs)
  await w.clock.settle()
  await w.clock.advance(1500)
  w.held[0]?.()
  await read
  await $.tool.call({ tool: 'mcp__x__y', text: long, list: [1, 2], tool_use_id: 'u3' } as unknown as ToolArgs)
  await w.clock.settle()

  // Each call's whole input, in order, its strings together cut at 4000 characters.
  expect(events(w, 'tool')).toEqual([
    { kind: 'tool', ...head, use: 'u1', tool: 'Bash', input: { command: 'ls -la', description: 'List files' } },
    { kind: 'tool', ...head, use: 'u2', tool: 'Read', input: { file_path: '/a' } },
    { kind: 'tool', ...head, use: 'u3', tool: 'x__y', input: { text: `${'x'.repeat(3999)}…`, list: '…' } },
  ])
  const ends = events(w, 'tool-end')
  expect(ends.map(e => [e.use, e.ok, e.request])).toEqual([
    ['u1', true, 'r1'],
    ['u2', true, 'r1'],
    ['u3', true, 'r1'],
  ])
  expect(ends[1]?.ms).toBe(1500)
  // Each call's end comes after its start.
  const order = w.sent.filter(s => s.body.kind === 'tool' || s.body.kind === 'tool-end').map(s => `${s.body.kind}:${s.body.use}`)
  expect(order.indexOf('tool:u2')).toBeLessThan(order.indexOf('tool-end:u2'))

  await finish($, w, 't1')
  expect(events(w, 'turn-end')).toEqual([{ kind: 'turn-end', ...head, reason: 'answer', ms: 1 }])
})

test('a failed call ends with ok false and its error', async ($, on) => {
  // Above the world's tool.call, so it answers first.
  on('tool.call', { tool: 'Bash' }, () => ({ deny: 'no such directory' }))
  const w = world(on)
  await startStudio($, w)
  await $.tool.call({ tool: 'Bash', command: 'ls nowhere', tool_use_id: 'g1' } as unknown as ToolArgs)
  await w.clock.settle()
  expect(events(w, 'tool-end')).toEqual([
    expect.objectContaining({ use: 'g1', tool: 'Bash', ok: false, error: 'no such directory' }),
  ])
})

test('a terminal turn is logged with request null and its prompt', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await begin($, w, 'x1', 'what is in this folder?')
  await $.tool.call({ tool: 'Bash', command: 'ls', tool_use_id: 'u1' } as unknown as ToolArgs)
  await finish($, w, 'x1')
  expect(events(w, 'turn-start')).toEqual([
    { kind: 'turn-start', request: null, agent: null, time: expect.any(Number), text: 'what is in this folder?' },
  ])
  expect(events(w, 'tool')).toEqual([expect.objectContaining({ request: null, agent: null, tool: 'Bash' })])
  expect(events(w, 'turn-end')).toHaveLength(1)
})

test('a subagent is logged under the request that spawned it, with its type and task', async ($, on) => {
  const w = world(on)
  on('agent.spawn', () => ({ model: 'm', agentId: 'a1' }))
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  await $.agent.spawn({ prompt: 'Find the files', description: 'Find files', subagentType: 'Explore' } as Parameters<
    Engine['agent']['spawn']
  >[0])
  await $.turn.start({ text: 'Find the files', turnId: 's1', agentId: 'a1' })
  await $.tool.call({ tool: 'Grep', pattern: 'cat', agentId: 'a1', tool_use_id: 'u1' } as unknown as ToolArgs)
  await $.turn.complete(end('s1', 'a1'))
  await finish($, w, 't1')
  // A background subagent goes on after the request's turn: it stays the request's.
  await $.tool.call({ tool: 'Read', file_path: '/b', agentId: 'a1', tool_use_id: 'u2' } as unknown as ToolArgs)
  await w.clock.settle()

  expect(events(w, 'agent-start')).toEqual([
    {
      kind: 'agent-start',
      request: 'r1',
      agent: 'a1',
      time: expect.any(Number),
      parent: null,
      type: 'Explore',
      description: 'Find files',
      background: false,
      prompt: 'Find the files',
    },
  ])
  expect(events(w, 'turn-start').map(e => [e.agent, e.request])).toEqual([
    [null, 'r1'],
    ['a1', 'r1'],
  ])
  expect(events(w, 'tool').map(e => [e.agent, e.request, e.tool])).toEqual([
    ['a1', 'r1', 'Grep'],
    ['a1', 'r1', 'Read'],
  ])
  expect(events(w, 'turn-end').map(e => [e.agent, e.request])).toEqual([
    ['a1', 'r1'],
    [null, 'r1'],
  ])
})

test("a subagent's first turn, which starts before its spawn resolves, is its spawner's request", async ($, on) => {
  const w = world(on)
  // As the engine does: the child's first turn starts inside the spawn, before its id is answered.
  on('agent.spawn', async (_, e) => {
    const id = e.prompt === 'Parent task' ? 'p1' : 'c1'
    await $.turn.start({ text: e.prompt, turnId: `s-${id}`, agentId: id })
    return { model: 'm', agentId: id }
  })
  const spawn = (prompt: string, parentAgentId?: string) =>
    $.agent.spawn({ prompt, description: prompt, subagentType: 'general-purpose', parentAgentId } as Parameters<
      Engine['agent']['spawn']
    >[0])
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  await spawn('Parent task')
  await finish($, w, 't1')
  // r1's turn ended; a turn typed in the terminal runs while r1's background subagent p1 spawns c1.
  await begin($, w, 'x1', 'what is in this folder?')
  await spawn('Child task', 'p1')
  await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'c1', tool_use_id: 'c-u1' } as unknown as ToolArgs)
  await w.clock.settle()

  expect(events(w, 'turn-start').map(e => [e.agent, e.request])).toEqual([
    [null, 'r1'],
    ['p1', 'r1'],
    [null, null],
    ['c1', 'r1'],
  ])
  expect(events(w, 'agent-start').map(e => [e.agent, e.request, e.parent])).toEqual([
    ['p1', 'r1', null],
    ['c1', 'r1', 'p1'],
  ])
  expect(events(w, 'tool').map(e => [e.agent, e.request])).toEqual([['c1', 'r1']])
})

test('event strings are bounded: post text and images, a whole tool input, an ask', async ($, on) => {
  const w = world(on)
  on('tool.check', () => ({ decision: 'ask' }))
  on('classic.PermissionRequest', () => ({}))
  await startStudio($, w)
  const long = 'y'.repeat(5000)
  await $.tool.call({ tool: 'mcp__studio__post', text: long, images: [long] } as ToolArgs)
  const posted = events(w, 'agent')[0]
  expect((posted?.text as string).length).toBe(4000)
  expect((posted?.images as string[])[0]?.endsWith('…')).toBe(true)

  await $.tool.call({ tool: 'Write', file_path: '/f', content: long, tool_use_id: 'w1' } as unknown as ToolArgs)
  await w.clock.settle()
  const input = events(w, 'tool')[0]?.input as Record<string, string>
  expect(input.file_path).toBe('/f')
  expect((input.file_path ?? '').length + (input.content ?? '').length).toBe(4000)
  await $.tool.call({ tool: 'Bash', command: long, tool_use_id: 'b1' } as unknown as ToolArgs)
  await w.clock.settle()
  const ask = events(w, 'ask').at(-1)
  expect((ask?.text as string).length).toBe(200)
  expect((ask?.text as string).endsWith('…')).toBe(true)
})

test("the agent's text blocks reach the page as text events, its other blocks do not", async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  const row = (content: Record<string, unknown>[], agentId?: string) =>
    ({
      message: { type: 'assistant', role: 'assistant', content },
      door: 'response',
      origin: { kind: 'model', model: 'm' },
      uuid: `row-${content.length}-${agentId ?? 'main'}`,
      ...(agentId ? { agentId } : {}),
    }) as unknown as Parameters<Engine['session']['append']>[0]
  await $.session.append(row([{ type: 'text', text: 'I will draw the cat.' }]))
  await $.session.append(row([{ type: 'tool_use', id: 'u1', name: 'Bash', input: {} }, { type: 'thinking', thinking: 'x' }]))
  await w.clock.settle()
  expect(events(w, 'text')).toEqual([
    { kind: 'text', request: 'r1', agent: null, time: expect.any(Number), text: 'I will draw the cat.' },
  ])
})

test('a permission ask and its answer are logged with the call', { plugins: [PERSON] }, async ($, on) => {
  const w = world(on)
  on('tool.check', () => ({ decision: 'ask' }))
  on('classic.PermissionRequest', () => ({}))
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await begin($, w, 't1', w.prompts[0] ?? '')
  await $.tool.call({ tool: 'Bash', command: 'rm -rf build', tool_use_id: 'u1' } as unknown as ToolArgs)
  await w.clock.settle()
  const ask = events(w, 'ask')[0]
  expect(ask).toEqual(expect.objectContaining({ request: 'r1', tool: 'Bash', text: 'rm -rf build' }))
  expect(events(w, 'answer')).toEqual([
    { kind: 'answer', request: 'r1', agent: null, time: expect.any(Number), use: ask?.use, tool: 'Bash', ok: true },
  ])
  const kinds = w.sent.map(s => s.body.kind)
  expect(kinds.indexOf('ask')).toBeLessThan(kinds.indexOf('answer'))
})

test('a submitted prompt passed by two other turns counts as lost, and the queue goes on', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await sendRequest(w, 'r2')
  for (const id of ['x1', 'x2']) {
    await begin($, w, id, 'typed at the terminal')
    await finish($, w, id)
  }
  expect(w.prompts).toHaveLength(2)
  expect(w.prompts[1]).toContain('"id": "r2"')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: [] })
})

test('a stopped submitted prompt does not hold the next request back', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await sendRequest(w, 'r2')
  w.write(JSON.stringify({ type: 'stop', id: 'r1' }))
  await w.clock.settle()
  expect(w.prompts).toHaveLength(2)
  expect(w.prompts[1]).toMatch(/^The user stopped the Studio request r1 in the page/)
  await begin($, w, 't1', w.prompts[0] ?? '')
  expect(w.aborted).toEqual(['t1'])
})
